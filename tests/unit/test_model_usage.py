import httpx
import pytest

from agent.handoffs import RiskReport
from agent.model import OpenModel, usage_sink


@pytest.mark.asyncio
async def test_failed_structured_attempts_count_tokens_and_fallback(monkeypatch):
    calls = []
    def respond(request):
        import json
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "invalid" if len(calls) == 1 else
            '{"score":0.2,"flags":[],"reasons":[]}'}, "prompt_eval_count": 20, "eval_count": 5,
            "eval_duration": 100000000})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs:
        original(transport=httpx.MockTransport(respond), **kwargs))
    observations = []
    token = usage_sink.set(observations)
    try:
        result, usage = await OpenModel().complete("risk", {"untrusted": "job"}, RiskReport)
    finally:
        usage_sink.reset(token)
    assert result["score"] == .2 and usage["tokens"] == 50 and usage["attempts"] == 2
    assert usage["usage_complete"] and len(observations) == 2
    assert sum(u["tokens"] for u in observations) == 50
    assert calls[0]["messages"][0]["role"] == "system"
    assert calls[0]["think"] is False


@pytest.mark.asyncio
async def test_unreported_remote_usage_is_marked_unknown(monkeypatch):
    original = httpx.AsyncClient
    def respond(request):
        raise httpx.ReadTimeout("Unconfirmed inference", request=request)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs:
        original(transport=httpx.MockTransport(respond), **kwargs))
    observations = []
    token = usage_sink.set(observations)
    try:
        with pytest.raises(RuntimeError, match="unavailable"):
            await OpenModel().complete("risk", {}, RiskReport)
    finally:
        usage_sink.reset(token)
    assert len(observations) == 2 and all(not u["usage_complete"] for u in observations)


@pytest.mark.asyncio
async def test_malformed_response_cannot_report_zero_known_usage(monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs:
        original(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])), **kwargs))
    observations = []
    token = usage_sink.set(observations)
    try:
        with pytest.raises(RuntimeError):
            await OpenModel().complete("risk", {}, RiskReport)
    finally:
        usage_sink.reset(token)
    assert len(observations) == 2 and all(not u["usage_complete"] for u in observations)
