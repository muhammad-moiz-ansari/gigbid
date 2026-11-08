"""Isolated browser-test API and real graph worker. No production model switch."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

if os.environ.get("GIGBID_E2E_TEST_SERVER") != "1":
    raise RuntimeError("This labelled test server requires explicit test-only opt-in")

folder = Path(__file__).resolve().parents[1] / ".cache/e2e" / os.environ["GIGBID_E2E_RUN_ID"]
folder.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (folder / "domain.db").as_posix()
os.environ["CHECKPOINT_URL"] = (folder / "checkpoints.db").as_posix()
os.environ["MARKETPLACE_MODE"] = "mock"
os.environ["QUEUE_MODE"] = "database"
os.environ["WEB_ORIGIN"] = "http://127.0.0.1:3100"
os.environ["MCP_CALLS_PER_MINUTE"] = "10000"

from sqlalchemy import select  # noqa: E402

from apps.api.db import Base, Run, engine, transaction  # noqa: E402
from apps.api.main import app  # noqa: E402
from tests.support import TestModels, TestTools  # noqa: E402
from worker.runtime import process_run  # noqa: E402


class BrowserTestModels(TestModels):
    async def complete(self, node, data, schema):
        await asyncio.sleep(.15)
        result, usage = await super().complete(node, data, schema)
        if node == "writer" and "regenerate_paragraph" in data:
            result["text"] = "Proposed approach: I would test authorization."
        return result, usage


async def drain():
    while True:
        with transaction() as db:
            jobs = [(run.id, run.tenant) for run in db.scalars(select(Run).where(Run.status == "queued"))]
        for run_id, tenant in jobs:
            await process_run(run_id, TestTools(tenant), BrowserTestModels())
        await asyncio.sleep(.15)


@asynccontextmanager
async def lifespan(_):
    Base.metadata.create_all(engine)
    task = asyncio.create_task(drain())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        engine.dispose()


app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8106, log_level="warning")

