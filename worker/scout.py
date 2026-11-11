from agent.model import config
from apps.api.config import settings
from apps.api.db import digest, get_record, put_record, transaction
from apps.api.routers.workflow import enqueue
from worker.pipeline import sync
from worker.schedule import due, failed, tools_for, users


def duplicate_of(tenant, job):
    """The same title, description and client under another id is a duplicate posting."""
    fingerprint = digest({key: str(job[key]).casefold().strip() for key in ("title", "description", "client_id")})
    with transaction() as db:
        seen = get_record(db, tenant, "job_fingerprint", fingerprint)
        if seen and seen.value["job_id"] != job["id"]:
            put_record(db, tenant, "duplicate_job", job["id"], {"of": seen.value["job_id"]})
            return seen.value["job_id"]
        put_record(db, tenant, "job_fingerprint", fingerprint, {"job_id": job["id"]})
        return None


async def scout_all():
    mode = "mock" if settings().marketplace_mode == "mock" else "live"
    minimum = config()["scheduling"][f"{mode}_min_interval_seconds"]
    for user in users():
        if not due(user.id, "scout", max(minimum, user.profile.get("interval_seconds", 14400))):
            continue
        try:
            async with tools_for(user.id) as tools:
                for job in await tools.call("scout", "search_jobs", {"query": user.profile.get("saved_query", "")}):
                    if not duplicate_of(user.id, job):
                        enqueue(user.id, job["id"])
                await sync(user.id, tools)
        except Exception as exc:
            # A failed scheduled search stays inspectable and never authorizes writes.
            failed(user.id, "scout", exc)
