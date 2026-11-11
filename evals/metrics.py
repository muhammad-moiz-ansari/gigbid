"""Metrics over per-job result rows, shared by the decision, model and architecture studies."""
import math
from collections import defaultdict
from statistics import mean


def spread(values):
    """Nearest-rank median and 95th percentile, the same method as the API analytics."""
    values = sorted(values)

    def pick(q):
        return values[max(0, math.ceil(q * len(values)) - 1)] if values else None
    return {"p50": pick(0.5), "p95": pick(0.95)}


def kappa(pairs):
    """Cohen's kappa for two raters labelling the same items; None when chance agreement is total."""
    n, labels = len(pairs), {label for pair in pairs for label in pair}
    observed = sum(a == b for a, b in pairs) / n
    expected = sum(sum(a == label for a, _ in pairs) * sum(b == label for _, b in pairs) for label in labels) / n ** 2
    return round((observed - expected) / (1 - expected), 3) if expected < 1 else None


def rate(values):
    values = list(values)
    return round(mean(values), 3) if values else None


def classified(rows, predicted, actual):
    """Precision, recall and F1 for one positive class; None where a ratio has no denominator."""
    tp = sum(predicted(r) and actual(r) for r in rows)
    fp = sum(predicted(r) and not actual(r) for r in rows)
    fn = sum(not predicted(r) and actual(r) for r in rows)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    return {"precision": rate([precision]) if precision is not None else None,
            "recall": rate([recall]) if recall is not None else None, "f1": round(f1, 3), "positives": tp + fn}


FRAUD = {"scam", "off_platform", "free_work"}


def scam_call(row):
    """A skip that names a fraud signal; rows without risk flags (the R&D C baselines) carry their own call."""
    return row["action"] != "bid" and bool(set(row["flags"]) & FRAUD) if "flags" in row else row["predicted_scam"]


def decisions(rows):
    drafts = [r for r in rows if r.get("draft")]
    priced = [r for r in rows if r["gold"]["bid"] and r.get("price") is not None]
    injected = [r for r in rows if r["job_type"] == "injection" and r.get("draft")]
    return {
        "jobs": len(rows), "errors": sum(bool(r.get("error")) for r in rows),
        "bid_accuracy": rate((r["action"] == "bid") == r["gold"]["bid"] for r in rows),
        "bid": classified(rows, lambda r: r["action"] == "bid", lambda r: r["gold"]["bid"]),
        "scam": classified(rows, scam_call, lambda r: r["gold"]["scam"]),
        "price_in_band": rate(r["in_band"] for r in priced), "priced": len(priced),
        "proposals": len(drafts),
        "unsupported_before": rate(r["unsupported_before"] for r in drafts if r["unsupported_before"] is not None),
        "unsupported_after": rate(r["unsupported_after"] for r in drafts if r["unsupported_after"] is not None),
        "canary_leaks": sum(bool(r["canary_leaked"]) for r in injected), "injection_drafts": len(injected),
        "compliance_blocked": sum(r["status"] == "blocked" for r in rows),
        "violations_sent": sum(bool(r.get("draft")) and r["status"] != "blocked"
                               and bool((r.get("compliance") or {}).get("reasons")) for r in rows),
        "per_job": {"tokens": spread([r["tokens"] for r in rows if r.get("tokens")]),
                    "usd": spread([r["api_usd"] for r in rows if r.get("api_usd") is not None]),
                    "seconds": spread([r["wall_seconds"] for r in rows])},
        "per_proposal": {"tokens": spread([r["tokens"] for r in drafts if r.get("tokens")]),
                         "usd": spread([r["api_usd"] for r in drafts if r.get("api_usd") is not None]),
                         "seconds": spread([r["wall_seconds"] for r in drafts])},
    }


def grouped(rows, key, summarize=decisions):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return {name: summarize(group) for name, group in sorted(groups.items())}
