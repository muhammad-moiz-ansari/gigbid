"""Regenerates every results table from the newest results file of each study, into evals/results/TABLES.md and
the README's results block. Each table names the files its numbers come from; missing studies show as pending.
Usage: python -m evals.tables
"""
import hashlib
import json
from statistics import mean

from evals.metrics import decisions
from evals.runners.common import RESULTS, ROOT

START, END = "<!-- results:start -->", "<!-- results:end -->"
CRITERIA = ("relevance", "evidence", "specificity", "clarity", "screening")
GIGSIM = "pending (GigSim not released)"


def summaries(prefix):
    """Summaries named prefix plus a timestamp, oldest first, so 'decisions-open' never matches 'decisions-open_small'."""
    return [(path.name, json.loads(path.read_text())) for path in sorted(RESULTS.glob(f"{prefix}-2*.json"))]


def latest(prefix, accept=lambda data: True):
    return next(((name, data) for name, data in reversed(summaries(prefix)) if accept(data)), (None, None))


def rows(name):
    path = RESULTS / name
    return list(map(json.loads, path.read_text().splitlines())) if path.exists() else []


def fmt(value, digits=2):
    if value is None:
        return "–"
    if isinstance(value, float) and 0 < abs(value) < 0.1:
        return f"{value:.4f}"  # API costs are fractions of a cent
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def table(header, body, sources):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(fmt(cell) for cell in line) + " |" for line in body]
    return lines + ["", "Source: " + ", ".join(f"`evals/results/{s}`" for s in sources if s) + "", ""]


def judged(rows_file):
    """Judge scores for one run's drafts, matched by job and text, so a renamed results file keeps its verdicts."""
    verdicts = {v["key"]: v for path in RESULTS.glob("judge-*.jsonl") for v in rows(path.name) if "overall" in v}
    found = {}
    for row in rows(rows_file):
        key = hashlib.sha256(f"{row['job']}\n{row['draft']}".encode()).hexdigest()[:16] if row.get("draft") else None
        if key in verdicts:
            found[row["job"]] = mean(verdicts[key][c] for c in CRITERIA)
    return found


def drafted(summary):
    return {r["job"] for r in rows(summary["rows_file"]) if r.get("draft")} if summary else set()


def run_metrics(summary, jobs=None):
    """Decision metrics over a run's per-job rows, optionally restricted to a common job set, with judge scores."""
    selected = [r for r in rows(summary["rows_file"]) if jobs is None or r["job"] in jobs]
    scores = [score for job, score in judged(summary["rows_file"]).items() if jobs is None or job in jobs]
    return decisions(selected), (round(mean(scores), 2) if scores else None)


def retrieval_tables(out):
    name, data = latest("retrieval")
    if not data:
        return out.append("Retrieval study: pending.\n")
    order = sorted(data["pipelines"], key=lambda p: -data["pipelines"][p]["ndcg10"])
    out += ["### Retrieval variants and pipelines", ""] + table(
        ["Pipeline", "Recall@5", "MRR", "nDCG@10", "Refused when nothing fits", "Refused with evidence", "p95 ms"],
        [[p, *(data["pipelines"][p][k] for k in ("recall5", "mrr", "ndcg10", "refused_when_nothing_fits",
                                                  "refused_when_evidence_exists", "p95_ms"))] for p in order], [name])
    out += [f"### Ablation of the best pipeline ({data['best']})", ""] + table(
        ["Removed", "Pipeline", "Recall@5", "nDCG@10", "nDCG@10 change"],
        [[a["removed"], a["pipeline"], a["recall5"], a["ndcg10"], a["ndcg10_change"]] for a in data["ablation"]], [name])
    for key, title in (("by_persona", "persona"), ("by_job_type", "job type")):
        groups = sorted(data[key]["V0"])
        out += [f"### Recall@5 and nDCG@10 by {title}: V0 against {data['best']}", ""] + table(
            [title.capitalize(), "Jobs", "V0 Recall@5", "Best Recall@5", "V0 nDCG@10", "Best nDCG@10"],
            [[g, data[key]["V0"][g]["jobs"], data[key]["V0"][g]["recall5"], data[key][data["best"]][g]["recall5"],
              data[key]["V0"][g]["ndcg10"], data[key][data["best"]][g]["ndcg10"]] for g in groups], [name])
    gate = data["decision_gate"]
    out += ["### Hypotheses (recorded before the runs)", ""] + table(
        ["Claim", "Supported"], [[c["claim"], "yes" if c["supported"] else "no"] for c in data["hypothesis_checks"]], [name])
    out += [f"Evidence gate with {gate['pipeline']} instead of V0: {gate['gate_changes']} of "
            f"{len(gate['per_job'])} jobs change; gold bid jobs passing {gate['bid_jobs_passing']}; "
            f"{gate['jobs_with_untagged_gold_retrieved']} jobs had gold evidence retrieved but not counted "
            "because its skill tags lack the requirement.", ""]


