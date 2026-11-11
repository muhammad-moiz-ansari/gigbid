"""Long-term memory in a LangGraph store: only promoted style and outcome rules, never raw tool output."""
from contextlib import asynccontextmanager, contextmanager

from langgraph.config import get_store

from apps.api.config import settings
from apps.api.db import get_record, put_record, transaction

KINDS = ("style", "outcome")


def _postgres():
    return settings().checkpoint_url.startswith(("postgresql://", "postgres://"))


@contextmanager
def open_store():
    if _postgres():
        from langgraph.store.postgres import PostgresStore
        with PostgresStore.from_conn_string(settings().checkpoint_url) as store:
            store.setup()
            yield store
    else:
        from langgraph.store.sqlite import SqliteStore
        with SqliteStore.from_conn_string(settings().checkpoint_url) as store:
            store.setup()
            yield store


@asynccontextmanager
async def open_async_store():
    if _postgres():
        from langgraph.store.postgres.aio import AsyncPostgresStore
        async with AsyncPostgresStore.from_conn_string(settings().checkpoint_url) as store:
            await store.setup()
            yield store
    else:
        from langgraph.store.sqlite.aio import AsyncSqliteStore
        async with AsyncSqliteStore.from_conn_string(settings().checkpoint_url) as store:
            await store.setup()
            yield store


async def recall(tenant, kind):
    """Promoted memory for a graph node; empty when the graph runs without a store."""
    try:
        store = get_store()
    except RuntimeError:
        return []
    return [item.value for item in await store.asearch((tenant, kind), limit=50)] if store else []


def list_memory(tenant):
    with open_store() as store:
        return [{"id": item.key, **item.value} for kind in KINDS for item in store.search((tenant, kind), limit=100)]


def promote(tenant, kind, key, value):
    """Writes a promoted rule unless the user deleted it earlier."""
    with transaction() as db:
        if get_record(db, tenant, "forgotten_memory", key):
            return False
    with open_store() as store:
        store.put((tenant, kind), key, value)
    return True


def delete_memory(tenant, key):
    with open_store() as store:
        for kind in KINDS:
            store.delete((tenant, kind), key)
    with transaction() as db:
        # A tombstone stops later observations from promoting the same rule again.
        put_record(db, tenant, "forgotten_memory", key, {"deleted": True})
