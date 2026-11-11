"""R&D B: retrieval variants, combined pipelines and ablation of the best one on the labelled dev set.

No LLM calls: dense retrieval uses the local embedding model and V3 the local cross-encoder.
Usage: python -m evals.runners.retrieval
"""
import math
import time
from collections import defaultdict
from statistics import mean

from evals.runners.common import isolate, tenant, write

isolate("retrieval")

from agent.model import config  # noqa: E402
from evals.dataset import load  # noqa: E402
from evals.metrics import spread  # noqa: E402
from rag.retriever import retrieve  # noqa: E402

SINGLE = ["V0", "BM25", "V1", "V2", "V3", "V4", "V8"]
COMBINED = ["V1+V2", "V1+V3", "V2+V3", "V1+V2+V3", "V1+V2+V3+V4", "V1+V2+V3+V8"]
METRICS = ("recall5", "mrr", "ndcg10")
SEVERAL = {"multi_requirement", "exact_tool"}


def post(job):
    return f"{job['title']}\n{job['description']}\nSkills: {', '.join(job['skills'])}"


def requirements(job):
    """What decomposition retrieves for, one line each: the title, the skill tags and the deliverables."""
    return "\n".join([job["title"], *job["skills"], *job["deliverables"]])


def gain(grades):
    return sum((2 ** grade - 1) / math.log2(position + 2) for position, grade in enumerate(grades))


def score(ranking, gold):
    sources = list(dict.fromkeys(item["source"] for item in ranking))
    grades = [gold.get(source, 0) for source in sources[:10]]
    first = next((position for position, grade in enumerate(grades) if grade), None)
    return {"recall5": len(set(sources[:5]) & set(gold)) / len(gold),
            "mrr": 1 / (first + 1) if first is not None else 0.0,
            "ndcg10": gain(grades) / gain(sorted(gold.values(), reverse=True)[:10]), "top5": sources[:5]}


def evaluate(personas, pipeline):
    rows = []
    for persona, user in personas:
        for job in persona["jobs"]:
            query = requirements(job) if "V1" in pipeline.split("+") else post(job)
            start = time.perf_counter()
            ranking = retrieve(user, query, k=10, variant=pipeline)
            row = {"job": job["id"], "persona": persona["persona"], "job_type": job["job_type"],
                   "ms": round((time.perf_counter() - start) * 1000), "returned": len(ranking)}
            gold = job["gold"]["evidence"]
            rows.append({**row, **score(ranking, gold)} if gold else row)
    return rows


def summary(rows):
    graded, empty = [r for r in rows if "ndcg10" in r], [r for r in rows if "ndcg10" not in r]
    latency = spread([r["ms"] for r in rows])
    # Out-of-scope jobs have no gold evidence, so their group measures refusals only.
    return {**{metric: round(mean(r[metric] for r in graded), 3) if graded else None for metric in METRICS},
            "jobs": len(graded),
            "refused_when_nothing_fits": round(mean(r["returned"] == 0 for r in empty), 3) if empty else None,
            "refused_when_evidence_exists": round(mean(r["returned"] == 0 for r in graded), 3) if graded else None,
            "p50_ms": latency["p50"], "p95_ms": latency["p95"]}


