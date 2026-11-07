import asyncio
from contextlib import AsyncExitStack

import pytest
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared.memory import create_connected_server_and_client_session

from agent.mcp_client import ToolGateway
from apps.api.auth.service import issue_session
from apps.api.config import settings
from apps.api.db import transaction
from mcp_servers.marketplace.server import create_server as marketplace
from mcp_servers.portfolio.server import create_server as portfolio
from mcp_servers.workspace.server import create_server as workspace


@pytest.fixture
def mcp_identity(account, monkeypatch):
    with transaction() as db:
        token, _ = issue_session(db, account["id"])
    monkeypatch.setenv("GIGBID_MCP_TOKEN", token)
    monkeypatch.setenv("GIGBID_TRACE_ID", "phase3-test-trace")
    monkeypatch.setenv("RETRIEVAL_VARIANT", "BM25")
    monkeypatch.setattr(settings(), "retrieval_variant", "BM25")
    return account["id"], token


@pytest.fixture
async def protocol(mcp_identity):
    # AnyIO scopes must enter/exit in the same task; pytest-asyncio runs fixture
    # setup and teardown in separate tasks. Keep SDK lifetimes in a dedicated owner.
    ready = asyncio.get_running_loop().create_future()
    stop = asyncio.Event()

    async def owner():
        async with AsyncExitStack() as stack:
            sessions, tools = {}, []
            for name, builder in (
                ("marketplace", marketplace),
                ("portfolio", portfolio),
                ("workspace", workspace),
            ):
                session = await stack.enter_async_context(
                    create_connected_server_and_client_session(builder())
                )
                sessions[name] = session
                tools.extend(await load_mcp_tools(session, handle_tool_errors=False))
            ready.set_result((sessions, ToolGateway(tools)))
            await stop.wait()

    task = asyncio.create_task(owner())
    try:
        yield await ready
    finally:
        stop.set()
        await task
