import asyncio

from worker.runtime import drain_once
from worker.scout import scout_all


async def main():
    print("GigBid local database worker. Real open models required; Ctrl+C to stop.")
    while True:
        await scout_all()
        if not await drain_once():
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