def by(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return {name: summary(group) for name, group in sorted(groups.items())}


def fit(user, job, pipeline):
    """The Fit Matcher's rule (share of skill tags with retrieved evidence carrying that tag), plus gold
    evidence it retrieved but cannot count because the tag is missing."""
    supported, untagged = 0, set()
    for skill in job["skills"]:
        hits = retrieve(user, skill, k=5, variant=pipeline)
        tagged = [h for h in hits if skill.casefold() in {s.casefold() for s in h["skills"]}]
        supported += bool(tagged)
        untagged |= {h["source"] for h in hits if h not in tagged and h["source"] in job["gold"]["evidence"]}
    return round(supported / len(job["skills"]), 2), sorted(untagged)


def impact(personas, pipeline):
    """Whether better retrieval changes the evidence gate before any model runs (fit below min_fit skips)."""
    floor, rows = config()["thresholds"]["min_fit"], []
    for persona, user in personas:
        for job in persona["jobs"]:
            (before, _), (after, untagged) = fit(user, job, "V0"), fit(user, job, pipeline)
            rows.append({"job": job["id"], "job_type": job["job_type"], "gold_bid": job["gold"]["bid"],
                         "fit_v0": before, "fit": after, "passes_v0": before >= floor, "passes": after >= floor,
                         "untagged_gold_retrieved": untagged})
    changed = [r for r in rows if r["passes_v0"] != r["passes"]]
    return {"pipeline": pipeline, "min_fit": floor, "gate_changes": len(changed),
            "implied_skill_gate_changes": sum(r["job_type"] == "implied_skill" for r in changed),
            "bid_jobs_passing": {"V0": sum(r["passes_v0"] for r in rows if r["gold_bid"]),
                                 pipeline: sum(r["passes"] for r in rows if r["gold_bid"]),
                                 "of": sum(r["gold_bid"] for r in rows)},
            "jobs_with_untagged_gold_retrieved": sum(bool(r["untagged_gold_retrieved"]) for r in rows), "per_job": rows}


def recall(rows, types):
    return round(mean(r["recall5"] for r in rows if r["job_type"] in types and "recall5" in r), 3)


def main():
    personas = [(persona, tenant(persona)[1]) for persona in load()]
    runs = {}

    def run(pipeline):
        if pipeline not in runs:
            runs[pipeline] = evaluate(personas, pipeline)
            print(f"{pipeline:<16} {summary(runs[pipeline])}", flush=True)
        return runs[pipeline]

    for pipeline in SINGLE + COMBINED:
        run(pipeline)
    overall = {name: summary(rows) for name, rows in runs.items()}
    best = max(overall, key=lambda name: (overall[name]["ndcg10"], overall[name]["recall5"]))
    parts = best.split("+")
    ablation = []
    for part in [p for p in parts if p != "V0"]:
        reduced = "+".join(p for p in parts if p != part) or "V0"
        result = summary(run(reduced))
        ablation.append({"removed": part, "pipeline": reduced, **result,
                         "ndcg10_change": round(result["ndcg10"] - overall[best]["ndcg10"], 3)})
    overall = {name: summary(rows) for name, rows in runs.items()}
    several = {name: recall(run(name), SEVERAL) for name in ("V0", "V1+V2+V3")}
    implied = {name: recall(run(name), {"implied_skill"}) for name in ("V1+V3", "V1+V2+V3")}
    outcome = {name: overall[name]["recall5"] for name in ("V0", "V4")}
    checks = [
        {"claim": "V1+V2+V3 raises Recall@5 by at least 10 points over V0 on multi_requirement and exact_tool jobs",
         "recall5": several, "supported": several["V1+V2+V3"] - several["V0"] >= 0.10},
        {"claim": "On implied_skill jobs V1+V3 scores at least as well as V1+V2+V3",
         "recall5": implied, "supported": implied["V1+V3"] >= implied["V1+V2+V3"]},
        {"claim": "V4 moves Recall@5 by less than 2 points", "recall5": outcome,
         "supported": abs(outcome["V4"] - outcome["V0"]) < 0.02},
    ]
    # The Fit Matcher already retrieves once per skill tag, so the gate check runs the best pipeline without V1.
    gate = impact(personas, "+".join(p for p in parts if p != "V1") or "V0")
    checks.append({"claim": "Better retrieval does not change bid or skip decisions on implied_skill jobs",
                   "implied_skill_gate_changes": gate["implied_skill_gate_changes"],
                   "supported": gate["implied_skill_gate_changes"] == 0})
    retrieval = config()["retrieval"]
    path = write("retrieval", {
        "setup": {"embedding_model": retrieval["embedding_model"], "reranker": retrieval["reranker"], "k": 10,
                  "queries": {"with V1": "title, skill tags and deliverables, one retrieval each, merged",
                              "others": "the whole post: title, description and skill tags"}},
        "pipelines": overall, "best": best, "ablation": ablation, "hypothesis_checks": checks, "decision_gate": gate,
        "by_persona": {name: by(rows, "persona") for name, rows in runs.items()},
        "by_job_type": {name: by(rows, "job_type") for name, rows in runs.items()}, "per_job": runs})
    print(f"Best: {best}. Results: {path.relative_to(path.parents[2])}")


if __name__ == "__main__":
    main()
