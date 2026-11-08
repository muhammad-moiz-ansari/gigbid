import asyncio
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from langgraph.types import Command
from sqlalchemy import select

from agent import budgets
from agent.checkpoints import checkpointer, thread_config, thread_lock
from agent.graphs.bid_graph import build_bid_graph
from agent.model import config
from apps.api.db import Approval, Record, Run, get_record, transaction
from dev_support.mock_marketplace.service import MockMarketplace
from tests.support import TestModels, TestTools
from worker.runtime import process_run


async def pending(client, tenant, model=None, tools=None):
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, tools or TestTools(tenant), model or TestModels())
    result = client.get(f"/runs/{run_id}").json()
    assert result["status"] == "awaiting_approval", result["state"].get("error")
    return run_id, result["state"]


@pytest.mark.asyncio
async def test_forged_interrupt_resume_cannot_authorize(client, account):
    tenant = account["id"]
    run_id, state = await pending(client, tenant)
    async with checkpointer() as saver:
        graph = build_bid_graph(TestTools(tenant), TestModels(), saver)
        with pytest.raises(PermissionError, match="persisted human decision"):
            await graph.ainvoke(Command(resume={"decision": "approve"}), thread_config(tenant, run_id))
    assert MockMarketplace().balance(tenant)["spent"] == 0
    with transaction() as db:
        assert db.get(Approval, state["approval_id"]).decision == "pending"


@pytest.mark.asyncio
async def test_forged_database_approval_without_receipt_cannot_write(client, account):
    tenant = account["id"]
    run_id, state = await pending(client, tenant)
    from agent.nodes.workflow import Nodes
    request = Nodes(None, None).request(state).model_copy(update={"dry_run": False})
    with transaction() as db:
        db.get(Approval, state["approval_id"]).decision = "approved"
    with pytest.raises(PermissionError, match="persisted human decision"):
        MockMarketplace().write(tenant, request)
    assert MockMarketplace().balance(tenant)["spent"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["job", "profile", "policy"])
async def test_material_context_change_blocks_write(client, account, monkeypatch, field):
    tenant = account["id"]
    run_id, state = await pending(client, tenant)
    client.post(f'/approvals/{state["approval_id"]}/decision', json={"decision": "approve"})
    if field == "policy":
        monkeypatch.setitem(config()["policy"], "version", "changed-during-pause")
    else:
        with transaction() as db:
            if field == "job":
                job = get_record(db, tenant, "job", "mock-api")
                job.value = {**job.value, "description": "Materially different requirements"}
            else:
                from apps.api.db import User
                user = db.get(User, tenant)
                user.profile = {**user.profile, "floor_fixed": 999}
    await process_run(run_id, TestTools(tenant), TestModels())
    assert client.get(f"/runs/{run_id}").json()["status"] == "recoverable"
    assert MockMarketplace().balance(tenant)["spent"] == 0


@pytest.mark.asyncio
async def test_decision_race_has_one_receipt(client, account):
    _, state = await pending(client, account["id"])
    def decide(decision):
        return client.post(f'/approvals/{state["approval_id"]}/decision',
                           json={"decision": decision, "reason": "Review decision"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(decide, ["approve", "reject"]))
    assert sorted(codes) == [200, 409]
    with transaction() as db:
        receipts = list(db.scalars(select(Record).where(Record.kind == "approval_receipt")))
        assert len(receipts) == 1


@pytest.mark.asyncio
async def test_edit_is_saved_as_diff_and_cannot_reset_revisions(client, account):
    run_id, state = await pending(client, account["id"])
    text = "Proposed approach: I would test authorization."
    client.post(f'/approvals/{state["approval_id"]}/decision', json={"decision": "edit", "text": text})
    await process_run(run_id, TestTools(account["id"]), TestModels())
    edited = client.get(f"/runs/{run_id}").json()
    assert edited["status"] == "awaiting_approval"
    assert edited["state"]["draft"]["version"] == 2
    assert edited["state"]["approval_id"] != state["approval_id"]
    with transaction() as db:
        saved = get_record(db, account["id"], "draft_edit", state["approval_id"]).value
        assert saved["before"] == state["draft"]["text"] and saved["after"] == text
        assert "--- before" in saved["diff"] and "+Proposed approach" in saved["diff"]


@pytest.mark.asyncio
async def test_parallel_fanout_barrier_and_two_verified_rewrites(client, account):
    started = set()
    ready = asyncio.Event()
    class Models(TestModels):
        writes = 0
        critiques = 0
        async def complete(self, node, data, schema):
            if node in ("analyst", "risk"):
                started.add(node)
                if len(started) == 2:
                    ready.set()
                await asyncio.wait_for(ready.wait(), 2)
            result, usage = await super().complete(node, data, schema)
            if node == "writer":
                self.writes += 1
                result["text"] += "\n\nProposed approach: I would use my 20 years of experience."
            if node == "critic":
                self.critiques += 1
                assert "20 years" not in data["draft"]["text"]
                result = {"passed": self.critiques > 2, "comments": ["Revise"]}
            return result, usage
    class Tools(TestTools):
        async def call(self, role, name, args):
            if role == "matcher":
                await asyncio.wait_for(ready.wait(), 2)
            return await super().call(role, name, args)
    model = Models()
    _, state = await pending(client, account["id"], model, Tools(account["id"]))
    assert model.writes == model.critiques == 3
    assert state["revision"] == 2 and state["draft"]["version"] == 3
    assert {a["role"] for a in state["analyses"]} == {"analyst", "risk", "matcher"}


@pytest.mark.asyncio
async def test_third_failed_critique_blocks_without_fourth_draft(client, account):
    class Models(TestModels):
        writes = 0
        async def complete(self, node, data, schema):
            result, usage = await super().complete(node, data, schema)
            if node == "writer":
                self.writes += 1
            if node == "critic":
                result = {"passed": False, "comments": ["Still insufficient"]}
            return result, usage
    model = Models()
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(account["id"]), model)
    state = client.get(f"/runs/{run_id}").json()
    assert state["status"] == "blocked" and model.writes == 3
    assert state["state"]["revision"] == 3 and client.get("/approvals").json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field,limit", [("steps", 3), ("tokens", 15), ("api_usd", .001), ("active_seconds", .001)])
