"""Rubric judge for proposals, calibrated against human labels with Cohen's kappa.

Judges every proposal in the decision and architecture results (verdicts are cached by text), writes the blind
30-item labelling sheet with --sheet and the classmates' pairwise sheet with --panel, and reports kappa and win
rates once people fill them in.
Usage: python -m evals.runners.judge [--sheet] [--panel]
"""
import argparse
import csv
import hashlib
import json
import random
import time
from collections import Counter, defaultdict
from itertools import combinations
from statistics import mean
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from agent.model import config, prompt
from evals.dataset import load
from evals.metrics import kappa
from evals.runners.common import RESULTS, ROOT, write

LABELS = ROOT / "evals/labels"
SHEET, KEY = LABELS / "judge_calibration.csv", LABELS / "judge_calibration_key.json"
PANEL, PANEL_KEY = LABELS / "panel_pairs.csv", LABELS / "panel_pairs_key.json"
URL = "https://api.groq.com/openai/v1/chat/completions"
CRITERIA = ("relevance", "evidence", "specificity", "clarity", "screening")


class Verdict(BaseModel):
    relevance: int = Field(ge=1, le=5)
    evidence: int = Field(ge=1, le=5)
    specificity: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    screening: int = Field(ge=1, le=5)
    overall: Literal["good", "acceptable", "poor"]
    reason: str


def proposals():
    """Every drafted proposal in the per-job results files, keyed by job and text."""
    jobs = {job["id"]: job for persona in load() for job in persona["jobs"]}
    found = []
    for path in sorted(RESULTS.glob("decisions-*.jsonl")) + sorted(RESULTS.glob("architecture-*.jsonl")):
        for row in map(json.loads, path.read_text().splitlines()):
            if row.get("draft") and row["job"] in jobs:
                key = hashlib.sha256(f"{row['job']}\n{row['draft']}".encode()).hexdigest()[:16]
                found.append({"key": key, "source": path.stem, "job": jobs[row["job"]], "persona": row["persona"],
                              "text": row["draft"], "answers": row.get("screening_answers") or {}})
    return found


def verdict(item):
    """One judge call; None when the daily quota is spent."""
    from apps.api.config import settings

    job = item["job"]
    post = {k: job[k] for k in ("title", "description", "skills", "deliverables", "screening_questions")}
    system = f"{prompt('judge')}\n{prompt('json_mode').strip()} {json.dumps(Verdict.model_json_schema())}"
    judge = config()["evaluation"]["judge"]
    body = {"model": judge["model"], "temperature": 0, "reasoning_effort": judge["reasoning_effort"],
            "max_completion_tokens": judge["max_tokens"], "response_format": {"type": "json_object"}, "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"job": post, "proposal": item["text"],
                                                        "screening_answers": item["answers"]})}]}
    for _ in range(10):
        response = httpx.post(URL, headers={"Authorization": f"Bearer {settings().groq_api_key}"}, json=body, timeout=90)
        wait = float(response.headers.get("retry-after", 20))
        if response.status_code == 429:
            if wait > 300:
                return None
            time.sleep(wait)
            continue
        response.raise_for_status()
        out = response.json()
        try:
            return {**Verdict.model_validate_json(out["choices"][0]["message"]["content"]).model_dump(),
                    "tokens": out["usage"]["total_tokens"]}
        except ValidationError as exc:
            return {"invalid": str(exc)[:300], "tokens": out["usage"]["total_tokens"]}
    return None


def sheet(items):
    """Grows the blind sheet towards 30 proposals spread across result sources, shown without their source or
    the judge's verdict. Rows already on the sheet, and their labels, never change."""
    rows = list(csv.DictReader(SHEET.open())) if SHEET.exists() else []
    key = json.loads(KEY.read_text()) if KEY.exists() else {}
    taken = {entry["key"] for entry in key.values()}
    groups, rng, chosen = defaultdict(list), random.Random(4016 + len(rows)), []
    for item in items:
        if item["key"] not in taken:
            groups[item["source"]].append(item)
    for group in groups.values():
        rng.shuffle(group)
    while len(rows) + len(chosen) < 30 and any(groups.values()):
        for group in groups.values():
            if group and len(rows) + len(chosen) < 30:
                chosen.append(group.pop())
    rng.shuffle(chosen)
    for number, item in enumerate(chosen, len(rows) + 1):
        job = item["job"]
        rows.append({"item": str(number), "job_title": job["title"], "job_post": job["description"],
                     "screening_questions": "\n".join(job["screening_questions"]), "proposal": item["text"],
                     "screening_answers": "\n\n".join(f"{q}\n{a}" for q, a in item["answers"].items()),
                     "label": "", "notes": ""})
        key[str(number)] = {"key": item["key"], "source": item["source"], "job": job["id"]}
    LABELS.mkdir(parents=True, exist_ok=True)
    with SHEET.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item", "job_title", "job_post", "screening_questions",
                                                    "proposal", "screening_answers", "label", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    KEY.write_text(json.dumps(key, indent=1) + "\n")
    print(f"{SHEET.relative_to(ROOT)} holds {len(rows)} of 30 items; label each good, acceptable or poor.")


