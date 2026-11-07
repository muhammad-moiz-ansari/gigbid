"""Shared MCP authentication, bounded execution, rate limiting and redacted audit."""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel
from sqlalchemy import select, text

from agent.marketplace_port import (
    AmbiguousWrite,
    IdempotencyConflict,
    MarketplaceTimeout,
    NotFound,
    RateLimited,
    Unavailable,
)
from apps.api.auth.service import token_hash
from apps.api.config import settings
from apps.api.db import Event, Session, User, digest, get_record, now, put_record, transaction, uid
from apps.api.safety import redact
from mcp_servers.auth import resolve_tool_token

READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
MARKET_READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
MARKET_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
SPEND = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
)


class BoundaryError(RuntimeError):
    def __init__(self, code, message, *, retryable=False, retry_after=0, ambiguous=False):
        self.data = {
            "code": code,
            "message": str(redact(message)),
            "retryable": retryable,
            "retry_after": retry_after,
            "ambiguous": ambiguous,
        }
        super().__init__(json.dumps(self.data))


def error_data(exc):
    if isinstance(exc, BoundaryError):
        return exc
    if isinstance(exc, PermissionError):
        return BoundaryError("permission_denied", str(exc))
    if isinstance(exc, IdempotencyConflict):
        return BoundaryError("idempotency_conflict", str(exc))
    if isinstance(exc, NotFound):
        return BoundaryError("not_found", str(exc))
    if isinstance(exc, AmbiguousWrite):
        return BoundaryError(
            "ambiguous_write", "Write response unknown; reconcile the stable key", ambiguous=True
        )
    if isinstance(exc, RateLimited):
        return BoundaryError(
            "rate_limited", "Rate limit reached", retryable=True, retry_after=exc.retry_after
        )
    if isinstance(exc, MarketplaceTimeout):
        return BoundaryError("service_timeout", "Marketplace timed out", retryable=True)
    if isinstance(exc, Unavailable):
        return BoundaryError("service_unavailable", str(exc), retryable=True)
    if isinstance(exc, ValueError):
        return BoundaryError("invalid_request", str(exc)[:300])
    return BoundaryError("internal_error", "Tool failed; inspect the correlated audit event")


class RedactingFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        try:
            record.msg = json.dumps(redact(json.loads(message)))
        except (ValueError, TypeError):
            record.msg = str(redact(message))
        record.args = ()
        # Do not let SDK traceback formatting reintroduce raw arguments or credentials.
        if record.exc_info:
            record.msg += " [exception details omitted; inspect the redacted audit]"
            record.exc_info = None
            record.exc_text = None
        return True


class SessionVerifier:
    def __init__(self, resource_url):
        self.resource_url = resource_url.rstrip("/")

    async def verify_token(self, token: str):
        resolved = resolve_tool_token(token, self.resource_url)
        if resolved:
            tenant, expires = resolved
            return AccessToken(
                token=token,
                client_id=tenant,
                subject=tenant,
                scopes=["tools"],
                expires_at=int(expires),
                resource=self.resource_url,
            )
        return None


def make_server(name, port):
    cfg = settings()
    http = cfg.mcp_transport == "http"
    resource = getattr(
        cfg,
        {8001: "portfolio_mcp_url", 8002: "marketplace_mcp_url", 8003: "workspace_mcp_url"}[port],
    )
    server = FastMCP(
        name,
        host=cfg.mcp_bind_host,
        port=urlsplit(resource).port or port,
        stateless_http=True,
        json_response=True,
        token_verifier=SessionVerifier(resource) if http else None,
        auth=AuthSettings(
            issuer_url="http://localhost:8000",
            resource_server_url=resource,
            validate_token_resource=True,
            required_scopes=["tools"],
        )
        if http
        else None,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=cfg.mcp_allowed_hosts,
            allowed_origins=[
                cfg.web_origin,
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
            ],
        ),
    )
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
    return server


