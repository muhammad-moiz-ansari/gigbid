import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager

from langchain_mcp_adapters.client import MultiServerMCPClient

from apps.api.config import ROOT, settings

ALLOWLISTS = {
    "scout": {"search_jobs", "list_events"},
    "intake": {"get_job"},
    "risk": {"get_client_history"},
    "matcher": {"search_evidence"},
    "pricing": {"get_connects_balance", "get_client_history"},
    "writer": {"search_evidence", "get_case_study"},
    "verifier": {"get_case_study"},
    "critic": {"get_case_study"},
    "liaison": {"list_messages", "search_evidence", "free_slots"},
    "executor": {"submit_proposal", "send_message", "create_proposal_draft", "reconcile_write"},
}


class ToolGateway:
    def __init__(self, tools):
        self.tools = {tool.name: tool for tool in tools}

    async def call(self, role, name, arguments):
        if name not in ALLOWLISTS.get(role, set()):
            raise PermissionError(f"{role} cannot call {name}")
        tool = self.tools.get(name)
        if not tool:
            raise RuntimeError(f"MCP tool unavailable: {name}")
        attempts = 3 if name in {"search_jobs", "get_job", "get_client_history",
                                 "get_connects_balance", "search_evidence", "list_messages"} else 1
        for attempt in range(attempts):
            try:
                result = await asyncio.wait_for(tool.ainvoke(arguments), settings().tool_timeout_seconds)
                if isinstance(result, tuple):
                    content, artifact = result
                    if isinstance(artifact, dict) and artifact.get("structured_content") is not None:
                        result = artifact["structured_content"]
                    else:
                        result = content
                if isinstance(result, list) and result and isinstance(result[0], dict) and "text" in result[0]:
                    result = json.loads(result[0]["text"])
                elif isinstance(result, str):
                    result = json.loads(result)
                if isinstance(result, dict) and set(result) == {"result"}:
                    result = result["result"]
                return result
            except (PermissionError, ValueError):
                raise
            except Exception:
                if attempt + 1 == attempts:
                    raise
                await asyncio.sleep(0.2 * 2**attempt)


@asynccontextmanager
async def gateway(token, trace_id):
    cfg = settings()
    connections = {}
    for name in ("portfolio", "marketplace", "workspace"):
        if cfg.mcp_transport == "http":
            connections[name] = {"transport": "streamable_http",
                                  "url": getattr(cfg, f"{name}_mcp_url"),
                                  "headers": {"Authorization": f"Bearer {token}", "X-Trace-ID": trace_id}}
        else:
            connections[name] = {"transport": "stdio", "command": sys.executable,
                "args": ["-m", f"mcp_servers.{name}.server"], "cwd": str(ROOT),
                "env": {**os.environ, "GIGBID_MCP_TOKEN": token, "GIGBID_TRACE_ID": trace_id}}
    client = MultiServerMCPClient(connections, handle_tool_errors=False)
    # Persistent sessions avoid a subprocess per tool call.
    from contextlib import AsyncExitStack

    from langchain_mcp_adapters.tools import load_mcp_tools
    async with AsyncExitStack() as stack:
        tools = []
        for name in connections:
            session = await stack.enter_async_context(client.session(name))
            tools.extend(await load_mcp_tools(session))
        yield ToolGateway(tools)
