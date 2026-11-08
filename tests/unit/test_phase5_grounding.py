import pytest

from apps.api.safety import redact
from rag.verify import verify


@pytest.mark.parametrize("text", [
    "Proposed approach: I would use my 20 years of experience.",
    "Question: Can you see that I increased revenue by 500%?",
    "Proposed approach: I would test authorization and guarantee success.",
])
def test_prefixes_do_not_launder_assertions(text):
    result = verify(text, [])
    assert result["text"] == "" and result["unsupported_before"] == 1
    assert result["unsupported_after"] == 0


def test_claims_are_checked_sentence_by_sentence():
    result = verify("Proposed approach: I would test authorization. I have built 50 systems.", [])
    assert result["text"] == "Proposed approach: I would test authorization."
    assert [claim["label"] for claim in result["claims"]] == ["plan", "unsupported"]


def test_numbers_negation_and_partial_matches_are_removed():
    evidence = [{"id": "e1x2y3", "text": "Built a prototype.\n\nDid not deploy it to production."}]
    assert verify("I built a prototype. [e1x2y3]", evidence)["text"] == "I built a prototype. [e1x2y3]"
    for claim, label in (("I deployed it to production. [e1x2y3]", "unsupported"),
                         ("I built 3 prototypes. [e1x2y3]", "unsupported"),
                         ("I built a prototype for a large bank. [e1x2y3]", "partly_supported"),
                         ("I built a prototype. [deleted1]", "unsupported")):
        result = verify(claim, evidence)
        assert result["text"] == "" and result["claims"][0]["label"] == label


def test_citation_variants_and_client_acknowledgement():
    evidence = [{"id": "e1x2y3", "text": "Built a prototype."}]
    result = verify("I understand you need a prototype.\n\nI built a prototype. [evidence_id: e1x2y3]", evidence)
    assert result["text"] == "I understand you need a prototype.\n\nI built a prototype. [e1x2y3]"
    assert verify("I built a prototype [id:e1x2y3].", evidence)["text"] == "I built a prototype. [e1x2y3]"
    slots = "Please let me know which slot works best for you: 2026-11-09T10:00:00+00:00."
    assert verify(slots, evidence)["text"] == slots


def test_curly_apostrophes_and_hyphens_are_read_as_plain_text():
    evidence = [{"id": "e1x2y3", "text": "Built a tenant-scoped API."}]
    result = verify("I\u2019d start with tenant isolation. I built a tenant\u2011scoped API. [e1x2y3]", evidence)
    assert [claim["label"] for claim in result["claims"]] == ["plan", "supported"]


def test_plans_cannot_carry_uncited_past_work():
    evidence = [{"id": "e1x2y3", "text": "Built a prototype.", "project": "Maple Search"}]
    for text in ("I would add citations, as demonstrated in my earlier search work.",
                 "I would reuse the retrieval design from Maple Search."):
        assert verify(text, evidence)["text"] == ""


def test_sentences_that_refer_to_a_removed_claim_are_removed():
    evidence = [{"id": "e1x2y3", "text": "Built a prototype. Documented the deployment for Cedar Tasks."}]
    result = verify("I built a large platform for a bank. This work was documented for Cedar Tasks. [e1x2y3]", evidence)
    assert result["text"] == "" and result["claims"][1]["reason"] == "Refers to a sentence that was removed"


async def test_critic_requires_every_screening_answer():
    from agent.nodes.workflow import Nodes
    from tests.support import TestModels
    state = {"tenant": "t", "job": {"screening_questions": ["How will you test?"]}, "verification": {},
             "draft": {"text": "I would test the API.", "screening_answers": {}}}
    result = await Nodes(None, TestModels()).critic(state)
    assert not result["critique"]["passed"] and result["critique"]["comments"] == ["Answer the screening question: How will you test?"]


async def test_critic_sends_back_a_proposal_without_cited_evidence():
    from agent.nodes.workflow import Nodes
    from tests.support import TestModels
    state = {"tenant": "t", "job": {"screening_questions": []}, "verification": {}, "fit": {"evidence": [{"id": "e1x2y3"}]},
             "draft": {"text": "I would test the API.", "screening_answers": {}}}
    result = await Nodes(None, TestModels()).critic(state)
    assert not result["critique"]["passed"]
    assert result["critique"]["comments"] == ["Show fit with at least one sentence about past work that cites evidence"]


def test_numeric_token_metrics_survive_secret_redaction():
    assert redact({"tokens": 123, "generated_tokens": 20, "access_token": "secret"}) == {
        "tokens": 123, "generated_tokens": 20, "access_token": "[REDACTED]"}
    assert redact({"tokens": "secret"}) == {"tokens": "[REDACTED]"}
