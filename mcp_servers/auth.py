"""Local audience-bound MCP credentials delegated from revocable app sessions."""

import secrets

from sqlalchemy import select

from apps.api.auth.service import token_hash
from apps.api.db import Record, Session, User, now, put_record, transaction


def issue_tool_token(parent_token: str, audience: str) -> str:
    with transaction() as db:
        parent_hash = token_hash(parent_token)
        parent = db.get(Session, parent_hash)
        if not parent or parent.expires <= now() or not db.get(User, parent.tenant):
            raise PermissionError("Valid parent session required")
        token = secrets.token_urlsafe(32)
        put_record(
            db,
            parent.tenant,
            "mcp_credential",
            token_hash(token),
            {
                "audience": audience.rstrip("/"),
                "parent_hash": parent_hash,
                "expires": min(parent.expires, now() + 3600),
            },
        )
        return token


def resolve_tool_token(token: str, audience: str):
    with transaction() as db:
        row = db.scalar(
            select(Record).where(Record.kind == "mcp_credential", Record.key == token_hash(token))
        )
        if (
            not row
            or row.value["audience"] != audience.rstrip("/")
            or row.value["expires"] <= now()
        ):
            return None
        parent = db.get(Session, row.value["parent_hash"])
        if (
            not parent
            or parent.tenant != row.tenant
            or parent.expires <= now()
            or not db.get(User, row.tenant)
        ):
            return None
        return row.tenant, row.value["expires"]


def revoke_tool_token(token: str):
    with transaction() as db:
        row = db.scalar(
            select(Record).where(Record.kind == "mcp_credential", Record.key == token_hash(token))
        )
        if row:
            db.delete(row)
