"""MCP-only agent capabilities with role filtering and recoverable service failures."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.model import config
from apps.api.config import ROOT, settings

ALLOWLISTS = {
    "scout": {"search_jobs", "list_events"},
    "intake": {"get_job"},
    "analyst": set(),
    "risk": {"get_client_history"},
    "matcher": {"search_evidence"},
    "pricing": {"get_connects_balance", "get_client_history"},
    "writer": {"search_evidence", "get_case_study"},
    "verifier": {"get_case_study"},
    "critic": {"get_case_study"},
    "compliance": set(),
    "liaison": {"list_messages", "search_evidence", "free_slots"},
    "executor": {
        "submit_proposal",
        "send_message",
        "create_proposal_draft",
        "reconcile_write",
        "create_interview_hold",
        "create_email_draft",
    },
}
TOOL_SERVERS = {
    **{
        name: "marketplace"
        for name in (
            "search_jobs",
            "get_job",
            "get_client_history",
            "get_connects_balance",
            "list_messages",
            "list_events",
            "submit_proposal",
            "send_message",
            "create_proposal_draft",
            "reconcile_write",
        )
    },
    **{name: "portfolio" for name in ("search_evidence", "get_case_study", "list_skills")},
    **{name: "workspace" for name in ("free_slots", "create_interview_hold", "create_email_draft")},
}
WRITE_TOOLS = {
    "submit_proposal",
    "send_message",
    "create_proposal_draft",
    "create_interview_hold",
    "create_email_draft",
}


class ToolFailure(RuntimeError):
    def __init__(
        self, code, *, retryable=False, retry_after=0, ambiguous=False, message="MCP tool failed"
    ):
        self.code, self.retryable, self.retry_after, self.ambiguous = (
            code,
            retryable,
            retry_after,
            ambiguous,
        )
        super().__init__(message)


class ToolUnavailable(ToolFailure):
    pass


def execution_error(exc):
    if isinstance(exc, ToolFailure):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        return execution_error(exc.exceptions[0])
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) in (401, 403):
        return ToolFailure(
            "authentication_failed", message="MCP credential was rejected; sign in again"
        )
    if isinstance(exc, ToolException):
        raw = str(exc)
        offset = raw.find("{")
        if offset >= 0:
            try:
                data, _ = json.JSONDecoder().raw_decode(raw[offset:])
                return ToolFailure(
                    data["code"],
                    retryable=data.get("retryable", False),
                    retry_after=data.get("retry_after", 0),
                    ambiguous=data.get("ambiguous", False),
                    message=data.get("message", "MCP tool rejected the call"),
                )
            except (ValueError, KeyError, TypeError):
                pass
        return ToolFailure("tool_error", message="MCP tool rejected the request")
    if isinstance(exc, (ValueError, TypeError)):
        return ToolFailure(
            "invalid_result", message="MCP result did not match the expected JSON contract"
        )
    return ToolUnavailable(
        "transport_unavailable",
        retryable=True,
        message="MCP transport unavailable; work is retained for retry",
    )


def decode_result(result):
    # Full LangChain ToolCall invocation preserves the structured MCP artifact.
    if isinstance(result, ToolMessage):
        if result.status == "error":
            text = (
                result.content
                if isinstance(result.content, str)
                else "\n".join(
                    block.get("text", "") for block in result.content if isinstance(block, dict)
                )
            )
            raise execution_error(ToolException(text))
        artifact = result.artifact
        if isinstance(artifact, dict) and "structured_content" in artifact:
            value = artifact["structured_content"]
            return (
                value["result"] if isinstance(value, dict) and set(value) == {"result"} else value
            )
        result = result.content
    elif isinstance(result, tuple):
        content, artifact = result
        if isinstance(artifact, dict) and "structured_content" in artifact:
            value = artifact["structured_content"]
            return (
                value["result"] if isinstance(value, dict) and set(value) == {"result"} else value
            )
        result = content
    if isinstance(result, str):
        return json.loads(result)
    if (
        isinstance(result, list)
        and result
        and all(isinstance(block, dict) and block.get("type") == "text" for block in result)
    ):
        values = [json.loads(block["text"]) for block in result]
        return values[0] if len(values) == 1 else values
    return result


@dataclass(frozen=True)
class RoleGateway:
    gateway: "ToolGateway"
    role: str

    @property
    def tools(self):
        return self.gateway.tools_for(self.role)

    async def call(self, name, arguments):
        return await self.gateway.call(self.role, name, arguments)


class ToolGateway:
    def __init__(self, tools, *, loader=None, report=None):
        self.tools = {tool.name: tool for tool in tools}
        self.loader, self.report = loader, report
        self._availability = {}
        self._refresh_locks = {
            name: asyncio.Lock() for name in ("portfolio", "marketplace", "workspace")
        }

    def tools_for(self, role):
        if role not in ALLOWLISTS:
            raise PermissionError("Unknown agent role")
        return tuple(tool for name, tool in self.tools.items() if name in ALLOWLISTS[role])

    def for_role(self, role):
        self.tools_for(role)
        return RoleGateway(self, role)

    def availability(self):
        return {name: dict(value) for name, value in self._availability.items()}

    def _status(self, server, available, code=None):
        state = {"available": available, "error_code": code}
        self._availability[server] = state
        if self.report:
            self.report(server, state)

    async def refresh(self, server):
        if not self.loader:
            return False
        async with self._refresh_locks[server]:
            try:
                loaded = await asyncio.wait_for(
                    self.loader(server), settings().tool_timeout_seconds
                )
                self.tools = {
                    name: tool
                    for name, tool in self.tools.items()
                    if TOOL_SERVERS.get(name) != server
                }
                self.tools.update(
                    {tool.name: tool for tool in loaded if TOOL_SERVERS.get(tool.name) == server}
                )
                self._status(server, True)
                return True
            except Exception as exc:
                error = execution_error(exc)
                self._status(server, False, error.code)
                return False

    async def call(self, role, name, arguments):
        if name not in ALLOWLISTS.get(role, set()):
            raise PermissionError(f"{role} cannot call {name}")
        server = TOOL_SERVERS[name]
        attempts = (
            1 if name in WRITE_TOOLS else min(max(config()["retries"]["read_attempts"], 1), 5)
        )
        for attempt in range(attempts):
            tool = self.tools.get(name)
            if not tool and self.loader:
                await self.refresh(server)
                tool = self.tools.get(name)
            if not tool:
                error = ToolUnavailable(
                    "transport_unavailable",
                    retryable=True,
                    message=f"{server} MCP unavailable; work is retained for retry",
                )
            else:
                try:
                    result = await asyncio.wait_for(
                        tool.ainvoke(
                            {
                                "type": "tool_call",
                                "id": str(uuid4()),
                                "name": name,
                                "args": arguments,
                            }
                        ),
                        settings().tool_timeout_seconds,
                    )
                    value = decode_result(result)
                    self._status(server, True)
                    return value
                except Exception as exc:
                    error = execution_error(exc)
                    if (
                        isinstance(exc, TimeoutError)
                        and name in WRITE_TOOLS
                        and not arguments.get("request", {}).get("dry_run", True)
                    ):
                        error = ToolFailure(
                            "ambiguous_write",
                            ambiguous=True,
                            message="Write response timed out; reconcile the stable key",
                        )
            self._status(server, False if error.retryable else True, error.code)
            max_delay = settings().mcp_retry_max_delay_seconds
            # Do not sleep past provider Retry-After or retry any mutating operation.
            if not error.retryable or attempt + 1 >= attempts or error.retry_after > max_delay:
                raise error
            await asyncio.sleep(min(max_delay, max(error.retry_after, 0.2 * 2**attempt)))
        raise ToolUnavailable("transport_unavailable", retryable=True)


def connections(token, trace_id, http_tokens=None):
    cfg = settings()
    result = {}
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "DATABASE_URL",
        "CHECKPOINT_URL",
        "MARKETPLACE_MODE",
        "RETRIEVAL_VARIANT",
        "OLLAMA_URL",
        "QDRANT_URL",
        "QDRANT_MODE",
        "QDRANT_PATH",
        "MCP_CALLS_PER_MINUTE",
        "MCP_SERVER_TIMEOUT_SECONDS",
        "MCP_ALLOWED_HOSTS",
        "WEB_ORIGIN",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    for key in (
        "database_url",
        "checkpoint_url",
        "marketplace_mode",
        "retrieval_variant",
        "ollama_url",
        "qdrant_url",
        "qdrant_mode",
        "qdrant_path",
        "mcp_calls_per_minute",
        "mcp_server_timeout_seconds",
        "mcp_allowed_hosts",
        "web_origin",
    ):
        value = getattr(cfg, key)
        env.setdefault(key.upper(), json.dumps(value) if isinstance(value, list) else str(value))
    env.update(GIGBID_MCP_TOKEN=token, GIGBID_TRACE_ID=trace_id, MCP_TRANSPORT="stdio")
    for name in ("portfolio", "marketplace", "workspace"):
        if cfg.mcp_transport == "http":
            if not http_tokens or name not in http_tokens:
                raise PermissionError("HTTP MCP requires audience-bound delegated credentials")
            result[name] = {
                "transport": "streamable_http",
                "url": getattr(cfg, f"{name}_mcp_url"),
                "headers": {"Authorization": f"Bearer {http_tokens[name]}", "X-Trace-ID": trace_id},
            }
        else:
            result[name] = {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", f"mcp_servers.{name}.server"],
                "cwd": str(ROOT),
                "env": env,
            }
    return result


@asynccontextmanager
async def gateway(token, trace_id):
    from apps.api.auth.service import token_hash
    from apps.api.db import Session, now, put_record, transaction

    with transaction() as db:
        session = db.get(Session, token_hash(token))
        if not session or session.expires <= now():
            raise PermissionError("Valid MCP session required")
        tenant = session.tenant

    def report(server, state):
        with transaction() as db:
            put_record(
                db,
                tenant,
                "mcp_health",
                server,
                {**state, "checked_at": now(), "trace_id": trace_id},
            )

    from mcp_servers.auth import issue_tool_token, revoke_tool_token

    http_tokens = {}
    if settings().mcp_transport == "http":
        for server in ("portfolio", "marketplace", "workspace"):
            http_tokens[server] = issue_tool_token(token, getattr(settings(), f"{server}_mcp_url"))
    client = MultiServerMCPClient(
        connections(token, trace_id, http_tokens), handle_tool_errors=False
    )
    tools = ToolGateway(
        [], loader=lambda server: client.get_tools(server_name=server), report=report
    )
    # A failed service cannot hide healthy servers. Calls create fresh sessions, so
    # restoring a server does not leave a stale broken transport in this gateway.
    try:
        await asyncio.gather(
            *(tools.refresh(name) for name in ("portfolio", "marketplace", "workspace"))
        )
        yield tools
    finally:
        for child in http_tokens.values():
            revoke_tool_token(child)
