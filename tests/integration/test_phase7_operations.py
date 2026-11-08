from dev_support.mock_marketplace.config import SimulatorConfig
from dev_support.mock_marketplace.service import MockMarketplace
from tests.support import TestModels, TestTools
from worker.runtime import process_run


async def analysed(client, tenant, job_id):
    run_id = client.post(f"/jobs/{job_id}/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), TestModels())
    return client.get(f"/runs/{run_id}").json()


async def submitted(client, tenant, job_id="mock-api"):
    run = await analysed(client, tenant, job_id)
    client.post(f"/approvals/{run['state']['approval_id']}/decision", json={"decision": "approve"})
    await process_run(run["id"], TestTools(tenant), TestModels())
    return run


def job(client, job_id):
    return next(item for item in client.get("/jobs").json() if item["id"] == job_id)


async def test_autonomy_archives_skips_but_never_sends(client, account):
    tenant = account["id"]
    assert client.put("/auth/profile", json={"auto_skip": False}).status_code == 200
    assert (await analysed(client, tenant, "mock-scam"))["status"] == "skip"
    scam = job(client, "mock-scam")
    assert scam["recommended_skip"] and not scam["skipped"]
    assert client.put("/auth/profile", json={"auto_skip": True}).status_code == 200
    assert job(client, "mock-scam")["skipped"]
    assert client.post("/jobs/mock-web/skip", json={"reason": "Not my stack"}).status_code == 200
    web = job(client, "mock-web")
    assert web["skipped"] and web["skip_reason"] == "Not my stack"
    assert (await analysed(client, tenant, "mock-api"))["status"] == "awaiting_approval"
    assert MockMarketplace().balance(tenant)["spent"] == 0


async def test_analytics_by_category_and_rejection_reasons(client, account):
    tenant = account["id"]
    MockMarketplace().configure(tenant, SimulatorConfig(reply_probability=1, interview_probability=1, hire_probability=0))
    await submitted(client, tenant)
    for _ in range(4):
        client.post("/dev/advance")
    other = await analysed(client, tenant, "mock-web")
    client.post(f"/approvals/{other['state']['approval_id']}/decision", json={"decision": "reject", "reason": "Too generic"})
    data = client.get("/analytics").json()
    assert data["by_category"] == [{"category": "backend", "submitted": 1, "replied": 1, "hired": 0,
                                    "connects_spent": 8, "reply_rate": 1.0, "hire_rate": 0.0}]
    assert data["rejection_reasons"] == [{"reason": "Too generic", "count": 1}]
    assert data["proposal_tokens"]["p50"] > 0 and data["proposal_active_seconds"]["p95"] > 0


async def test_replay_needs_new_approval_and_never_resubmits(client, account):
    tenant = account["id"]
    run = await submitted(client, tenant)
    assert MockMarketplace().balance(tenant)["spent"] == 8
    history = client.get(f"/runs/{run['id']}/checkpoints").json()
    writer = next(item for item in history if "writer" in item["next"])
    execute = next(item for item in history if "execute" in item["next"])
    assert client.post(f"/runs/{run['id']}/replay", json={"checkpoint_id": "missing"}).status_code == 404
    queued = client.post(f"/runs/{run['id']}/replay", json={"checkpoint_id": writer["checkpoint_id"]}).json()
    assert queued["status"] == "queued"
    await process_run(run["id"], TestTools(tenant), TestModels())
    replayed = client.get(f"/runs/{run['id']}").json()
    assert replayed["status"] == "awaiting_approval" and replayed["approval_status"] == "pending"
    assert replayed["state"]["approval_id"] != run["state"]["approval_id"]
    assert len(replayed["state"]["budget"]["replays"]) == 1
    client.post(f"/runs/{run['id']}/replay", json={"checkpoint_id": execute["checkpoint_id"]})
    await process_run(run["id"], TestTools(tenant), TestModels())
    assert client.get(f"/runs/{run['id']}").json()["status"] == "submitted"
    assert MockMarketplace().balance(tenant)["spent"] == 8


def test_scout_skips_duplicate_postings(account):
    from apps.api.db import get_record, transaction
    from worker.scout import duplicate_of
    jobs = {job.id: job.model_dump() for job in MockMarketplace().search(account["id"])}
    assert duplicate_of(account["id"], jobs["mock-api"]) is None
    assert duplicate_of(account["id"], jobs["mock-api"]) is None
    assert duplicate_of(account["id"], jobs["mock-api-duplicate"]) == "mock-api"
    with transaction() as db:
        assert get_record(db, account["id"], "duplicate_job", "mock-api-duplicate").value == {"of": "mock-api"}


async def test_retry_acknowledges_an_interrupted_step(client, account):
    from agent import budgets
    tenant = account["id"]
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    budgets.reserve(tenant, run_id, "writer")  # A step that was running when its worker died.
    await process_run(run_id, TestTools(tenant), TestModels())
    stuck = client.get(f"/runs/{run_id}").json()
    assert stuck["status"] == "needs_attention" and "unknown_model_usage" in stuck["state"]["error"]
    assert client.post(f"/runs/{run_id}/retry").status_code == 200
    await process_run(run_id, TestTools(tenant), TestModels())
    done = client.get(f"/runs/{run_id}").json()
    assert done["status"] == "awaiting_approval"
    assert done["state"]["budget"]["acknowledged"][0]["nodes"] == ["writer"]


async def test_models_never_see_marketplace_ids_or_evidence_hashes(client, account):
    import json
    seen = []

    class Recording(TestModels):
        async def complete(self, node, data, schema):
            seen.append(json.dumps(data))
            return await super().complete(node, data, schema)
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(account["id"]), Recording())
    assert client.get(f"/runs/{run_id}").json()["status"] == "awaiting_approval"
    assert seen and not any(marker in data for data in seen for marker in ("mock-api", "mock-client", "content_hash", account["id"]))


async def test_planted_instructions_raise_risk_without_forcing_a_skip(client, account):
    run_id = client.post("/jobs/mock-injection/analyse").json()["id"]
    await process_run(run_id, TestTools(account["id"]), TestModels())
    state = client.get(f"/runs/{run_id}").json()["state"]
    assert "prompt_injection" in state["risk"]["flags"] and state["risk"]["score"] == 0.5
    assert state["decision"]["action"] == "bid"


async def test_pricing_stays_in_the_budget_range_and_sees_client_history(client, account):
    seen = {}

    class LowBidder(TestModels):
        async def complete(self, node, data, schema):
            result, usage = await super().complete(node, data, schema)
            if node == "pricing":
                seen.update(data)
                result["amount"] = 50
            return result, usage
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(account["id"]), LowBidder())
    state = client.get(f"/runs/{run_id}").json()["state"]
    assert seen["bid_range"] == [540, 900]
    assert seen["client"] == {"total_spend": 4000.0, "hires": 8, "average_paid_per_hire": 500}
    assert state["price"]["amount"] == 540


async def test_connects_not_worth_spending_moves_the_job_to_watch(client, account, monkeypatch):
    from agent.model import config
    monkeypatch.setitem(config()["pricing"], "min_return", 1000)
    run = await analysed(client, account["id"], "mock-api")
    assert run["status"] == "watch" and not run["state"].get("draft")
    assert run["state"]["decision"] == {"action": "watch", "reason": "Expected value does not justify the Connects cost"}
    assert MockMarketplace().balance(account["id"])["spent"] == 0