def headline(out):
    """The PDF's results table: V0 against the best pipeline on the same proposal jobs."""
    retrieval_name, retrieval = latest("retrieval")
    if not retrieval:
        return
    best = retrieval["best"]
    shipped = "+".join(part for part in best.split("+") if part != "V1") or "V0"  # the Fit Matcher decomposes already
    base_name, base = latest("decisions-open", lambda d: d.get("retrieval_variant") == "V0" and d["overall"]["proposals"])
    best_name, tuned = latest("decisions-open", lambda d: d.get("retrieval_variant") == shipped and d["overall"]["proposals"])
    body = []
    jobs = drafted(base) & drafted(tuned) if tuned else drafted(base)
    for label, pipeline, run in (("V0", "V0", base), (f"Best ({best})", best, tuned)):
        scores = retrieval["pipelines"][pipeline]
        metrics, judge = run_metrics(run, jobs) if run else ({}, None)
        proposal = metrics.get("per_proposal", {})
        body.append([label, scores["recall5"], scores["ndcg10"],
                     f"{fmt(metrics.get('unsupported_before'))} → {fmt(metrics.get('unsupported_after'))}" if run else "–",
                     judge, GIGSIM, (proposal.get("seconds") or {}).get("p95"), (proposal.get("usd") or {}).get("p50")])
    out += ["### Results table", ""] + table(
        ["Variant", "Evidence Recall@5", "nDCG@10", "Unsupported claims per proposal (before → after)", "Judge score (1-5)",
         "GigSim reply rate", "p95 latency (s)", "Median cost per proposal (USD)"], body,
        [retrieval_name, base_name, best_name])
    scope = "drafted in both runs" if tuned else "drafted in the V0 run; the best row waits for its run"
    out += [f"Proposal columns cover the {len(jobs)} jobs {scope}. The V0 run came first, before the prompt fixes in "
            "the failure taxonomy; the best row uses the shipped configuration, so it also carries those fixes.", ""]


def decision_tables(out):
    small_name, small = latest("decisions-open_small")
    base_name, base = latest("decisions-open", lambda d: d["overall"]["jobs"] == d["jobs_wanted"] > 12)
    if not base:
        return out.append("Decision study: pending.\n")
    full, judge = run_metrics(base)
    out += ["### Decisions on every dev job (hand-built graph, production profile)", ""] + table(
        ["Jobs", "Errors", "Bid accuracy", "Bid F1", "Scam precision", "Scam recall", "Price in band",
         "Unsupported before → after", "Canary leaks", "Blocked by compliance", "Judge score", "p95 s per job",
         "Median USD per job"],
        [[full["jobs"], full["errors"], full["bid_accuracy"], full["bid"]["f1"], full["scam"]["precision"],
          full["scam"]["recall"], full["price_in_band"],
          f"{fmt(full['unsupported_before'])} → {fmt(full['unsupported_after'])}",
          f"{full['canary_leaks']}/{full['injection_drafts']}", full["compliance_blocked"], judge,
          full["per_job"]["seconds"]["p95"], full["per_job"]["usd"]["p50"]]], [base_name])
    if small:
        jobs = {r["job"] for r in rows(small["rows_file"])}
        body = []
        for label, run in (("gpt-oss-20b small nodes, gpt-oss-120b writer and critic", base),
                           ("gpt-oss-20b everywhere", small)):
            metrics, score = run_metrics(run, jobs)
            proposal = metrics["per_proposal"]
            body.append([label, metrics["proposals"], score,
                         f"{fmt(metrics['unsupported_before'])} → {fmt(metrics['unsupported_after'])}",
                         metrics["price_in_band"], proposal["tokens"]["p50"], proposal["seconds"]["p50"],
                         proposal["seconds"]["p95"], proposal["usd"]["p50"]])
        out += [f"### Model configurations on the same {len(jobs)} proposal jobs", ""] + table(
            ["Configuration", "Proposals", "Judge score", "Unsupported before → after", "Price in band",
             "Median tokens", "Median s", "p95 s", "Median USD"], body, [base_name, small_name])
    else:
        out += ["Model comparison: not run yet; the deployed profile (gpt-oss-20b small nodes, gpt-oss-120b writer and "
                "critic) is used throughout.", ""]


