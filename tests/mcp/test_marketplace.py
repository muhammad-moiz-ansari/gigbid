import json

import pytest
from sqlalchemy import select

from agent.handoffs import Action, WriteRequest
from agent.mcp_client import ToolFailure
from apps.api.approvals import stage_approval
from apps.api.db import Event, Run, get_record, transaction, uid
from dev_support.mock_marketplace.service import MockMarketplace


def request(kind="proposal", destination="mock-api"):
    return WriteRequest(
        action=Action(
            kind=kind,
            destination=destination,
            text="Proposed approach: Test a scoped API.",
            price=500,
        ),
        run_id=uid(),
        idempotency_key=uid(),
    ).model_dump()


def approve(tenant, req, preview):
    preview = {k: v for k, v in preview.items() if k != "effect_id"}
    with transaction() as db:
        db.add(Run(id=req["run_id"], tenant=tenant, subject=uid(), kind="bid", status="running"))
        db.flush()
        approval = stage_approval(db, tenant, req["run_id"], preview)
        approval.decision = "approved"
        req.update(approval_id=approval.id, dry_run=False)


@pytest.mark.asyncio
async def test_exact_preview_approval_execution_and_idempotency(protocol, mcp_identity):
    sessions, tools = protocol
    req = request()
    before = MockMarketplace().balance(mcp_identity[0])
    preview = await tools.call("executor", "submit_proposal", {"request": req})
    assert preview["payload"] == req["action"] and preview["connects_cost"] == 8
    assert MockMarketplace().balance(mcp_identity[0]) == before
    assert (
        await tools.call("executor", "reconcile_write", {"idempotency_key": req["idempotency_key"]})
        is None
    )
    unapproved = {**req, "dry_run": False}
    with pytest.raises(ToolFailure) as error:
        await tools.call("executor", "submit_proposal", {"request": unapproved})
    assert error.value.code == "permission_denied"
    approve(mcp_identity[0], req, preview)
    first = await tools.call("executor", "submit_proposal", {"request": req})
    second = await tools.call("executor", "submit_proposal", {"request": req})
    assert first == second and first["status"] == "submitted"
    assert MockMarketplace().balance(mcp_identity[0])["spent"] == 8
    changed = {**req, "action": {**req["action"], "text": "Changed after approval"}}
    with pytest.raises(ToolFailure) as conflict:
        await tools.call("executor", "submit_proposal", {"request": changed})
    assert conflict.value.code == "idempotency_conflict"
    with transaction() as db:
        events = list(db.scalars(select(Event).where(Event.tenant == mcp_identity[0])))
    assert any(
        e.name.endswith(":success") and e.payload.get("effect_id") == first["effect_id"]
        for e in events
    )


@pytest.mark.asyncio
async def test_changed_cost_requires_new_approval(protocol, mcp_identity):
    _, tools = protocol
    req = request()
    preview = await tools.call("executor", "submit_proposal", {"request": req})
    approve(mcp_identity[0], req, preview)
    with transaction() as db:
        job = get_record(db, mcp_identity[0], "job", "mock-api")
        job.value = {**job.value, "connects": 10}
    with pytest.raises(ToolFailure) as error:
        await tools.call("executor", "submit_proposal", {"request": req})
    assert error.value.code == "permission_denied"
    assert MockMarketplace().balance(mcp_identity[0])["spent"] == 0


@pytest.mark.asyncio
async def test_deleted_evidence_and_cross_tenant_approvals_are_rejected(
    protocol, mcp_identity, monkeypatch
):
    from apps.api.auth.service import issue_session
    from apps.api.db import User
    from dev_support.mock_marketplace.seed import seed_marketplace

    _, tools = protocol
    hit = (await tools.call("matcher", "search_evidence", {"requirement": "FastAPI"}))[0]
    req = request()
    req["action"]["evidence_hashes"] = {hit["id"]: hit["content_hash"]}
    preview = await tools.call("executor", "submit_proposal", {"request": req})
    approve(mcp_identity[0], req, preview)
    with transaction() as db:
        db.delete(get_record(db, mcp_identity[0], "evidence", hit["id"]))
    with pytest.raises(ToolFailure) as error:
        await tools.call("executor", "submit_proposal", {"request": req})
    assert error.value.code == "permission_denied"
    with transaction() as db:
        other = uid()
        db.add(
            User(
                id=other,
                email="write-other@example.test",
                password_hash="unused-test-hash",
                profile={},
            )
        )
        db.flush()
        token, _ = issue_session(db, other)
    seed_marketplace(other)
    monkeypatch.setenv("GIGBID_MCP_TOKEN", token)
    with pytest.raises(ToolFailure) as denied:
        await tools.call("executor", "submit_proposal", {"request": req})
    assert denied.value.code == "permission_denied"
    assert (
        MockMarketplace().balance(other)["spent"]
        == MockMarketplace().balance(mcp_identity[0])["spent"]
        == 0
    )


@pytest.mark.asyncio
async def test_invalid_write_kind_and_missing_key_rejected_by_schema(protocol):
    sessions, _ = protocol
    req = request(kind="message")
    result = await sessions["marketplace"].call_tool("submit_proposal", {"request": req})
    assert result.isError
    req = request()
    req.pop("idempotency_key")
    result = await sessions["marketplace"].call_tool("submit_proposal", {"request": req})
    assert result.isError


@pytest.mark.asyncio
async def test_arguments_and_results_redacted_in_append_only_audit(protocol, mcp_identity):
    _, tools = protocol
    req = request()
    req["action"]["text"] = (
        "Email me at private@example.test, +92 300 1234567. Bearer private_token_value"
    )
    await tools.call("executor", "submit_proposal", {"request": req})
    with transaction() as db:
        events = list(
            db.scalars(select(Event).where(Event.tenant == mcp_identity[0], Event.run_id == "mcp"))
        )
    encoded = json.dumps([e.payload for e in events])
    assert "private@example.test" not in encoded and "private_token_value" not in encoded
    assert "1234567" not in encoded
    assert all(e.trace_id == "phase3-test-trace" for e in events)
    assert any("arguments_hash" in e.payload for e in events)
    assert any("sha256" in e.payload for e in events)
