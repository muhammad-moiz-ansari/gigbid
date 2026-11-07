import pytest
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared.memory import create_connected_server_and_client_session

from agent.mcp_client import ToolFailure, ToolGateway
from apps.api.auth.service import issue_session
from apps.api.config import settings
from apps.api.db import transaction
from mcp_servers.portfolio.server import create_server
from rag.ingest.loaders import ingest_text


@pytest.mark.asyncio
async def test_v0_indexed_upload_is_searchable_and_deletable_through_real_portfolio_mcp(
    client, account, vector_index, embeddings, monkeypatch
):
    with transaction() as db:
        token, _ = issue_session(db, account["id"])
    monkeypatch.setenv("GIGBID_MCP_TOKEN", token)
    monkeypatch.setattr(settings(), "retrieval_variant", "V0")
    item = ingest_text(
        account["id"],
        "Rust API demonstration",
        {
            "source": "mcp-rust.md",
            "project": "Phase4 isolated project",
            "skills": ["Rust"],
            "synthetic": True,
        },
    )[0]
    async with create_connected_server_and_client_session(create_server()) as session:
        gateway = ToolGateway(await load_mcp_tools(session, handle_tool_errors=False))
        arguments = {"requirement": "Rust", "filters": {"project": "Phase4 isolated project"}}
        results = await gateway.call("matcher", "search_evidence", arguments)
        assert len(results) == 1 and results[0]["id"] == item["id"]
        assert results[0]["retrieval_variant"] == "V0" and results[0]["synthetic"]
        case = await gateway.call("verifier", "get_case_study", {"id": item["id"]})
        assert case["text"] == item["text"] and case["content_hash"] == item["content_hash"]
        assert client.delete("/evidence/source/mcp-rust.md").status_code == 200
        assert await gateway.call("matcher", "search_evidence", arguments) == []
        with pytest.raises(ToolFailure):
            await gateway.call("verifier", "get_case_study", {"id": item["id"]})
