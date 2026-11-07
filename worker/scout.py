from sqlalchemy import select

from agent.mcp_client import gateway
from agent.model import config
from apps.api.auth.service import issue_session, token_hash
from apps.api.config import settings
from apps.api.db import Session, User, get_record, now, put_record, transaction, uid
from apps.api.routers.workflow import enqueue
from worker.pipeline import apply_events


async def scout_all():
    with transaction() as db:
        users = list(db.scalars(select(User)))
    for user in users:
        minimum = config()["scheduling"]["mock_min_interval_seconds" if settings().marketplace_mode == "mock"
                                         else "live_min_interval_seconds"]
        interval = max(minimum, user.profile.get("interval_seconds", 14400))
        with transaction() as db:
            last = get_record(db, user.id, "schedule", "scout")
            if last and now() - last.value["last"] < interval:
                continue
            token, _ = issue_session(db, user.id)
            put_record(db, user.id, "schedule", "scout", {"last": now()})
        try:
            async with gateway(token, uid()) as tools:
                jobs = await tools.call("scout", "search_jobs", {"query": user.profile.get("saved_query", "")})
                for job in jobs:
                    enqueue(user.id, job["id"])
                apply_events(user.id, await tools.call("scout", "list_events", {"after": 0}))
        except Exception:
            # Scheduled failure remains inspectable and does not authorize writes.
            with transaction() as db:
                put_record(db, user.id, "schedule", "scout", {"last": now(), "status": "marketplace_unavailable"})
        finally:
            with transaction() as db:
                session = db.get(Session, token_hash(token))
                if session:
                    db.delete(session)
