import time

from langgraph.types import Command
from sqlalchemy import or_, select, update

from agent.checkpoints import checkpointer, thread_config
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.mcp_client import gateway
from agent.memory.promotion_rules import style_candidates
from agent.memory.store import load_store, promote
from agent.model import OpenModel
from agent.nodes.workflow import BudgetExceeded
from apps.api.auth.service import issue_session, token_hash
from apps.api.db import Event, Record, Run, Session, User, now, put_record, transaction
from apps.api.safety import redact
from worker.pipeline import apply_events


def record_event(tenant, run_id, name, payload, trace_id):
    with transaction() as db:
        db.add(Event(tenant=tenant, run_id=run_id, name=name, payload=redact(payload), trace_id=trace_id))


async def process_run(run_id, tool_gateway=None, model=None):
    with transaction() as db:
        claimed = db.execute(update(Run).where(Run.id == run_id,
            or_(Run.status == "queued", (Run.status == "running") & (Run.lease_until < now())))
            .values(status="running", lease_until=now() + 300))
        if not claimed.rowcount:
            return
        run = db.get(Run, run_id)
        tenant, kind, subject, trace_id = run.tenant, run.kind, run.subject, run.trace_id
        resume = run.resume
        user = db.get(User, tenant)
        profile = user.profile
        token, _ = issue_session(db, tenant)
    started = time.monotonic()
    record_event(tenant, run_id, "worker:started", {"kind": kind}, trace_id)
    try:
        async with checkpointer() as saver:
            async def execute(tools):
                graph = (build_bid_graph if kind == "bid" else build_conversation_graph)(tools, model or OpenModel(), saver)
                cfg = thread_config(tenant, run_id)
                snapshot = await graph.aget_state(cfg)
                if resume and resume.get("decision") == "renew":
                    draft = dict(snapshot.values["draft"])
                    draft["version"] += 1
                    await graph.aupdate_state(cfg, {"draft": draft, "revision": 0},
                                              as_node="writer" if kind == "bid" else "draft")
                    value = None
                elif resume:
                    value = Command(resume=resume)
                elif snapshot.values:
                    value = None
                else:
                    memory = load_store(tenant)
                    value = {"tenant": tenant, "run_id": run_id, "job": {"id": subject},
                             "profile": profile, "analyses": [], "usage": [], "steps": 0,
                             "active_seconds": 0.0, "revision": 0,
                             "memory": [entry.value for entry in memory.search((tenant, "style"))]}
                    if kind == "conversation":
                        value["conversation"] = subject
                async for change in graph.astream(value, cfg, stream_mode="updates", durability="sync"):
                    for node, payload in change.items():
                        if node != "__interrupt__":
                            record_event(tenant, run_id, f"node:{node}", {
                                "completed": True, "status": payload.get("status"),
                                "usage": payload.get("usage", []), "steps": payload.get("steps", 0)}, trace_id)
                    with transaction() as db:
                        db.get(Run, run_id).lease_until = now() + 300
                final = await graph.aget_state(cfg)
                state = dict(final.values)
                status = "awaiting_approval" if final.next and state.get("approval_id") else state.get("status", "needs_attention")
                with transaction() as db:
                    r = db.get(Run, run_id)
                    r.state, r.status, r.resume, r.lease_until = state, status, None, 0
                    if state.get("edit"):
                        put_record(db, tenant, "edit_observation", run_id,
                                   {**state["edit"], "run_id": run_id, "approved": status in ("submitted", "sent")})
                if status in ("submitted", "sent"):
                    with transaction() as db:
                        edits = [r.value for r in db.scalars(select(Record).where(Record.tenant == tenant,
                                  Record.kind == "edit_observation")) if r.value.get("approved")]
                    for candidate in style_candidates(edits):
                        promote(tenant, candidate)
                events = await tools.call("scout", "list_events", {"after": 0})
                apply_events(tenant, events)
                record_event(tenant, run_id, "worker:finished", {"status": status,
                             "latency_seconds": time.monotonic() - started}, trace_id)
            if tool_gateway:
                await execute(tool_gateway)
            else:
                async with gateway(token, trace_id) as tools:
                    await execute(tools)
    except Exception as exc:
        status = "needs_attention" if isinstance(exc, (BudgetExceeded, ValueError)) else "recoverable"
        with transaction() as db:
            run = db.get(Run, run_id)
            run.status, run.lease_until = status, 0
            run.state = {**run.state, "error": str(redact(str(exc))), "error_type": type(exc).__name__}
        record_event(tenant, run_id, "worker:error", {"type": type(exc).__name__, "message": str(exc),
                                                    "status": status}, trace_id)
    finally:
        with transaction() as db:
            session = db.get(Session, token_hash(token))
            if session:
                db.delete(session)


async def drain_once():
    with transaction() as db:
        ids = list(db.scalars(select(Run.id).where(or_(Run.status == "queued",
            (Run.status == "running") & (Run.lease_until < now()))).order_by(Run.created).limit(10)))
    for run_id in ids:
        await process_run(run_id)
    return len(ids)