def tenant_id(context: Context | None = None):
    access = get_access_token()
    request = context.request_context.request if context else None
    if access:
        resolved = resolve_tool_token(access.token, access.resource or "")
        if not resolved:
            raise PermissionError("Valid resource-bound bearer token required")
        return resolved[0]
    # An HTTP caller may never fall back to credentials inherited by the server.
    raw = (
        access.token
        if access
        else ("" if request is not None else os.environ.get("GIGBID_MCP_TOKEN", ""))
    )
    with transaction() as db:
        session = db.get(Session, token_hash(raw))
        if not session or session.expires <= now() or not db.get(User, session.tenant):
            raise PermissionError("Valid bearer session required for every MCP call")
        return session.tenant


def trace_id(context=None):
    request = context.request_context.request if context else None
    value = (
        request.headers.get("x-trace-id", "")
        if request is not None
        else os.environ.get("GIGBID_TRACE_ID", "")
    )
    return value if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) else uid()


def audit_arguments(value):
    if isinstance(value, dict):
        return {
            key: {"sha256": digest(item), "characters": len(item)}
            if key.lower() in ("text", "body", "content") and isinstance(item, str)
            else audit_arguments(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [audit_arguments(item) for item in value]
    return redact(value)


def plain(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def result_summary(value):
    value = plain(value)
    summary = {"sha256": digest(value), "type": type(value).__name__}
    if isinstance(value, list):
        summary["items"] = len(value)
    if isinstance(value, dict):
        summary.update(
            {k: value[k] for k in ("status", "effect_id", "connects_cost", "dry_run") if k in value}
        )
    return summary


def append_audit(tenant, tool, stage, payload, trace):
    with transaction() as db:
        db.add(
            Event(
                tenant=tenant,
                run_id="mcp",
                name=f"tool:{tool}:{stage}",
                payload=payload,
                trace_id=trace,
            )
        )


@asynccontextmanager
async def audited(tool, arguments, context=None):
    try:
        tenant, trace = tenant_id(context), trace_id(context)
    except PermissionError as exc:
        raise error_data(exc) from None
    limited = False
    with transaction() as db:
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        else:
            db.scalar(select(User).where(User.id == tenant).with_for_update())
        window = str(int(now() // 60))
        counter = get_record(db, tenant, "rate_limit", window)
        count = counter.value["count"] if counter else 0
        limited = count >= settings().mcp_calls_per_minute
        if not limited:
            put_record(db, tenant, "rate_limit", window, {"count": count + 1})
        db.add(
            Event(
                tenant=tenant,
                run_id="mcp",
                name=f"tool:{tool}:{'rate_limited' if limited else 'start'}",
                payload={
                    "arguments": audit_arguments(arguments),
                    "arguments_hash": digest(arguments),
                },
                trace_id=trace,
            )
        )
    if limited:
        raise BoundaryError(
            "rate_limited",
            "Per-user MCP limit reached",
            retryable=True,
            retry_after=max(1, 60 - int(now() % 60)),
        )
    state = {"tenant": tenant, "trace_id": trace, "result": None}
    try:
        yield state
    except Exception as exc:
        error = error_data(exc)
        append_audit(tenant, tool, "error", error.data, trace)
        raise error from None
    else:
        append_audit(tenant, tool, "success", result_summary(state["result"]), trace)


async def execute_tool(name, arguments, operation, *, context=None, mutating=False):
    async with audited(name, arguments, context) as audit:
        task = asyncio.create_task(asyncio.to_thread(operation, audit["tenant"]))
        try:
            result = await asyncio.wait_for(
                asyncio.shield(task), settings().mcp_server_timeout_seconds
            )
        except TimeoutError:
            # A timed-out sync adapter may finish later. Never report a known failure
            # or automatically retry a potentially successful write.
            def completed(finished):
                try:
                    value = result_summary(finished.result())
                    append_audit(audit["tenant"], name, "late_success", value, audit["trace_id"])
                except Exception:
                    append_audit(
                        audit["tenant"], name, "late_error", {"completed": False}, audit["trace_id"]
                    )

            task.add_done_callback(completed)
            raise BoundaryError(
                "ambiguous_write" if mutating else "service_timeout",
                "Write may still finish; reconcile the stable key"
                if mutating
                else "Tool deadline exceeded",
                retryable=not mutating,
                ambiguous=mutating,
            ) from None
        audit["result"] = result
        return result


def serve(server):
    server.run(transport="streamable-http" if settings().mcp_transport == "http" else "stdio")
