"""Bid decisions, grounding, cost and speed of the hand-built bid graph on the labelled dev set.

Real hosted models: each job runs once, nothing is approved or sent. Every job is decided and priced; only the
proposal subset (one job of each drafting type per persona) is written up to the approval interrupt, which keeps a
full run inside the free tier's daily tokens. One line per job is appended to a JSONL file, so a run stopped by
provider quotas resumes where it stopped.
Usage: python -m evals.runners.decisions [--profile open] [--variant V2+V3] [--subset proposals] [--jobs aiml-01,fs-02]
"""
import argparse
import asyncio
import json
import os
import time

from evals.runners.common import RESULTS, isolate, tenant, write

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--profile", default="open", help="Model profile from agent/config.yaml")
parser.add_argument("--subset", choices=["all", "proposals"], default="all",
                    help="all: decide every job, draft the proposal subset; proposals: only the proposal subset")
parser.add_argument("--jobs", default="", help="Comma-separated job ids instead of a subset")
parser.add_argument("--variant", default="", help="Retrieval pipeline; default the configured one")
parser.add_argument("--pause", type=float, default=5, help="Seconds between jobs, under per-minute token limits")
parser.add_argument("--tag", default="", help="Names a fix experiment, whose results stay apart from the main run")
parser.add_argument("--decide-only", action="store_true", help="Stop every job where the writer would start")
ARGS = parser.parse_args()
os.environ.update(MODEL_PROFILE=ARGS.profile, RETRIEVAL_VARIANT=ARGS.variant)
LABEL = "-".join(part for part in (ARGS.profile, ARGS.variant, ARGS.tag) if part)
isolate(f"decisions-{LABEL}")

from agent.model import OpenModel, config, profile  # noqa: E402
from evals.dataset import fingerprint, load  # noqa: E402
from evals.metrics import decisions, grouped  # noqa: E402
from worker.runtime import process_run  # noqa: E402

DRAFTED = ("multi_requirement", "exact_tool", "implied_skill", "injection")
FRAUD = {"scam", "off_platform", "free_work"}


class StopBeforeWriting(Exception):
    pass


class DecisionsOnly:
    """The configured models, except that a run ends where the writer would start."""

    def __init__(self, model):
        self.model = model

    async def complete(self, node, data, schema):
        if node == "writer":
            raise StopBeforeWriting("decision-only evaluation run")
        return await self.model.complete(node, data, schema)


def drafted(persona):
    return [next(job for job in persona["jobs"] if job["job_type"] == kind) for kind in DRAFTED]


def selected(persona):
    if ARGS.jobs:
        return [job for job in persona["jobs"] if job["id"] in ARGS.jobs.split(",")]
    return drafted(persona) if ARGS.subset == "proposals" else persona["jobs"]


def row(persona, job, run):
    state = run["state"]
    gold, decision, risk = job["gold"], state.get("decision") or {}, state.get("risk") or {}
    draft, price, checked = state.get("draft") or {}, state.get("price") or {}, state.get("verification") or {}
    band, budget = gold.get("price_band"), state.get("budget") or {}
    sent = draft.get("text", "") + "\n" + "\n".join((draft.get("screening_answers") or {}).values())
    stopped = "decision-only evaluation run" in str(state.get("error"))
    return {"job": job["id"], "persona": persona, "job_type": job["job_type"],
            "gold": {"bid": gold["bid"], "scam": gold["scam"], "price_band": band},
            "status": "decided" if stopped else run["status"], "action": decision.get("action"), "reason": decision.get("reason"),
            "risk": risk.get("score"), "flags": risk.get("flags", []),
            # A scam call is a skip that names a fraud signal; a skip for a low budget alone is not one.
            "predicted_scam": decision.get("action") != "bid" and bool(set(risk.get("flags", [])) & FRAUD),
            "fit": (state.get("fit") or {}).get("score"), "price": price.get("amount"),
            "in_band": band[0] <= price["amount"] <= band[1] if band and price else None,
            "unsupported_before": checked.get("unsupported_before"), "unsupported_after": checked.get("unsupported_after"),
            "revisions": state.get("revision"), "compliance": state.get("compliance"),
            "canary_leaked": job["canary"] in sent if job.get("canary") and draft else None,
            "tokens": budget.get("tokens"), "api_usd": budget.get("api_usd"),
            "models": sorted({u["model"] for u in state.get("usage", [])}), "error": None if stopped else state.get("error"),
            "draft": draft.get("text"), "screening_answers": draft.get("screening_answers"),
            "evidence": [item["source"] for item in (state.get("fit") or {}).get("evidence", [])]}


async def main():
    path = RESULTS / f"decisions-{LABEL}-{fingerprint()[:8]}.jsonl"
    done = {json.loads(line)["job"] for line in path.read_text().splitlines()} if path.exists() else set()
    limited = 0
    for persona in load():
        todo = [job for job in selected(persona) if job["id"] not in done]
        if not todo or limited >= 3:
            continue
        client, _ = tenant(persona)
        writing = set() if ARGS.decide_only else {job["id"] for job in selected(persona)} if (
            ARGS.jobs or ARGS.subset == "proposals") else {job["id"] for job in drafted(persona)}
        for job in todo:
            start = time.monotonic()
            try:
                run_id = client.post(f"/jobs/{job['id']}/analyse").json()["id"]
                await process_run(run_id, model=None if job["id"] in writing else DecisionsOnly(OpenModel()))
                result = row(persona["persona"], job, client.get(f"/runs/{run_id}").json())
            except Exception as exc:
                result = row(persona["persona"], job, {"status": "harness_error",
                                                       "state": {"error": f"{type(exc).__name__}: {exc}"}})
            result["wall_seconds"] = round(time.monotonic() - start, 1)
            # Quota failures are not results: stop after three in a row and resume later.
            limited = limited + 1 if any(word in str(result.get("error")).lower() for word in ("rate limit", "ratelimited")) else 0
            if limited:
                print(f"{job['id']:<9} rate limited: {result['error']}", flush=True)
                if limited >= 3:
                    break
                continue
            with path.open("a") as handle:
                handle.write(json.dumps(result) + "\n")
            print(f"{job['id']:<9} {result.get('status', '-'):<17} {str(result.get('action')):<6} "
                  f"gold {'bid' if job['gold']['bid'] else 'skip':<5} tokens {result.get('tokens')} "
                  f"{result['wall_seconds']} s {result.get('error') or ''}", flush=True)
            await asyncio.sleep(ARGS.pause)
    wanted = {job["id"] for persona in load() for job in selected(persona)}
    lines = path.read_text().splitlines() if path.exists() else []
    rows = [r for r in map(json.loads, lines) if r["job"] in wanted]
    report = {"profile": ARGS.profile, "nodes": profile()["nodes"], "rows_file": path.name,
              "retrieval_variant": ARGS.variant or config()["retrieval"]["variant"],
              "selection": ARGS.jobs or ARGS.subset, "jobs_wanted": len(wanted), "overall": decisions(rows),
              "by_persona": grouped(rows, "persona"), "by_job_type": grouped(rows, "job_type")}
    print(f"{len(rows)}/{len(wanted)} jobs. Results: {write(f'decisions-{LABEL}', report).name}")


if __name__ == "__main__":
    asyncio.run(main())
