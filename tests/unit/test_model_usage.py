import json

import httpx
import pytest

from agent.handoffs import RiskReport
from agent.model import OpenModel, usage_sink
from apps.api.config import settings


def transport(monkeypatch, respond):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs:
        original(transport=httpx.MockTransport(respond), **kwargs))


async def complete(node="risk", data=None):
    observations = []
    token = usage_sink.set(observations)
    try:
        return await OpenModel().complete(node, data or {"untrusted": "job"}, RiskReport), observations
    finally:
        usage_sink.reset(token)


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(settings(), "model_profile", "open_local")


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setattr(settings(), "model_profile", "open")
    monkeypatch.setattr(settings(), "groq_api_key", "test-key")


async def test_failed_structured_attempts_count_tokens_and_fallback(monkeypatch, local):
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "invalid" if len(calls) == 1 else
            '{"score":0.2,"flags":[],"reasons":[]}'}, "prompt_eval_count": 20, "eval_count": 5,
            "eval_duration": 100000000})
    transport(monkeypatch, respond)
    (result, usage), observations = await complete()
    assert result["score"] == .2 and usage["tokens"] == 50 and usage["attempts"] == 2
    assert usage["usage_complete"] and len(observations) == 2
    assert sum(u["tokens"] for u in observations) == 50
    assert calls[0]["messages"][0]["role"] == "system"
    assert calls[0]["think"] is False and calls[0]["keep_alive"] == "30m"
    assert calls[0]["options"]["num_predict"] == 400 and [c["model"] for c in calls] == ["qwen3:4b", "qwen3:1.7b"]


async def test_unreported_remote_usage_is_marked_unknown(monkeypatch, local):
    def respond(request):
        raise httpx.ReadTimeout("Unconfirmed inference", request=request)
    transport(monkeypatch, respond)
    with pytest.raises(RuntimeError, match="unavailable"):
        await complete()


async def test_malformed_response_cannot_report_zero_known_usage(monkeypatch, local):
    transport(monkeypatch, lambda request: httpx.Response(200, json=[]))
    observations = []
    token = usage_sink.set(observations)
    try:
        with pytest.raises(RuntimeError):
            await OpenModel().complete("risk", {}, RiskReport)
    finally:
        usage_sink.reset(token)
    assert len(observations) == 2 and all(not u["usage_complete"] for u in observations)


def groq_reply(content, prompt_tokens=300, completion_tokens=100):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                                               "completion_time": 0.2}})


async def test_hosted_request_uses_json_mode_caps_and_published_prices(monkeypatch, hosted):
    requests = []
    def respond(request):
        requests.append(request)
        return groq_reply('{"score":0.3,"flags":["vague_scope"],"reasons":["Scope is unclear"]}')
    transport(monkeypatch, respond)
    (result, usage), _ = await complete()
    body = json.loads(requests[0].content)
    assert str(requests[0].url) == "https://api.groq.com/openai/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    assert body["model"] == "openai/gpt-oss-20b" and body["max_completion_tokens"] == 1000
    assert body["response_format"] == {"type": "json_object"} and body["reasoning_effort"] == "low"
    assert "Return only JSON matching this schema:" in body["messages"][0]["content"]
    assert "flags" in body["messages"][0]["content"]
    assert result["flags"] == ["vague_scope"] and usage["provider"] == "groq" and usage["tokens"] == 400
    assert usage["api_usd"] == pytest.approx((300 * 0.075 + 100 * 0.30) / 1e6)


async def test_hosted_rate_limit_falls_back_with_known_zero_usage(monkeypatch, hosted):
    models = []
    def respond(request):
        models.append(json.loads(request.content)["model"])
        if len(models) == 1:
            return httpx.Response(429, headers={"retry-after": "0.01"}, json={"error": {"code": "rate_limit_exceeded"}})
        return groq_reply('{"score":0.1,"flags":[],"reasons":[]}')
    transport(monkeypatch, respond)
    (_, usage), observations = await complete()
    assert models == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert usage["attempts"] == 2 and usage["usage_complete"] and observations[0]["tokens"] == 0


async def test_invalid_risk_flag_is_rejected_by_the_contract(monkeypatch, hosted):
    transport(monkeypatch, lambda request: groq_reply('{"score":0.1,"flags":["Off-Platform Payment"],"reasons":[]}'))
    with pytest.raises(RuntimeError, match="invalid"):
        await complete()


def test_risk_flags_come_from_config(monkeypatch):
    from agent.model import config
    monkeypatch.setitem(config()["policy"], "risk_flags", [*config()["policy"]["risk_flags"], "new_policy_rule"])
    assert RiskReport.model_validate({"score": 0.2, "flags": ["new_policy_rule"], "reasons": ["x"]}).flags == ["new_policy_rule"]
    with pytest.raises(ValueError, match="Unknown risk flags"):
        RiskReport.model_validate({"score": 0.2, "flags": ["unlisted"], "reasons": ["x"]})


@pytest.mark.parametrize("status,known", [(404, True), (503, False)])
async def test_rejected_request_falls_back_with_known_usage_but_server_errors_stay_unknown(monkeypatch, hosted, status, known):
    calls = []
    def respond(request):
        calls.append(json.loads(request.content)["model"])
        if len(calls) == 1:
            return httpx.Response(status, json={"error": {"message": "unavailable"}})
        return groq_reply('{"score":0.1,"flags":[],"reasons":[]}')
    transport(monkeypatch, respond)
    (_, usage), observations = await complete()
    assert calls == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert observations[0]["usage_complete"] is known and usage["usage_complete"] is known
