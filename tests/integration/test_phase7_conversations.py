from agent.memory.store import delete_memory, list_memory, promote
from apps.api.db import Approval, transaction
from dev_support.mock_marketplace.config import SimulatorConfig
from dev_support.mock_marketplace.service import MockMarketplace
from tests.support import TestModels, TestTools
from worker.runtime import process_run


async def turn(client, tenant, text, conversation="mock-api", model=None):
    client.post("/dev/client-message", json={"conversation": conversation, "text": text})
    run_id = client.post(f"/messages/{conversation}/draft").json()["id"]
    await process_run(run_id, TestTools(tenant), model or TestModels())
    return client.get(f"/runs/{run_id}").json()


async def approve(client, tenant, run):
    client.post(f"/approvals/{run['state']['approval_id']}/decision", json={"decision": "approve"})
    await process_run(run["id"], TestTools(tenant), TestModels())
    return client.get(f"/runs/{run['id']}").json()


async def test_client_messages_continue_one_thread(client, account):
    tenant = account["id"]
    first = await turn(client, tenant, "Can we schedule an interview about the API?")
    assert first["status"] == "awaiting_approval" and first["state"]["intent"] == "interview"
    assert first["state"]["slots"] and first["state"]["job"]["title"] == "Build a secure task API"
    assert (await approve(client, tenant, first))["status"] == "sent"
    second = await turn(client, tenant, "Thanks. What would you test first?")
    assert second["id"] == first["id"] and second["status"] == "awaiting_approval"
    assert second["state"]["intent"] == "question" and second["state"]["draft"]["version"] > first["state"]["draft"]["version"]
    assert (await approve(client, tenant, second))["status"] == "sent"
    assert [m["direction"] for m in client.get("/messages").json()] == ["inbound", "outbound", "inbound", "outbound"]


async def test_new_message_during_review_redrafts(client, account):
    tenant = account["id"]
    first = await turn(client, tenant, "Could you share your approach?")
    second = await turn(client, tenant, "Also, what is your availability?")
    assert second["status"] == "awaiting_approval" and second["state"]["approval_id"] != first["state"]["approval_id"]
    with transaction() as db:
        assert db.get(Approval, first["state"]["approval_id"]).decision == "invalidated"
    stale = client.post(f"/approvals/{first['state']['approval_id']}/decision", json={"decision": "approve"})
    assert stale.status_code == 409


async def test_scam_message_gets_no_reply(client, account):
    run = await turn(client, account["id"], "Contact me on Telegram and complete a free test first.")
    assert run["status"] == "blocked" and run["state"]["intent"] == "scam" and not run["state"]["approval_id"]
    assert [m["direction"] for m in client.get("/messages").json()] == ["inbound"]


async def test_reply_below_price_floor_is_blocked(client, account):
    class Cheap(TestModels):
        async def complete(self, node, data, schema):
            result, usage = await super().complete(node, data, schema)
            if node == "liaison":
                result["text"] = "I would start this week for $20."
            return result, usage
    run = await turn(client, account["id"], "What is your best price?", model=Cheap())
    assert run["status"] == "blocked" and "minimum of $50" in run["state"]["compliance"]["reasons"][0]


async def test_events_drive_pipeline_and_outcome_memory(client, account):
    tenant = account["id"]
    MockMarketplace().configure(tenant, SimulatorConfig(reply_probability=1, interview_probability=1, hire_probability=1))
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    assert client.get("/pipeline").json()[0]["status"] == "drafted"
    assert (await approve(client, tenant, client.get(f"/runs/{run_id}").json()))["status"] == "submitted"
    for _ in range(4):
        assert client.post("/dev/advance").status_code == 200
    assert client.get("/pipeline").json()[0]["status"] == "hired"
    outcome = [m for m in client.get("/memory").json() if m["kind"] == "outcome"]
    assert outcome[0]["category"] == "backend" and len(outcome[0]["supporting_events"]) == 3
    assert any(r["kind"] == "conversation" and r["subject"] == "mock-api" for r in client.get("/runs").json())


async def test_learned_style_rule_sends_drafts_back_until_deleted(client, account):
    tenant = account["id"]
    promote(tenant, "style", "style:scope", {"kind": "style", "word": "scope", "rule": "Avoid this repeatedly removed word"})
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    blocked = client.get(f"/runs/{run_id}").json()
    assert blocked["status"] == "blocked" and "Avoid 'scope'" in blocked["state"]["critique"]["comments"][0]
    delete_memory(tenant, "style:scope")
    assert list_memory(tenant) == []
    run_id = client.post("/jobs/mock-web/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    assert client.get(f"/runs/{run_id}").json()["status"] == "awaiting_approval"
