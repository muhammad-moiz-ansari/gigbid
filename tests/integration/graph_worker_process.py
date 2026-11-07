"""Explicit graph-process test double; never used by the application."""
import asyncio
import os
import sys

from tests.support import TestModels, TestTools
from worker.runtime import process_run


class CrashAfterCommit(TestTools):
    async def call(self, role, name, args):
        result = await super().call(role, name, args)
        if name == "submit_proposal" and not args["request"]["dry_run"]:
            os._exit(73)  # Deliberate process death before execute's checkpoint.
        return result


if __name__ == "__main__":
    cls = CrashAfterCommit if len(sys.argv) > 3 else TestTools
    asyncio.run(process_run(sys.argv[1], cls(sys.argv[2]), TestModels()))

