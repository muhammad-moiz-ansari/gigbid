from contextlib import asynccontextmanager

import pytest
from mcp.types import CallToolResult, TextContent

import apps.api.auth.upwork as upwork_auth
import mcp_servers.marketplace.adapters.upwork_live as live
from agent.handoffs import Action, JobSpec, WriteRequest
from agent.marketplace_port import AmbiguousWrite, Unavailable
from apps.api.approvals import binding
from apps.api.config import settings
from apps.api.db import Approval, Event, Run, get_record, put_record, transaction

# Shapes as returned by Upwork's MCP server on 2026-11-08 (docs/checks/upwork-signin.json).
JOB = {"id": "123", "title": "Python API", "description_snippet": "Build an API", "skills": ["Python", "FastAPI"],
       "budget": "$500", "duration": "1 to 3 months", "client": {"total_spent": 4000, "verification_status": "VERIFIED"}}
DETAIL = {"connects_cost": 8, "client_record": {"jobs_with_hires": 5}, "data": {"marketplaceJobPosting": {
    "id": "123", "content": {"title": "Python API", "description": "Build a FastAPI service."},
    "contractTerms": {"fixedPriceContractTerms": {"amount": {"rawValue": "500.0", "currency": "USD"}}}}}}


@pytest.fixture
def upwork(monkeypatch):
    """A stand-in for Upwork's MCP server that records every tool call."""
    calls, replies = [], {
        "upwork__list_accounts": {"accounts": [{"org_uid": "org-1", "role": "TALENT"}]},
        "upwork__find_jobs": {"jobs": [JOB]}, "upwork__get_profile": {"balance": {"connectsBalance": 42}},
        "upwork__list_freelancer_proposals": {"data": {"vendorProposals": {"edges": []}}},
        "upwork__get_messages": {"data": {"rooms": []}},
        "upwork__manage_proposals": {"preview_id": "preview-1"}, "upwork__send_message": {"story_id": "story-1"}}

    class Session:
        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            reply = DETAIL if arguments.get("action") == "get" else replies[name]
            if isinstance(reply, Exception):
                raise reply
            return CallToolResult(content=[TextContent(type="text", text="ok")], structuredContent=reply)

    class Client:
        def __init__(self, connections):
            assert connections["upwork"]["headers"] == {"Authorization": "Bearer user-token"}

        @asynccontextmanager
        async def session(self, name):
            yield Session()

    async def token(tenant):
        return "user-token"
    monkeypatch.setattr(live, "MultiServerMCPClient", Client)
    monkeypatch.setattr(upwork_auth, "access_token", token)
    return calls, replies


def test_live_reads_map_onto_the_port(account, upwork):
    calls, _ = upwork
    adapter, tenant = live.UpworkAdapter(), account["id"]
    found = adapter.search(tenant, "python")
    assert found == [JobSpec(id="123", title="Python API", description="Build an API", skills=["Python", "FastAPI"],
                             budget=500, connects=0, client_id="123")]
    job = adapter.job(tenant, "123")
    assert (job.connects, job.budget, job.skills, job.description) == (8, 500, ["Python", "FastAPI"], "Build a FastAPI service.")
    assert adapter.client_history(tenant, "123") == {"id": "123", "verified": True, "spend": 4000.0, "hires": 5, "synthetic": False}
    assert adapter.balance(tenant)["balance"] == 42
    assert all(args.get("org_uid") == "org-1" for name, args in calls if name != "upwork__list_accounts")
    with pytest.raises(PermissionError, match="set_tool_permission"):
        adapter._call(tenant, "set_tool_permission", "set")


def approved(tenant, preview, run_id="run-1"):
    with transaction() as db:
        db.add(Run(id=run_id, tenant=tenant, subject="123", kind="bid", state={}, status="running"))
        approval = Approval(tenant=tenant, run_id=run_id, decision="approved", binding=binding(run_id, preview),
                            payload=preview)
        db.add(approval)
        db.flush()
        return approval.id


def proposal(approval_id=None, key="run-1:proposal:v1"):
    text = "I built a FastAPI service.\n\nScreening question: How will you test?\nI would add integration tests."
    return WriteRequest(action=Action(kind="proposal", destination="123", text=text, price=450),
                        run_id="run-1", approval_id=approval_id, idempotency_key=key, dry_run=False)


