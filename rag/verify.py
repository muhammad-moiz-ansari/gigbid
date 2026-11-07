"""Conservative claim checking: exact evidence quotations and a closed plan grammar."""
import re

from apps.api.safety import risks

QUOTED = re.compile(r'^Portfolio evidence: "([\s\S]+?)" \[([A-Za-z0-9_-]+)\](?=\s*(?:\n\s*\n|$))')
ACTIONS = (
    r"begin with a small scope",
    r"start with a scoped API",
    r"start with a small prototype",
    r"test (?:each requirement|authorization|tenant isolation|the API)",
    r"clarify (?:the scope|the timeline|the acceptance criteria|the data sources)",
    r"implement (?:the agreed scope|the API|a prototype)",
    r"verify (?:each requirement|the requirements|authorization)",
    r"validate (?:the data|source totals)",
    r"reconcile source totals",
    r"compare the requirements with the supplied evidence",
)
ACTION = "(?:" + "|".join(ACTIONS) + ")"
PLAN = re.compile(r"^Proposed approach: I would (?:first )?" + ACTION + r"(?: and " + ACTION + r"){0,2}\.$")
QUESTION = re.compile(
    r"^Question: (?:Could you clarify (?:the scope|the timeline|the acceptance criteria|the data sources)"
    r"|What (?:are the acceptance criteria|is the expected timeline|is the budget)"
    r"|Which data sources should I use"
    r"|Are you available (?:for an interview|to discuss the scope))\?$"
)


def paragraphs(text):
    """Preserve multi-paragraph exact quotes instead of splitting them mid-passage."""
    remaining = text.strip()
    while remaining:
        match = QUOTED.match(remaining)
        if match:
            yield match.group(0).strip(), match.groups()
            remaining = remaining[match.end():].strip()
        else:
            parts = re.split(r"\n\s*\n", remaining, maxsplit=1)
            yield parts[0].strip(), None
            remaining = parts[1].strip() if len(parts) > 1 else ""


def verify(text: str, evidence: list[dict]):
    by_id = {item["id"]: item for item in evidence}
    claims, accepted = [], []
    for paragraph, quote in paragraphs(text):
        evidence_id = None
        label, reason = "unsupported", "Free-form assertion is outside the verified claim grammar"
        if quote:
            passage, evidence_id = quote
            item = by_id.get(evidence_id)
            if item and passage.strip() == item["text"].strip() and not risks(passage):
                label, reason = "supported", "Exact complete current evidence passage"
            elif item and passage.strip() in item["text"]:
                label, reason = "partly_supported", "Partial quotations may remove negation or context; removed"
            else:
                reason = "Citation is missing, altered, unsafe or does not match the complete passage"
        elif (PLAN.fullmatch(paragraph) or QUESTION.fullmatch(paragraph)) and not risks(paragraph):
            label, reason = "plan_or_question", "Closed future-plan/question grammar; no experience assertion"
        claims.append({"text": paragraph, "label": label, "evidence_id": evidence_id, "reason": reason})
        if label in ("supported", "plan_or_question"):
            accepted.append(paragraph)
    result = "\n\n".join(accepted)
    # Reparse accepted output rather than claiming an unmeasured semantic error rate.
    after = sum(not (quote and by_id.get(quote[1]) and quote[0].strip() == by_id[quote[1]]["text"].strip())
                and not (PLAN.fullmatch(p) or QUESTION.fullmatch(p)) for p, quote in paragraphs(result))
    return {"text": result, "claims": claims,
            "unsupported_before": sum(c["label"] in ("unsupported", "partly_supported") for c in claims),
            "unsupported_after": after, "method": "closed-grammar-extractive-v2"}
