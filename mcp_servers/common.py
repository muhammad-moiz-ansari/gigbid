import os
from contextlib import contextmanager

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy import select

from apps.api.auth.service import token_hash
from apps.api.config import settings
from apps.api.db import Event, Session, digest, get_record, now, put_record, transaction
from apps.api.safety import redact

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class SessionVerifier:
    async def verify_token(self, token: str):
        with transaction() as db:
            session = db.get(Session, token_hash(token))
            if session and session.expires > now():
                return AccessToken(token=token, client_id=session.tenant, subject=session.tenant,
                                   scopes=["tools"], expires_at=int(session.expires))
        return None


def make_server(name, port):
    http = settings().mcp_transport == "http"
    return FastMCP(name, host="0.0.0.0" if http else "127.0.0.1", port=port,
        stateless_http=True, token_verifier=SessionVerifier() if http else None,
        auth=AuthSettings(issuer_url=f"http://localhost:{port}",
                          resource_server_url=f"http://localhost:{port}/mcp",
                          required_scopes=["tools"]) if http else None)


def tenant_id():
    token = get_access_token()
    raw = token.token if token else os.environ.get("GIGBID_MCP_TOKEN", "")
    with transaction() as db:
        session = db.get(Session, token_hash(raw))
        if not session or session.expires <= now():
            raise PermissionError("Valid bearer session required for every MCP call")
        return session.tenant


@contextmanager
def audited(tool, arguments):
    tenant = tenant_id()
    trace_id = os.environ.get("GIGBID_TRACE_ID", "mcp-http")
    # Shared fixed window; transaction serializes per-user counters across replicas.
    with transaction() as db:
        from sqlalchemy import text
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        else:
            db.execute(select(Session).where(Session.tenant == tenant).with_for_update())
        window = str(int(now() // 60))
        counter = get_record(db, tenant, "rate_limit", window)
        count = counter.value["count"] if counter else 0
        if count >= settings().mcp_calls_per_minute:
            raise RuntimeError("Per-user MCP rate limit exceeded; retry next window")
        put_record(db, tenant, "rate_limit", window, {"count": count + 1})
        # Audit exact payload identity without leaking proposal text or PII.
        db.add(Event(tenant=tenant, run_id="mcp", name=f"tool:{tool}:start",
                     payload={"arguments": redact(arguments), "arguments_hash": digest(arguments)},
                     trace_id=trace_id))
    try:
        yield tenant
    except Exception as exc:
        with transaction() as db:
            db.add(Event(tenant=tenant, run_id="mcp", name=f"tool:{tool}:error",
                         payload={"type": type(exc).__name__}, trace_id=trace_id))
        raise
    else:
        with transaction() as db:
            db.add(Event(tenant=tenant, run_id="mcp", name=f"tool:{tool}:success",
                         payload={"completed": True}, trace_id=trace_id))


def serve(server):
    server.run(transport="streamable-http" if settings().mcp_transport == "http" else "stdio")
