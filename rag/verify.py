import re

from apps.api.safety import risks

QUOTE = re.compile(r'^Portfolio evidence: "(.+)" \[([a-zA-Z0-9_-]+)\]$', re.S)
HISTORY = re.compile(r"\b(?:built|delivered|achieved|worked|implemented|created|led|increased|"
                     r"reduced|years?|experienced|expert|certified|guarantee|clients?|previously|"
                     r"past|won|percent|%)\b", re.I)


def verify(text: str, evidence: list[dict]):
    """Conservative extractive experience verification, not a semantic entailment claim.

    Exact quotation is deliberately restrictive. Free-form experience is blocked even
    when plausibly true; a future semantic verifier must be evaluated before relaxing it.
    """
    by_id = {item["id"]: item for item in evidence}
    claims, accepted = [], []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        match = QUOTE.fullmatch(paragraph)
        supported, evidence_id = False, None
        if match:
            quote, evidence_id = match.groups()
            item = by_id.get(evidence_id)
            supported = bool(item and quote.strip() in item["text"] and not risks(quote))
            label = "supported" if supported else "unsupported"
        elif paragraph.startswith(("Proposed approach:", "Question:")) and not HISTORY.search(paragraph) and not risks(paragraph):
            supported, label = True, "plan_or_question"
        else:
            label = "unsupported"
        claims.append({"text": paragraph, "label": label, "evidence_id": evidence_id})
        if supported:
            accepted.append(paragraph)
    return {"text": "\n\n".join(accepted), "claims": claims,
            "unsupported_before": sum(c["label"] == "unsupported" for c in claims),
            "unsupported_after": 0, "method": "conservative-extractive-v1"}
