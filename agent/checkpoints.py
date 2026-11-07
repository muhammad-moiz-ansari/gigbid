from contextlib import asynccontextmanager

from apps.api.config import settings


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
