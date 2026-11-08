"""Durable per-thread budget accounting, separate from graph state and audit traces."""
from pydantic import ValidationError
from sqlalchemy import select, text

from agent.errors import BudgetExceeded
from agent.handoffs import NodeUsage
from agent.model import config
from apps.api.db import Event, Run, get_record, put_record, transaction


def _locked(db, tenant, run_id):
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    run = db.scalar(select(Run).where(Run.id == run_id, Run.tenant == tenant).with_for_update())
    if not run:
        raise PermissionError("Budget thread is not owned by this tenant")
    row = get_record(db, tenant, "run_budget", run_id)
    return row.value if row else {"steps": 0, "tokens": 0, "api_usd": 0.0,
                                  "active_seconds": 0.0, "usage_complete": True}


def exceeded(value, *, before=False):
    limits = config()["budgets"]
    reasons = []
    for field in ("steps", "tokens", "active_seconds", "api_usd"):
        if value[field] > limits[field] or (before and value[field] >= limits[field]):
            reasons.append(field)
    if not value["usage_complete"]:
        reasons.append("unknown_model_usage")
    return reasons


def reserve(tenant, run_id, node):
    with transaction() as db:
        value = dict(_locked(db, tenant, run_id))
        reasons = exceeded(value, before=True)
        if reasons:
            raise BudgetExceeded(f"{node}: execution budget exhausted ({', '.join(reasons)})")
        value["steps"] += 1
        value["pending"] = {**value.get("pending", {}), node: True}
        put_record(db, tenant, "run_budget", run_id, value)
        run = db.get(Run, run_id)
        db.add(Event(tenant=tenant, run_id=run_id, trace_id=run.trace_id,
                     name="node:started", payload={"node": node, "phase": "started"}))
        return value


def observe(tenant, run_id, elapsed, usage, node="unspecified"):
    try:
        usage = [NodeUsage.model_validate(u).model_dump() for u in usage]
    except ValidationError:
        usage = [NodeUsage(node=node, model="unreported", tokens=0, usage_complete=False).model_dump()]
    with transaction() as db:
        value = dict(_locked(db, tenant, run_id))
        value["tokens"] += sum(u["tokens"] for u in usage)
        value["api_usd"] += sum(u["api_usd"] or 0 for u in usage)
        value["active_seconds"] += elapsed
        value["usage_complete"] &= all(u["usage_complete"] for u in usage)
        value["pending"] = {k: v for k, v in value.get("pending", {}).items() if k != node}
        put_record(db, tenant, "run_budget", run_id, value)
        run = db.get(Run, run_id)
        db.add(Event(tenant=tenant, run_id=run_id, trace_id=run.trace_id,
                     name=f"budget:{node}", payload={"usage": usage, "active_seconds": elapsed,
                                                    "totals": value}))
        return value


def recover(tenant, run_id):
    """An unfinished reservation after process death has unreported usage.

    Do not invent a zero-cost result or reset counters. Existing effects can still
    be reconciled, but further generation/writes require operator attention.
    """
    with transaction() as db:
        value = dict(_locked(db, tenant, run_id))
        if value.get("pending"):
            value["usage_complete"] = False
            value["interrupted_nodes"] = sorted(value["pending"])
            value["pending"] = {}
            put_record(db, tenant, "run_budget", run_id, value)


def read(tenant, run_id):
    with transaction() as db:
        row = get_record(db, tenant, "run_budget", run_id)
        return row.value if row else {}