def agreement(labels, verdicts, key):
    """Cohen's kappa between one rater's labels (item -> label) and the judge's overall labels."""
    pairs = [(label, verdicts.get(key[item]["key"], {}).get("overall")) for item, label in labels.items()]
    pairs = [(rater, judged) for rater, judged in pairs if rater in {"good", "acceptable", "poor"} and judged]
    if len(pairs) < 30:
        return {"status": "pending", "reason": f"{len(pairs)} of 30 items carry a label and a verdict"}
    return {"status": "measured", "items": len(pairs), "cohen_kappa": kappa(pairs),
            "agreement": round(mean(r == j for r, j in pairs), 3), "pairs": Counter(f"{r}/{j}" for r, j in pairs)}


def calibration(verdicts):
    """Human labels from the blind sheet against the judge's verdicts."""
    if not SHEET.exists():
        return {"human": {"status": "pending", "reason": "no labelling sheet yet; run with --sheet"}}
    labels = {r["item"]: r["label"].strip().lower() for r in csv.DictReader(SHEET.open())}
    return {"human": agreement(labels, verdicts, json.loads(KEY.read_text()))}


def shown(item):
    answers = "\n\n".join(f"{q}\n{a}" for q, a in item["answers"].items())
    return item["text"] + (f"\n\nScreening answers:\n{answers}" if answers else "")


def panel(items):
    """Up to 20 blind pairs: two runs' proposals for the same job, sides shuffled, for classmates to compare."""
    if PANEL.exists():
        return print(f"{PANEL.relative_to(ROOT)} exists; it may hold ratings, so it is not overwritten.")
    by_job, rng = defaultdict(dict), random.Random(4016)
    for item in items:
        by_job[item["job"]["id"]].setdefault(item["source"], item)
    pairs = [tuple(rng.sample([runs[a], runs[b]], 2)) for _, runs in sorted(by_job.items())
             for a, b in combinations(sorted(runs), 2)]
    rng.shuffle(pairs)
    LABELS.mkdir(parents=True, exist_ok=True)
    with PANEL.open("w", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(["pair", "job_title", "job_post", "proposal_a", "proposal_b", "rater_1", "rater_2", "rater_3"])
        for number, (a, b) in enumerate(pairs[:20], 1):
            out.writerow([number, a["job"]["title"], a["job"]["description"], shown(a), shown(b), "", "", ""])
    PANEL_KEY.write_text(json.dumps({n: {"a": a["source"], "b": b["source"], "job": a["job"]["id"]}
                                     for n, (a, b) in enumerate(pairs[:20], 1)}, indent=1) + "\n")
    print(f"Wrote {min(20, len(pairs))} pairs to {PANEL.relative_to(ROOT)}; raters write A, B or tie.")


def panel_results():
    if not PANEL.exists():
        return {"status": "pending", "reason": "No panel sheet yet; run with --panel"}
    key, tally = json.loads(PANEL_KEY.read_text()), defaultdict(Counter)
    for row in csv.DictReader(PANEL.open()):
        pair = key[row["pair"]]
        for vote in (row[f"rater_{n}"].strip().lower() for n in (1, 2, 3)):
            if vote in {"a", "b"}:
                tally[pair[vote]]["won"] += 1
                tally[pair["b" if vote == "a" else "a"]]["lost"] += 1
            elif vote == "tie":
                tally[pair["a"]]["tied"] += 1
                tally[pair["b"]]["tied"] += 1
    if not tally:
        return {"status": "pending", "reason": "No ratings in the panel sheet yet"}
    return {"status": "measured", "runs": {run: {**counts, "win_rate": round(counts["won"] / (counts["won"] + counts["lost"]), 3)
                                                 if counts["won"] + counts["lost"] else None} for run, counts in tally.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", action="store_true", help="Write the blind 30-item human labelling sheet")
    parser.add_argument("--panel", action="store_true", help="Write the blind pairwise sheet for classmates")
    args = parser.parse_args()
    model = config()["evaluation"]["judge"]["model"]
    path = RESULTS / f"judge-{model.split('/')[-1]}.jsonl"
    verdicts = {r["key"]: r for r in map(json.loads, path.read_text().splitlines())} if path.exists() else {}
    items = proposals()
    for item in items:
        if item["key"] in verdicts:
            continue
        result = verdict(item)
        if result is None:
            print("Daily judge quota reached; run again later to resume.")
            break
        verdicts[item["key"]] = row = {"key": item["key"], "source": item["source"], "job": item["job"]["id"], **result}
        with path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        print(f"{item['source']:<34} {item['job']['id']:<8} {row.get('overall', 'invalid')}", flush=True)
        time.sleep(2)
    if args.sheet:
        sheet([item for item in items if "overall" in verdicts.get(item["key"], {})])
    if args.panel:
        panel(items)
    scored = defaultdict(list)
    for item in items:
        if "overall" in verdicts.get(item["key"], {}):
            scored[item["source"]].append(verdicts[item["key"]])
    report = {"judge_model": model, "rows_file": path.name, "prompt_version": config()["prompts"]["judge"],
              "sources": {source: {"proposals": len(rows), "score": round(mean(mean(r[c] for c in CRITERIA) for r in rows), 2),
                                   "labels": Counter(r["overall"] for r in rows)} for source, rows in sorted(scored.items())},
              "invalid_verdicts": sum("invalid" in v for v in verdicts.values()), "calibration": calibration(verdicts),
              "panel": panel_results()}
    print(json.dumps(report["sources"], indent=1), report["calibration"], f"\nResults: {write('judge', report).name}")


if __name__ == "__main__":
    main()
