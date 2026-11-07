from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from apps.api.db import Record, digest, get_record, put_record, transaction


def list_memory(tenant):
    with transaction() as db:
        return [{"id": r.key, **r.value} for r in db.scalars(select(Record).where(
            Record.tenant == tenant, Record.kind == "memory"))]


def load_store(tenant) -> BaseStore:
    """Hydrate a LangGraph store from durable promoted entries only, per run.

    Local adapter deliberately reloads after deletion; it never caches stale memory.
    PostgresStore integration remains a documented deployment follow-up.
    """
    store = InMemoryStore()
    for value in list_memory(tenant):
        store.put((tenant, value["kind"]), value["id"], value)
    return store


def promote(tenant, value):
    key = digest(value)
    with transaction() as db:
        if not get_record(db, tenant, "forgotten_memory", key):
            put_record(db, tenant, "memory", key, value)


def delete_memory(tenant, key):
    with transaction() as db:
        row = get_record(db, tenant, "memory", key)
        if row:
            db.delete(row)
        # A tombstone prevents the same observations from immediately recreating it.
        put_record(db, tenant, "forgotten_memory", key, {"deleted": True})
