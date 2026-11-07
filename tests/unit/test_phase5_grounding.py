import pytest

from apps.api.safety import redact
from rag.verify import verify


@pytest.mark.parametrize("text", [
    "Proposed approach: I would use my 20 years of experience.",
    "Proposed approach: I would test authorization. I have built 50 systems.",
    "Question: Can you see that I increased revenue by 500%?",
    "Proposed approach: I would test authorization and guarantee success.",
])
def test_prefixes_do_not_launder_assertions(text):
    result = verify(text, [])
    assert result["text"] == "" and result["unsupported_before"] == 1
    assert result["unsupported_after"] == 0


def test_whole_quote_preserves_multiline_context_and_negation():
    evidence = [{"id": "e1", "text": "Built a prototype.\n\nDid not deploy it to production."}]
    complete = 'Portfolio evidence: "Built a prototype.\n\nDid not deploy it to production." [e1]'
    partial = 'Portfolio evidence: "Built a prototype." [e1]'
    assert verify(complete, evidence)["text"] == complete
    result = verify(partial, evidence)
    assert result["text"] == "" and result["claims"][0]["label"] == "partly_supported"


def test_numeric_token_metrics_survive_secret_redaction():
    assert redact({"tokens": 123, "generated_tokens": 20, "access_token": "secret"}) == {
        "tokens": 123, "generated_tokens": 20, "access_token": "[REDACTED]"}
    assert redact({"tokens": "secret"}) == {"tokens": "[REDACTED]"}