def test_a_live_proposal_is_only_a_draft_and_needs_an_approval(account, upwork):
    calls, _ = upwork
    adapter, tenant = live.UpworkAdapter(), account["id"]
    with pytest.raises(PermissionError):
        adapter.write(tenant, proposal())
    assert not [c for c in calls if c[0] == "upwork__manage_proposals"]
    adapter.search(tenant, "python")  # live jobs come from a search, which caches the posted duration
    preview = adapter.write(tenant, proposal().model_copy(update={"dry_run": True})).model_dump()
    assert preview["connects_cost"] == 8 and preview["status"] == "preview"
    preview.pop("effect_id")
    request = proposal(approved(tenant, preview))
    result = adapter.write(tenant, request)
    assert (result.status, result.effect_id, result.connects_cost) == ("drafted", "preview-1", 8)
    created = next(args for name, args in calls if name == "upwork__manage_proposals")
    assert created["action"] == "create" and created["params"] == {
        "job_reference": "123", "cover_letter": "I built a FastAPI service.", "charged_amount": 450,
        "answers": [{"question": "How will you test?", "answer": "I would add integration tests."}],
        "estimated_duration": "1_to_3_months", "payment_mode": "by_project"}
    assert preview["terms"] == {"estimated_duration": "1_to_3_months", "payment_mode": "by_project"}
    assert adapter.write(tenant, request) == result and len([c for c in calls if c[0] == "upwork__manage_proposals"]) == 1
    with transaction() as db:
        assert db.get(Approval, request.approval_id).consumed


def test_a_refused_write_can_retry_but_an_unknown_one_cannot(account, upwork):
    _, replies = upwork
    adapter, tenant = live.UpworkAdapter(), account["id"]
    preview = adapter.write(tenant, proposal().model_copy(update={"dry_run": True})).model_dump()
    preview.pop("effect_id")
    request = proposal(approved(tenant, preview))
    replies["upwork__manage_proposals"] = {"status": "terms_required", "next_step": "Ask how they want to be paid"}
    with pytest.raises(Unavailable, match="built no draft: Ask how they want to be paid"):
        adapter.write(tenant, request)
    replies["upwork__manage_proposals"] = Unavailable("Upwork refused the request")
    with pytest.raises(Unavailable):
        adapter.write(tenant, request)
    with transaction() as db:
        assert get_record(db, tenant, "idempotency", request.idempotency_key) is None
        put_record(db, tenant, "idempotency", request.idempotency_key, {"in_flight": True})
    with pytest.raises(AmbiguousWrite):
        adapter.write(tenant, request)


async def test_disconnect_purges_upwork_data_in_live_mode(account, monkeypatch):
    from worker.retention import purge
    tenant = account["id"]
    with transaction() as db:
        db.add(Run(id="live-run", tenant=tenant, subject="123", kind="bid", state={"job": {"title": "x"}}, status="drafted"))
        db.add(Event(tenant=tenant, run_id="live-run", trace_id="t", name="node:intake", payload={}))
        put_record(db, tenant, "upwork_cache", "123", {"skills": ["Python"], "at": 0})
        put_record(db, tenant, "style", "kept", {"word": "passionate"})
    assert await purge(tenant) == 1
    with transaction() as db:
        assert db.get(Run, "live-run") is None and get_record(db, tenant, "upwork_cache", "123") is None
        assert get_record(db, tenant, "style", "kept")


def test_live_inbox_is_not_ranked_or_archived(client, account, monkeypatch):
    import apps.api.routers.workflow as workflow
    jobs = [JobSpec(id=f"job-{i}", title=f"Job {i}", description="d", skills=["Python"], budget=500, connects=8,
                    client_id="c") for i in (1, 2)]
    monkeypatch.setattr(workflow, "marketplace", lambda: type("Fake", (), {"search": lambda self, t, q: jobs})())
    with transaction() as db:
        db.add(Run(tenant=account["id"], subject="job-2", kind="bid", status="skip",
                   state={"fit": {"score": 0.9}, "decision": {"action": "skip", "reason": "Risky"}}))
    assert [j["id"] for j in client.get("/jobs").json()] == ["job-2", "job-1"]
    monkeypatch.setattr(settings(), "marketplace_mode", "upwork")
    live_jobs = client.get("/jobs").json()
    assert [j["id"] for j in live_jobs] == ["job-1", "job-2"] and not any(j["skipped"] for j in live_jobs)


def test_policy_acknowledgement_only_runs_from_the_settings_endpoint(client, account, upwork):
    calls, _ = upwork
    assert client.post("/integrations/upwork/acknowledge-policy").json() == {"acknowledged": True}
    acknowledged = [args for name, args in calls if name == "upwork__manage_proposals"]
    assert acknowledged == [{"action": "acknowledge_policy", "org_uid": "org-1", "params": {}}]
