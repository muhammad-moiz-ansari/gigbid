import hashlib
from contextlib import asynccontextmanager

import portalocker

from apps.api.config import ROOT, settings


@asynccontextmanager
async def thread_lock(tenant, run_id):
    """One graph writer per durable thread, including after a lease expires."""
    key = hashlib.sha256(f"{tenant}:{run_id}".encode()).digest()
    if settings().checkpoint_url.startswith(("postgresql://", "postgres://")):
        import psycopg
        async with await psycopg.AsyncConnection.connect(settings().checkpoint_url, autocommit=True) as conn:
            lock_id = int.from_bytes(key[:8], "big", signed=True)
            cursor = await conn.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
            acquired = (await cursor.fetchone())[0]
            try:
                yield acquired
            finally:
                if acquired:
                    await conn.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
    else:
        path = ROOT / ".cache/worker-locks" / f"{key.hex()}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            try:
                portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
            except portalocker.LockException:
                yield False
            else:
                try:
                    yield True
                finally:
                    portalocker.unlock(handle)


@asynccontextmanager
async def checkpointer():
    url = settings().checkpoint_url
    if url.startswith(("postgresql://", "postgres://")):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async with AsyncPostgresSaver.from_conn_string(url) as saver:
            await saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        async with AsyncSqliteSaver.from_conn_string(url) as saver:
            yield saver


def thread_config(tenant, run_id):
    return {"configurable": {"thread_id": f"{tenant}:{run_id}"}, "recursion_limit": 40}
