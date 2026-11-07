import asyncio

import pytest

from agent.handoffs import Action, WriteRequest
from agent.mcp_client import ToolFailure
from apps.api.approvals import stage_approval
from apps.api.db import Run, transaction, uid


async def approved(tools, tenant, kind, destination, *, text="Discuss the project scope"):
    name = "create_interview_hold" if kind == "hold" else "create_email_draft"
    req = WriteRequest(
        action=Action(kind=kind, destination=destination, text=text),
        run_id=uid(),
        idempotency_key=uid(),
    ).model_dump()
    preview = await tools.call("executor", name, {"request": req})
    assert preview["payload"] == req["action"] and preview["connects_cost"] == 0
    with transaction() as db:
        db.add(
            Run(
                id=req["run_id"],
                tenant=tenant,
                kind="conversation",
                subject=uid(),
                status="running",
            )
        )
        db.flush()
        approval = stage_approval(
            db, tenant, req["run_id"], {k: v for k, v in preview.items() if k != "effect_id"}
        )
        approval.decision = "approved"
        req.update(approval_id=approval.id, dry_run=False)
    return name, req


@pytest.mark.asyncio
async def test_calendar_holds_are_approved_idempotent_and_concurrency_safe(protocol, mcp_identity):
    _, tools = protocol
    slots = await tools.call("liaison", "free_slots", {})
    assert len(slots) == 3 and all(s["synthetic"] and s["minutes"] == 30 for s in slots)
    name, req = await approved(tools, mcp_identity[0], "hold", slots[0]["start"])
    other_name, other = await approved(tools, mcp_identity[0], "hold", slots[0]["start"])
    assert len(await tools.call("liaison", "free_slots", {})) == 3  # previews made no hold
    results = await asyncio.gather(
        *(tools.call("executor", name, {"request": req}) for _ in range(5))
    )
    assert len({r["effect_id"] for r in results}) == 1
    assert results[0]["status"] == "tentative"
    assert len(await tools.call("liaison", "free_slots", {})) == 2
    with pytest.raises(ToolFailure) as error:
        await tools.call("executor", other_name, {"request": other})
    assert error.value.code == "invalid_request"
    altered = {**req, "run_id": "other-run"}
    with pytest.raises(ToolFailure):
        await tools.call("executor", name, {"request": altered})


@pytest.mark.asyncio
async def test_email_drafts_are_local_and_require_exact_approval(protocol, mcp_identity):
    _, tools = protocol
    name, req = await approved(tools, mcp_identity[0], "email", "client@example.test")
    changed = {**req, "action": {**req["action"], "text": "Changed content"}}
    with pytest.raises(ToolFailure) as error:
        await tools.call("executor", name, {"request": changed})
    assert error.value.code == "permission_denied"
    result = await tools.call("executor", name, {"request": req})
    assert result["mode"] == "workspace-mock" and result["status"] == "drafted"
    assert await tools.call("executor", name, {"request": req}) == result


@pytest.mark.asyncio
async def test_bad_calendar_and_email_destinations_are_rejected(protocol):
    _, tools = protocol
    for kind, destination in (
        ("hold", "2020-01-01T10:00:00+00:00"),
        ("hold", "2026-11-08T10:00:00"),
        ("email", "not-an-email"),
    ):
        req = WriteRequest(
            action=Action(kind=kind, destination=destination, text="test"),
            run_id=uid(),
            idempotency_key=uid(),
        ).model_dump()
        name = "create_interview_hold" if kind == "hold" else "create_email_draft"
        with pytest.raises(ToolFailure):
            await tools.call("executor", name, {"request": req})
