"""Upwork API & MCP Terms retention in live mode: cached search details expire after 24 hours (8.3),
live runs after 30 days (8.6), and all Upwork-derived data is deleted when the user disconnects (8.7)."""
from sqlalchemy import select

from agent.checkpoints import checkpointer
from apps.api.config import settings
from apps.api.db import Approval, Event, Record, Run, now, transaction
from worker.schedule import due, users

# Records that hold Upwork content or ids; style memory from the user's own edits is kept.
UPWORK_KINDS = ("upwork_cache", "upwork_org", "pipeline", "seen_event", "event_cursor", "job_skip", "run_budget",
                "approval_context", "approval_receipt", "draft_edit", "idempotency")


async def purge(tenant, older_than=None):
    """Deletes this user's live runs (with their events, approvals and checkpoints) and Upwork records.

    Without older_than (disconnect) everything goes; with it, only older runs and expired cache entries.
    """
    cutoff = now() - older_than if older_than else None
    with transaction() as db:
        runs = [r.id for r in db.scalars(select(Run).where(Run.tenant == tenant)) if cutoff is None or r.created < cutoff]
        if cutoff is None:
            records = list(db.scalars(select(Record).where(Record.tenant == tenant, Record.kind.in_(UPWORK_KINDS))))
        else:
            records = [r for r in db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == "upwork_cache"))
                       if now() - r.value["at"] > 24 * 3600]
        for model in (Event, Approval):
            records += list(db.scalars(select(model).where(model.tenant == tenant, model.run_id.in_(runs))))
        for row in records + list(db.scalars(select(Run).where(Run.id.in_(runs)))):
            db.delete(row)
    async with checkpointer() as saver:
        await saver.setup()  # A fresh SQLite database has no checkpoint tables yet.
        for run_id in runs:
            await saver.adelete_thread(f"{tenant}:{run_id}")
    return len(runs)


async def purge_all():
    """Hourly in live mode: expire cached details and runs older than 30 days for every user."""
    if settings().marketplace_mode != "upwork":
        return
    for user in users():
        if due(user.id, "upwork_retention", 3600):
            await purge(user.id, older_than=30 * 24 * 3600)
