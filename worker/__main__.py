import asyncio
import sys

from apps.api.config import settings
from worker.pipeline import sync_all, tick_all
from worker.retention import purge_all
from worker.runtime import drain_once
from worker.scout import scout_all


async def main():
    print("GigBid local database worker. Real open models required; Ctrl+C to stop.")
    while True:
        await scout_all()
        await sync_all()
        tick_all()
        await purge_all()
        if not await drain_once():
            await asyncio.sleep(2)


def run():
    config = settings()
    if sys.platform == "win32" and config.checkpoint_url.startswith(("postgresql://", "postgres://")):
        if config.mcp_transport != "http":
            raise SystemExit(
                "Windows workers with PostgreSQL checkpoints require MCP_TRANSPORT=http. "
                "Start the three local MCP servers first."
            )
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())


if __name__ == "__main__":
    run()