async def test_budget_limits_survive_retry(client, account, monkeypatch, field, limit):
    monkeypatch.setitem(config()["budgets"], field, limit)
    class Models(TestModels):
        async def complete(self, node, data, schema):
            result, usage = await super().complete(node, data, schema)
            usage["api_usd"] = .01
            return result, usage
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(account["id"]), Models())
    result = client.get(f"/runs/{run_id}").json()
    assert result["status"] == "needs_attention", result
    before = budgets.read(account["id"], run_id)
    assert before["steps"] > 0 and MockMarketplace().balance(account["id"])["spent"] == 0
    client.post(f"/runs/{run_id}/retry")
    await process_run(run_id, TestTools(account["id"]), Models())
    after = budgets.read(account["id"], run_id)
    assert after["steps"] >= before["steps"] and after["tokens"] >= before["tokens"]
    assert client.get(f"/runs/{run_id}").json()["status"] == "needs_attention"


@pytest.mark.asyncio
async def test_crash_after_commit_reconciles_in_new_worker_process(client, account):
    tenant = account["id"]
    run_id, state = await pending(client, tenant)
    client.post(f'/approvals/{state["approval_id"]}/decision', json={"decision": "approve"})
    args = [sys.executable, "-m", "tests.integration.graph_worker_process", run_id, tenant]
    crash = await asyncio.to_thread(subprocess.run, [*args, "crash"], capture_output=True, timeout=60)
    assert crash.returncode == 73, crash.stderr.decode(errors="replace")
    assert MockMarketplace().balance(tenant)["spent"] == 8
    with transaction() as db:
        run = db.get(Run, run_id)
        assert run.status == "running"
        run.lease_until = 0
    resumed = await asyncio.to_thread(subprocess.run, args, capture_output=True, timeout=60)
    assert resumed.returncode == 0, resumed.stderr.decode(errors="replace")
    result = client.get(f"/runs/{run_id}").json()
    assert result["status"] == "submitted", result["state"].get("error")
    assert MockMarketplace().balance(tenant)["spent"] == 8
    with transaction() as db:
        assert len(list(db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == "proposal")))) == 1
    assert budgets.read(tenant, run_id)["usage_complete"] is False


@pytest.mark.asyncio
async def test_restart_preserves_successful_parallel_branch_writes(client, account):
    class Models(TestModels):
        def __init__(self, fail=False):
            self.fail, self.calls = fail, []
        async def complete(self, node, data, schema):
            self.calls.append(node)
            if self.fail and node == "analyst":
                await asyncio.sleep(.1)  # Other branches complete and persist first.
                raise RuntimeError("Transient analysis failure")
            return await super().complete(node, data, schema)
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(account["id"]), Models(fail=True))
    assert client.get(f"/runs/{run_id}").json()["status"] == "recoverable"
    client.post(f"/runs/{run_id}/retry")
    resumed = Models()
    await process_run(run_id, TestTools(account["id"]), resumed)
    assert client.get(f"/runs/{run_id}").json()["status"] == "awaiting_approval"
    assert "analyst" in resumed.calls and "risk" not in resumed.calls


@pytest.mark.asyncio
async def test_pipeline_failure_preserves_pending_approval(client, account):
    class Tools(TestTools):
        async def call(self, role, name, args):
            if name == "list_events":
                raise RuntimeError("Event feed unavailable")
            return await super().call(role, name, args)
    await pending(client, account["id"], tools=Tools(account["id"]))


@pytest.mark.asyncio
async def test_screening_keys_cannot_launder_fabricated_achievements(client, account):
    class Models(TestModels):
        async def complete(self, node, data, schema):
            result, usage = await super().complete(node, data, schema)
            if node == "writer":
                result["screening_answers"] = {**result["screening_answers"], "I have built 50 production systems.":
                    "Proposed approach: I would test authorization."}
            return result, usage
    _, state = await pending(client, account["id"], model=Models())
    assert "I have built 50 production systems." not in state["draft"]["screening_answers"]
    assert state["verification"]["unsupported_before"] == 1
    assert "50 production" not in state["preview"]["payload"]["text"]


@pytest.mark.asyncio
async def test_thread_lock_rejects_competing_worker(account):
    async with thread_lock(account["id"], "same-run") as first:
        async with thread_lock(account["id"], "same-run") as second:
            assert first and not second


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("GIGBID_TEST_POSTGRES_CHECKPOINT_URL"),
                    reason="Real Postgres checkpoint service not configured")
async def test_real_postgres_checkpoint_restart(client, account, monkeypatch):
    from apps.api.config import settings
    monkeypatch.setattr(settings(), "checkpoint_url", os.environ["GIGBID_TEST_POSTGRES_CHECKPOINT_URL"])
    run_id, state = await pending(client, account["id"])
    client.post(f'/approvals/{state["approval_id"]}/decision', json={"decision": "approve"})
    await process_run(run_id, TestTools(account["id"]), TestModels())
    assert client.get(f"/runs/{run_id}").json()["status"] == "submitted"

