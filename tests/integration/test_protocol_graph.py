import pytest

from agent.mcp_client import gateway
from apps.api.auth.service import issue_session
from apps.api.db import transaction
from tests.support import TestModels
from worker.runtime import process_run


@pytest.mark.asyncio
async def test_full_graph_through_actual_mcp(client, account, monkeypatch):
    # Actual MCP subprocesses, real graph and durable checkpoints. Model is a labelled
    # test double and retrieval is explicitly lexical, never misreported as dense RAG.
    monkeypatch.setenv("RETRIEVAL_VARIANT", "BM25")
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    with transaction() as db:
        token, _ = issue_session(db, account["id"])
    async with gateway(token, "full-protocol-graph-test") as tools:
        await process_run(run_id, tools, TestModels())
        result = client.get(f"/runs/{run_id}").json()
        assert result["status"] == "awaiting_approval", result
        client.post(f'/approvals/{result["state"]["approval_id"]}/decision', json={"decision": "approve"})
        await process_run(run_id, tools, TestModels())
        result = client.get(f"/runs/{run_id}").json()
        assert result["status"] == "submitted", result
        assert (await tools.call("pricing", "get_connects_balance", {}))["spent"] == 8


@pytest.mark.asyncio
async def test_conversation_approval(client, account):
    from tests.support import TestTools
    client.post("/dev/client-message", json={"conversation": "client-one", "text": "Can we schedule an interview about Python?"})
    run_id = client.post("/messages/client-one/draft").json()["id"]
    await process_run(run_id, TestTools(account["id"]), TestModels())
    result = client.get(f"/runs/{run_id}").json()
    assert result["status"] == "awaiting_approval", result
    assert result["state"]["intent"] == "interview"
    assert len(client.get("/messages").json()) == 1
    client.post(f'/approvals/{result["state"]["approval_id"]}/decision', json={"decision": "approve"})
    await process_run(run_id, TestTools(account["id"]), TestModels())
    assert client.get(f"/runs/{run_id}").json()["status"] == "sent"
    assert len(client.get("/messages").json()) == 2
