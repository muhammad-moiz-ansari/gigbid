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
