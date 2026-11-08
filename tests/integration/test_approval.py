import pytest

from agent.handoffs import Action, WriteRequest
from apps.api.db import get_record, transaction
from dev_support.mock_marketplace.service import MockMarketplace
from tests.support import TestModels, TestTools
from worker.runtime import process_run


@pytest.mark.asyncio
async def test_restart_approve_and_replay(client, account):
    tenant = account["id"]
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    tools = TestTools(tenant)
    await process_run(run_id, tools, TestModels())
    result = client.get(f"/runs/{run_id}").json()
    assert result["status"] == "awaiting_approval", result
    assert MockMarketplace().balance(tenant)["spent"] == 0
    assert "[" in result["state"]["draft"]["text"] and "[" not in result["state"]["preview"]["payload"]["text"]
    approval_id = result["state"]["approval_id"]
    assert client.post(f"/approvals/{approval_id}/decision", json={"decision": "approve"}).status_code == 200
    # Reopens the durable SQLite checkpointer, recreates graph and model after pause.
    await process_run(run_id, TestTools(tenant), TestModels())
    result = client.get(f"/runs/{run_id}").json()
    assert result["status"] == "submitted", result
    assert MockMarketplace().balance(tenant)["spent"] == 8
    await process_run(run_id, TestTools(tenant), TestModels())
    assert MockMarketplace().balance(tenant)["spent"] == 8
    request = [args["request"] for _, name, args in tools.calls if name == "submit_proposal"][0]
    request.update(dry_run=False, approval_id=approval_id)
    first = MockMarketplace().write(tenant, WriteRequest.model_validate(request))
    second = MockMarketplace().write(tenant, WriteRequest.model_validate(request))
    assert first.effect_id == second.effect_id
    request["action"]["text"] += "tamper"
    with pytest.raises(ValueError, match="different payload"):
        MockMarketplace().write(tenant, WriteRequest.model_validate(request))


@pytest.mark.asyncio
async def test_no_bypass_and_stale_cost(client, account):
    tenant = account["id"]
    request = WriteRequest(action=Action(kind="proposal", destination="mock-api", text="Unapproved"),
                           run_id="unknown", idempotency_key="unapproved-key", dry_run=False)
    with pytest.raises(PermissionError):
        MockMarketplace().write(tenant, request)
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    result = client.get(f"/runs/{run_id}").json()
    approval_id = result["state"]["approval_id"]
    client.post(f"/approvals/{approval_id}/decision", json={"decision": "approve"})
    with transaction() as db:
        job = get_record(db, tenant, "job", "mock-api")
        job.value = {**job.value, "connects": 9}
    await process_run(run_id, TestTools(tenant), TestModels())
    assert MockMarketplace().balance(tenant)["spent"] == 0
    assert client.get(f"/runs/{run_id}").json()["status"] == "recoverable"


@pytest.mark.asyncio
async def test_edit_rechecks_and_reject_reason(client, account):
    tenant = account["id"]
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    approval_id = client.get(f"/runs/{run_id}").json()["state"]["approval_id"]
    assert client.post(f"/approvals/{approval_id}/decision", json={"decision": "reject"}).status_code == 422
    client.post(f"/approvals/{approval_id}/decision", json={"decision": "edit", "text": "Proposed approach: I would start with a scoped API."})
    await process_run(run_id, TestTools(tenant), TestModels())
    edited = client.get(f"/runs/{run_id}").json()
    assert edited["status"] == "awaiting_approval", edited
    assert edited["state"]["approval_id"] != approval_id
    assert edited["state"]["draft"]["version"] == 2
    new_id = edited["state"]["approval_id"]
    client.post(f"/approvals/{new_id}/decision", json={"decision": "reject", "reason": "Scope too broad"})
    await process_run(run_id, TestTools(tenant), TestModels())
    assert client.get(f"/runs/{run_id}").json()["status"] == "rejected"
    assert MockMarketplace().balance(tenant)["spent"] == 0


@pytest.mark.asyncio
async def test_ambiguous_response_reconciles_once(client, account):
    tenant = account["id"]
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    result = client.get(f"/runs/{run_id}").json()
    client.post(f'/approvals/{result["state"]["approval_id"]}/decision', json={"decision": "approve"})
    client.put("/dev/fault", json={"mode": "ambiguous_write"})
    await process_run(run_id, TestTools(tenant), TestModels())
    result = client.get(f"/runs/{run_id}").json()
    assert result["status"] == "submitted", result
    assert MockMarketplace().balance(tenant)["spent"] == 8


@pytest.mark.asyncio
async def test_scam_is_skipped_and_deleted_evidence_blocks(client, account):
    tenant = account["id"]
    run_id = client.post("/jobs/mock-scam/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    assert client.get(f"/runs/{run_id}").json()["status"] == "skip"
    assert client.get("/approvals").json() == []
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    result = client.get(f"/runs/{run_id}").json()
    source = result["state"]["fit"]["evidence"][0]["source"]
    client.delete(f"/evidence/source/{source}")
    assert client.post(f'/approvals/{result["state"]["approval_id"]}/decision', json={"decision": "approve"}).status_code == 409
