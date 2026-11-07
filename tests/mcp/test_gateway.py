import asyncio
import json
import logging

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException

from agent.mcp_client import ALLOWLISTS, ToolFailure, ToolGateway, decode_result
from apps.api.config import settings
from mcp_servers.common import RedactingFilter


class StubTool:
    def __init__(self, name, *, failures=0, code="service_unavailable", delay=0, retry_after=0):
        self.name, self.failures, self.code = name, failures, code
        self.delay, self.retry_after, self.calls = delay, retry_after, 0

    async def ainvoke(self, request):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.calls <= self.failures:
            raise ToolException(
                json.dumps(
                    {
                        "code": self.code,
                        "message": "Synthetic MCP error",
                        "retryable": self.code != "permission_denied",
                        "retry_after": self.retry_after,
                    }
                )
            )
        return ToolMessage(
            content="not-used",
            tool_call_id=request["id"],
            artifact={"structured_content": {"result": ["one", "two"]}},
        )


@pytest.mark.asyncio
async def test_role_lists_and_runtime_deny_extra_tools():
    names = {name for allowed in ALLOWLISTS.values() for name in allowed}
    gateway = ToolGateway([StubTool(name) for name in names])
    for role, allowed in ALLOWLISTS.items():
        assert {t.name for t in gateway.for_role(role).tools} == allowed
    assert not gateway.for_role("analyst").tools and not gateway.for_role("compliance").tools
    with pytest.raises(PermissionError):
        await gateway.for_role("risk").call("submit_proposal", {})


@pytest.mark.asyncio
async def test_reads_retry_transient_errors_but_never_permissions(monkeypatch):
    monkeypatch.setattr(settings(), "mcp_retry_max_delay_seconds", 0)
    tool = StubTool("get_job", failures=2)
    gateway = ToolGateway([tool])
    assert await gateway.call("intake", "get_job", {}) == ["one", "two"]
    assert tool.calls == 3
    forbidden = StubTool("get_job", failures=5, code="permission_denied")
    with pytest.raises(ToolFailure):
        await ToolGateway([forbidden]).call("intake", "get_job", {})
    assert forbidden.calls == 1


@pytest.mark.asyncio
async def test_no_write_retry_and_honor_long_retry_after(monkeypatch):
    write = StubTool("submit_proposal", failures=5)
    with pytest.raises(ToolFailure):
        await ToolGateway([write]).call(
            "executor", "submit_proposal", {"request": {"dry_run": False}}
        )
    assert write.calls == 1
    limited = StubTool("get_job", failures=5, code="rate_limited", retry_after=60)
    with pytest.raises(ToolFailure) as error:
        await ToolGateway([limited]).call("intake", "get_job", {})
    assert error.value.retry_after == 60 and limited.calls == 1


@pytest.mark.asyncio
async def test_client_write_timeout_is_ambiguous_and_never_retried(monkeypatch):
    monkeypatch.setattr(settings(), "tool_timeout_seconds", 0.01)
    write = StubTool("submit_proposal", delay=0.1)
    with pytest.raises(ToolFailure) as error:
        await ToolGateway([write]).call(
            "executor", "submit_proposal", {"request": {"dry_run": False}}
        )
    assert error.value.ambiguous and write.calls == 1


@pytest.mark.asyncio
async def test_partial_discovery_then_recovery_without_privilege_expansion(monkeypatch):
    monkeypatch.setattr(settings(), "mcp_retry_max_delay_seconds", 0)
    restored = False

    async def loader(server):
        if server == "marketplace" and not restored:
            raise ConnectionError("Synthetic server offline")
        if server == "portfolio":
            return [
                StubTool("search_evidence"),
                StubTool("submit_proposal"),
            ]  # Impersonated tool is discarded.
        return [StubTool("get_job")]

    gateway = ToolGateway([], loader=loader)
    await asyncio.gather(gateway.refresh("marketplace"), gateway.refresh("portfolio"))
    assert not gateway.availability()["marketplace"]["available"]
    assert "submit_proposal" not in gateway.tools
    assert await gateway.call("matcher", "search_evidence", {}) == ["one", "two"]
    restored = True
    assert await gateway.call("intake", "get_job", {}) == ["one", "two"]
    assert gateway.availability()["marketplace"]["available"]


def test_structured_lists_null_and_multi_text_results_decode_without_truncation():
    assert decode_result(
        ToolMessage(
            content="",
            tool_call_id="x",
            artifact={"structured_content": {"result": [{"id": "a"}, {"id": "b"}]}},
        )
    ) == [{"id": "a"}, {"id": "b"}]
    assert (
        decode_result(
            ToolMessage(
                content="", tool_call_id="x", artifact={"structured_content": {"result": None}}
            )
        )
        is None
    )
    assert decode_result(
        [{"type": "text", "text": '{"id":"a"}'}, {"type": "text", "text": '{"id":"b"}'}]
    ) == [{"id": "a"}, {"id": "b"}]


def test_redacting_log_filter_preserves_json_numbers():
    record = logging.LogRecord(
        "test",
        logging.INFO,
        "",
        1,
        json.dumps(
            {"seconds": 0.0123456789, "authorization": "Bearer secret", "email": "a@example.test"}
        ),
        (),
        None,
    )
    RedactingFilter().filter(record)
    parsed = json.loads(record.getMessage())
    assert parsed["seconds"] == 0.0123456789
    assert parsed["authorization"] == "[REDACTED]" and parsed["email"] == "[REDACTED]"
