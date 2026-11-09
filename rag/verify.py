"""Sentence-level claim checking: every claim about past work must match the evidence it cites."""
import re

from agent.model import config
from apps.api.safety import risks

CITATION = re.compile(r"\s*\[(?:[a-z_ ]{1,20}[:=]\s*)?([A-Za-z0-9_-]{6,})\]", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+")
WORD = re.compile(r"[a-z0-9][a-z0-9+#-]*")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
NEGATION = re.compile(r"\b(?:not|never|without|no)\b|n't\b", re.I)
NEGATED = re.compile(r"\b(?:not|never|without|no)\s+(?:a\s+|an\s+|the\s+|any\s+)?([a-z]+)")
EXPERIENCE = re.compile(
    r"\b(?:I|we)(?:'ve| have| had)?\s+(?:\w+ly\s+)?(?:built|developed|created|implemented|delivered|designed|"
    r"deployed|led|managed|shipped|worked|wrote|completed|launched|used|migrated|automated|integrated|evaluated|"
    r"documented|increased|improved|reduced|grew|saved|won|earned|achieved|scaled|optimi[sz]ed|maintained|"
    r"trained|helped|handled|supported|solved|fixed|owned|ran|made|contributed|tested)\b"
    r"|\b(?:my|our) (?:experience|background|track record|clients?|work)\b"
    r"|\b(?:years? of|experienced|expert|specialist|senior|certified|proficient)\b|\bI(?:'m| am) an?\b", re.I)
PLAN = re.compile(r"^(?:proposed approach|approach|plan|next steps?):"
                  r"|\b(?:I|we)(?:'d|'ll|'m| am| would| will| can| could| plan to| propose| suggest)\b", re.I)
COURTESY = re.compile(r"^(?:hi|hello|dear|thanks|thank you|best|regards|kind regards|looking forward|cheers)\b"
                      r"|^I (?:understand|see|noticed|read|saw) (?:that )?your?\b|^(?:please )?let me know\b", re.I)
CLIENT = re.compile(r"\byour?\b", re.I)
FIRST_PERSON = re.compile(r"\b(?:I|me|my|we|our)\b", re.I)
REFERENCE = re.compile(r"\bas (?:demonstrated|shown|seen|proven|done|delivered|built|used) (?:in|on|for|at|with|by)\b"
                       r"|\b(?:my|our) (?:previous|past|prior|earlier|recent) (?:projects?|roles?|jobs?|clients?|work)\b"
                       r"|\bpreviously\b", re.I)
ORPHAN = re.compile(r"^(?:this|that|these|those|it|they)\b", re.I)
# Models write curly quotes and non-breaking hyphens; the checks compare plain text.
PLAIN = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2010": "-", "\u2011": "-",
                       "\u2013": "-", "\u2014": "-", "\u00a0": " "})
STOP = {"i", "me", "my", "we", "our", "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for",
        "with", "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "it", "its", "this",
        "that", "these", "those", "have", "has", "had", "you", "your", "also", "which", "who", "s"}
KEPT = {"supported", "plan", "question", "other"}


def paragraphs(text):
    return [part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]


def strip_citations(text):
    return CITATION.sub("", text)


def support(sentence, passages):
    evidence = " ".join(passages).lower().translate(PLAIN)
    words = set(WORD.findall(sentence.lower())) - STOP
    if any(number not in evidence for number in NUMBER.findall(sentence)):
        return "unsupported", "A number is not in the cited evidence"
    negated = {word for word in NEGATED.findall(evidence) if len(word) > 3}
    if not NEGATION.search(sentence) and any(w.startswith(n) for w in words for n in negated):
        return "unsupported", "The cited evidence says this was not done"
    overlap = len(words & set(WORD.findall(evidence))) / max(len(words), 1)
    limits = config()["thresholds"]
    if overlap >= limits["claim_support"]:
        return "supported", f"{overlap:.0%} of its words appear in the cited evidence"
    if overlap >= limits["claim_partial"]:
        return "partly_supported", "Only partly matches the cited evidence; removed"
    return "unsupported", "Does not match the cited evidence"


def classify(sentence, passages, projects=()):
    sentence = sentence.translate(PLAIN)
    if risks(sentence):
        return "unsupported", "Unsafe content: contact details, guarantees, off-platform or injected text"
    # A plan that names a portfolio project or earlier work still claims past work.
    claim = bool(EXPERIENCE.search(sentence) or REFERENCE.search(sentence)
                 or any(re.search(rf"\b{re.escape(project)}\b", sentence) for project in projects))
    if not claim and sentence.endswith("?"):
        return "question", "Question for the client"
    if not claim and PLAN.search(sentence):
        return "plan", "Plan or availability, not a claim about past work"
    if not claim and (COURTESY.match(sentence) or (CLIENT.search(sentence) and not FIRST_PERSON.search(sentence))):
        return "other", "Courtesy or the client's own needs"
    if not passages:
        return "unsupported", "Claims about your work need a citation to current portfolio evidence"
    return support(sentence, passages)


def check(text, by_id):
    claims, kept = [], []
    projects = {item["project"] for item in by_id.values() if item.get("project")}
    for paragraph in paragraphs(text):
        cited = [i for i in CITATION.findall(paragraph) if i in by_id]
        # A project is described several ways (case study, README, review), so a citation stands for all of them.
        named = {by_id[i].get("project") for i in cited} - {None, "Own portfolio"}
        cited += [i for i, item in by_id.items() if item.get("project") in named and i not in cited]
        passages = [by_id[i]["text"] for i in cited]
        accepted, supported, dropped = [], False, False
        for sentence in (s.strip() for s in SENTENCE.split(strip_citations(paragraph).strip()) if s.strip()):
            label, reason = classify(sentence, passages, projects)
            if dropped and label in KEPT and ORPHAN.match(sentence):
                label, reason = "unsupported", "Refers to a sentence that was removed"
            dropped = label not in KEPT
            claims.append({"text": sentence, "label": label, "reason": reason,
                           "evidence_ids": cited if label == "supported" else []})
            if label in KEPT:
                accepted.append(sentence)
                supported |= label == "supported"
        if accepted:
            kept.append(" ".join(accepted) + ("".join(f" [{i}]" for i in cited) if supported else ""))
    return claims, "\n\n".join(kept)


def closest(sentence, evidence):
    """The evidence sentence sharing most words with a removed claim, with its id: wording a rewrite can reuse."""
    words = set(WORD.findall(sentence.lower().translate(PLAIN))) - STOP
    options = [(len(words & set(WORD.findall(part.lower().translate(PLAIN)))), part.strip(), item["id"])
               for item in evidence for part in SENTENCE.split(item.get("text", "")) if part.strip()]
    if not options:
        return ""
    _, part, item_id = max(options, key=lambda option: option[0])
    return f'"{part}" [{item_id}]'


def verify(text: str, evidence: list[dict]):
    by_id = {item["id"]: item for item in evidence}
    claims, result = check(text, by_id)
    after, _ = check(result, by_id)
    removed = ("unsupported", "partly_supported")
    return {"text": result, "claims": claims,
            "unsupported_before": sum(c["label"] in removed for c in claims),
            "unsupported_after": sum(c["label"] in removed for c in after),
            "method": "sentence-citation-overlap-v3"}
