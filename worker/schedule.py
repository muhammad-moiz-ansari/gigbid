"""Per-user schedules and short-lived tool sessions for background work."""
from contextlib import asynccontextmanager

from sqlalchemy import select

from agent.mcp_client import gateway
from apps.api.auth.service import issue_session, token_hash
from apps.api.db import Session, User, get_record, now, put_record, transaction, uid


def users():
    with transaction() as db:
        return list(db.scalars(select(User)))


def due(tenant, name, seconds):
    """Claims the next slot of a schedule; true when the task should run now."""
    with transaction() as db:
        last = get_record(db, tenant, "schedule", name)
        if last and now() - last.value["last"] < seconds:
            return False
        put_record(db, tenant, "schedule", name, {"last": now()})
        return True


def failed(tenant, name, error):
    with transaction() as db:
        put_record(db, tenant, "schedule", name, {"last": now(), "status": type(error).__name__})


@asynccontextmanager
async def tools_for(tenant):
    with transaction() as db:
        token, _ = issue_session(db, tenant)
    try:
        async with gateway(token, uid()) as tools:
            yield tools
    finally:
        with transaction() as db:
            session = db.get(Session, token_hash(token))
            if session:
                db.delete(session)
