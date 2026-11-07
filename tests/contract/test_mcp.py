import json
from pathlib import Path

import pytest
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared.memory import create_connected_server_and_client_session

from agent.mcp_client import ToolGateway
from apps.api.auth.service import issue_session
from apps.api.db import transaction
from mcp_servers.marketplace.server import mcp as marketplace
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace


@pytest.mark.asyncio
async def test_mcp_in_memory_schema_and_authorization(account, monkeypatch):
    with transaction() as db:
        token, _ = issue_session(db, account["id"])
    monkeypatch.setenv("GIGBID_MCP_TOKEN", token)
    snapshot = {}
    for server in (marketplace, portfolio, workspace):
        async with create_connected_server_and_client_session(server) as session:
            tools = await session.list_tools()
            snapshot[server.name] = [tool.model_dump(mode="json", exclude_none=True) for tool in tools.tools]
    expected = json.loads((Path(__file__).parent / "mcp_schema.json").read_text())
    assert snapshot == expected, "Tool schema changed. Review and explicitly regenerate snapshot."
    async with create_connected_server_and_client_session(marketplace) as session:
        result = await session.call_tool("get_connects_balance", {})
        assert not result.isError
        loaded = await load_mcp_tools(session)
        gateway = ToolGateway(loaded)
        assert (await gateway.call("pricing", "get_connects_balance", {}))["balance"] == 100
        with pytest.raises(PermissionError):
            await gateway.call("risk", "submit_proposal", {})
    monkeypatch.setenv("GIGBID_MCP_TOKEN", "invalid-token")
    async with create_connected_server_and_client_session(marketplace) as session:
        result = await session.call_tool("get_connects_balance", {})
        assert result.isError


@pytest.mark.asyncio
async def test_real_stdio_mcp_reads(account):
    from agent.mcp_client import gateway
    with transaction() as db:
        token, _ = issue_session(db, account["id"])
    async with gateway(token, "protocol-test") as tools:
        job = await tools.call("intake", "get_job", {"job_id": "mock-api"})
        assert job["id"] == "mock-api"
        skills = tools.tools.get("list_skills")
        assert skills is not None
        assert (await tools.call("pricing", "get_connects_balance", {}))["balance"] == 100
