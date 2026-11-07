import asyncio
import time

import pytest
from sqlalchemy import select

from apps.api.config import settings
from apps.api.db import Event, get_record, put_record, transaction
from mcp_servers.common import BoundaryError, execute_tool


@pytest.mark.asyncio
async def test_server_read_deadline_is_bounded_and_audited(mcp_identity, monkeypatch):
    monkeypatch.setattr(settings(), "mcp_server_timeout_seconds", 0.01)

    def delayed(tenant):
        time.sleep(0.04)
        return {"status": "read-completed"}

    with pytest.raises(BoundaryError) as error:
        await execute_tool("deadline_read", {}, delayed)
    assert error.value.data["code"] == "service_timeout"
    assert error.value.data["retryable"] and not error.value.data["ambiguous"]
    await asyncio.sleep(0.08)
    with transaction() as db:
        events = list(db.scalars(select(Event).where(Event.tenant == mcp_identity[0])))
    assert any(e.name == "tool:deadline_read:error" for e in events)
    assert any(e.name == "tool:deadline_read:late_success" for e in events)


@pytest.mark.asyncio
async def test_sync_write_timeout_reports_unknown_outcome_instead_of_failure(
    mcp_identity, monkeypatch
):
    monkeypatch.setattr(settings(), "mcp_server_timeout_seconds", 0.01)

    def delayed(tenant):
        time.sleep(0.04)
        with transaction() as db:
            put_record(db, tenant, "deadline_test", "effect", {"committed": True})
        return {"status": "committed"}

    with pytest.raises(BoundaryError) as error:
        await execute_tool(
            "deadline_write", {"idempotency_key": "stable-test-key"}, delayed, mutating=True
        )
    assert error.value.data["code"] == "ambiguous_write"
    assert error.value.data["ambiguous"] and not error.value.data["retryable"]
    await asyncio.sleep(0.08)
    with transaction() as db:
        assert get_record(db, mcp_identity[0], "deadline_test", "effect").value["committed"]
