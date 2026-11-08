"""Marketplace events drive the pipeline board, outcome memory and replies to new client messages."""
from sqlalchemy import select

from agent.categories import category
from agent.memory.promotion_rules import outcome_candidate
from agent.memory.store import promote
from agent.model import config
from apps.api.config import settings
from apps.api.conversations import queue_reply
from apps.api.db import Record, Run, get_record, now, put_record, transaction
from dev_support.mock_marketplace.service import MockMarketplace
from worker.schedule import due, failed, tools_for, users

ORDER = {"drafted": 0, "submitted": 1, "viewed": 2, "replied": 3,
         "interview": 4, "hired": 5, "lost": 5}
FINAL = ("hired", "lost")
OUTCOMES = ("replied", "interview", "hired", "lost")


def mark(db, tenant, subject, status, event_id=None, synthetic=True):
    """Statuses only move forward; hired and lost are final."""
    prior = get_record(db, tenant, "pipeline", subject)
    if prior and (prior.value["status"] in FINAL or ORDER[status] < ORDER[prior.value["status"]]):
        return
    put_record(db, tenant, "pipeline", subject, {"subject": subject, "status": status, "event_id": event_id,
                                                 "synthetic": synthetic, "updated": now()})


def observe(db, tenant, event):
    """Records an outcome under the job's category; raw events never become memory directly."""
    run = db.scalar(select(Run).where(Run.tenant == tenant, Run.kind == "bid", Run.subject == event["subject"]))
    group = category(run.state.get("job", {}).get("skills", []) if run else [])
    put_record(db, tenant, "outcome_observation", event["id"], {"event_id": event["id"], "category": group,
                                                                 "status": event["status"], "job_id": event["subject"]})
    return group


def learn_outcomes(tenant, group):
    with transaction() as db:
        rows = [r.value for r in db.scalars(select(Record).where(Record.tenant == tenant,
                Record.kind == "outcome_observation").order_by(Record.created)) if r.value["category"] == group]
    candidate = outcome_candidate(rows)
    if candidate:
        promote(tenant, "outcome", f"outcome:{group}", candidate)


def cursor(tenant):
    with transaction() as db:
        row = get_record(db, tenant, "event_cursor", "marketplace")
        return row.value["after"] if row else 0


def apply_events(tenant, events):
    """Applies each event once and returns conversations with a new client message."""
    replies, groups = set(), set()
    with transaction() as db:
        row = get_record(db, tenant, "event_cursor", "marketplace")
        after = row.value["after"] if row else 0
        for event in sorted(events, key=lambda e: e["sequence"]):
            if not get_record(db, tenant, "seen_event", event["id"]):
                if event.get("kind") == "message" and event["status"] == "received":
                    replies.add(event["subject"])
                elif event["status"] in ORDER:
                    mark(db, tenant, event["subject"], event["status"], event["id"], event.get("synthetic", False))
                    # Upwork's terms (8.6) keep its outputs out of AI memory, so live outcomes are not learned.
                    if event["status"] in OUTCOMES and settings().marketplace_mode != "upwork":
                        groups.add(observe(db, tenant, event))
                put_record(db, tenant, "seen_event", event["id"], {"processed": True})
            after = max(after, event["sequence"])
        put_record(db, tenant, "event_cursor", "marketplace", {"after": after})
    for group in groups:
        learn_outcomes(tenant, group)
    return sorted(replies)


def handle(tenant, events):
    for conversation in apply_events(tenant, events):
        queue_reply(tenant, conversation)


async def sync(tenant, tools):
    handle(tenant, await tools.call("scout", "list_events", {"after": cursor(tenant)}))


async def sync_all():
    for user in users():
        if due(user.id, "events", config()["scheduling"]["event_sync_seconds"]):
            try:
                async with tools_for(user.id) as tools:
                    await sync(user.id, tools)
            except Exception as exc:
                failed(user.id, "events", exc)


def tick_all():
    """Mock mode only: simulated client outcomes advance on a schedule, once per time slot."""
    if settings().marketplace_mode != "mock":
        return
    seconds = config()["scheduling"]["mock_outcome_seconds"]
    for user in users():
        if due(user.id, "mock_outcomes", seconds):
            MockMarketplace().advance(user.id, f"scheduled-{int(now() // seconds)}")
