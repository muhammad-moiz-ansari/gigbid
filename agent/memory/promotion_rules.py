import re


def style_candidates(edits):
    """Promote only a repeated exact phrase removal across five distinct edited runs."""
    distinct = {e["run_id"]: e for e in edits if "before" in e and "after" in e}
    if len(distinct) < 5:
        return []
    observations = list(distinct.values())[-5:]
    removed = []
    for edit in observations:
        before, after = set(re.findall(r"\b\w+\b", edit["before"].lower())), set(re.findall(r"\b\w+\b", edit["after"].lower()))
        removed.append(before - after)
    common = set.intersection(*removed)
    return [{"kind": "style", "rule": "Avoid this repeatedly removed word", "word": word,
             "supporting_runs": sorted(e["run_id"] for e in observations),
             "promotion_rule": "same-word-removed-in-five-distinct-approved-edits-v1"}
            for word in sorted(common) if len(word) > 3 and word not in
            {"about", "this", "that", "with", "from", "have", "would", "could", "should", "your"}]


def outcome_candidate(observations):
    distinct = {o["event_id"]: o for o in observations}
    if len(distinct) < 3:
        return None
    rows = list(distinct.values())
    categories = {o["category"] for o in rows}
    if len(categories) != 1:
        return None
    return {"kind": "outcome", "category": rows[0]["category"],
            "observed_statuses": [o["status"] for o in rows],
            "supporting_events": sorted(distinct),
            "promotion_rule": "three-recorded-category-outcomes-v1",
            "interpretation": "Descriptive observations, not a causal success claim"}