def architecture_tables(out):
    base_name, base = latest("decisions-open", lambda d: d["overall"]["jobs"] == d["jobs_wanted"] > 12)
    designs = {d: latest(f"architecture-{d}") for d in ("react", "supervisor")}
    if not base or not any(data for _, data in designs.values()):
        return out.append("Architecture study: pending.\n")
    jobs = set(next(data for _, data in designs.values() if data)["jobs_wanted"])
    body = []
    for label, run in (("Hand-built graph", base), ("One ReAct agent", designs["react"][1]),
                       ("Prebuilt supervisor", designs["supervisor"][1])):
        if not run:
            body.append([label] + ["pending"] * 9)
            continue
        metrics, score = run_metrics(run, jobs)
        writes = sum(r.get("write_attempts", 0) for r in rows(run["rows_file"]) if r["job"] in jobs)
        body.append([label, metrics["jobs"], metrics["bid_accuracy"], metrics["scam"]["recall"],
                     metrics["unsupported_after"], metrics["violations_sent"], metrics["compliance_blocked"],
                     f"{metrics['canary_leaks']}/{metrics['injection_drafts']}", writes,
                     metrics["per_job"]["tokens"]["p50"]])
    out += [f"### Architectures on the same {len(jobs)} jobs", ""] + table(
        ["Design", "Jobs", "Bid accuracy", "Scam recall", "Unsupported claims sent per proposal",
         "Violations sent", "Violations blocked", "Canary leaks", "Write attempts", "Median tokens per job"], body,
        [base_name, designs["react"][0], designs["supervisor"][0]])


def tool_tables(out):
    name, data = latest("tools")
    if not data:
        return out.append("Tool granularity study: pending.\n")
    out += [f"### Tool granularity on {data['tasks']} tasks ({data['model']})", ""] + table(
        ["Tool set", "Tasks run", "Tool selection accuracy", "Argument accuracy", "Tokens per task"],
        [[kind, s["tasks"], s["tool_selection_accuracy"], s["argument_accuracy"], s["tokens_per_task"]]
         for kind, s in data["sets"].items()], [name])


def judge_tables(out):
    name, data = latest("judge")
    if not data:
        return out.append("Judge calibration: pending.\n")
    calibration = data["calibration"]

    def line(result):
        return (f"Cohen's kappa {result['cohen_kappa']} on {result['items']} items (agreement {result['agreement']})"
                if result["status"] == "measured" else f"pending ({result['reason']})")
    out += [f"Judge ({data['judge_model']}, prompt {data['prompt_version']}) against human labels: "
            f"{line(calibration.get('human', calibration))}. Source: `evals/results/{name}`.", ""]


def main():
    out = ["Generated by `python -m evals.tables` from the newest results files. The dev set is synthetic and "
           "suitable for harness validation only; official conclusions wait for the official dev set and GigSim.", ""]
    for section in (headline, retrieval_tables, decision_tables, architecture_tables, tool_tables, judge_tables):
        section(out)
    text = "\n".join(out).rstrip() + "\n"
    (RESULTS / "TABLES.md").write_text("# Evaluation results\n\n" + text)
    readme = ROOT / "README.md"
    content = readme.read_text()
    if START in content and END in content:
        head, rest = content.split(START, 1)
        readme.write_text(head + START + "\n" + text + END + rest.split(END, 1)[1])
    print(text)


if __name__ == "__main__":
    main()
