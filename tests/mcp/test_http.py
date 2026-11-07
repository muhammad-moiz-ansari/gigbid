import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.auth.service import issue_session, token_hash
from apps.api.config import settings
from apps.api.db import Event, Record, Session, User, get_record, now, transaction, uid
from mcp_servers.auth import issue_tool_token
from mcp_servers.marketplace.server import create_server as marketplace
from mcp_servers.portfolio.server import create_server as portfolio

HEADERS = {"Accept": "application/json, text/event-stream", "X-Trace-ID": "http-phase3-trace"}


def call(client, token, name="get_connects_balance", arguments=None, **headers):
    return client.post(
        "/mcp",
        headers={**HEADERS, "Authorization": f"Bearer {token}", **headers},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
    )


@pytest.fixture
def http_server(mcp_identity, monkeypatch):
    monkeypatch.setattr(settings(), "mcp_transport", "http")
    token = issue_tool_token(mcp_identity[1], settings().marketplace_mcp_url)
    with TestClient(
        marketplace().streamable_http_app(), base_url="http://localhost:8002"
    ) as client:
        yield client, token


def test_http_requires_resource_bound_bearer_and_rejects_inherited_env(http_server, mcp_identity):
    client, token = http_server
    assert (
        client.post(
            "/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        ).status_code
        == 401
    )
    assert call(client, "invalid").status_code == 401
    assert (
        call(client, mcp_identity[1]).status_code == 401
    )  # Raw app session is not an HTTP MCP credential.
    result = call(client, token)
    assert result.status_code == 200, result.text
    assert result.json()["result"]["structuredContent"]["balance"] == 100
    other_resource = issue_tool_token(mcp_identity[1], settings().portfolio_mcp_url)
    assert call(client, other_resource).status_code == 401
    with transaction() as db:
        entries = list(
            db.scalars(select(Event).where(Event.tenant == mcp_identity[0], Event.run_id == "mcp"))
        )
    assert entries and all(e.trace_id == "http-phase3-trace" for e in entries)


def test_http_expired_child_and_revoked_parent_are_rejected(http_server, mcp_identity):
    client, token = http_server
    with transaction() as db:
        row = get_record(db, mcp_identity[0], "mcp_credential", token_hash(token))
        row.value = {**row.value, "expires": now() - 1}
    assert call(client, token).status_code == 401
    active = issue_tool_token(mcp_identity[1], settings().marketplace_mcp_url)
    assert call(client, active).status_code == 200
    with transaction() as db:
        db.delete(db.get(Session, token_hash(mcp_identity[1])))
    assert call(client, active).status_code == 401


def test_http_resource_tenant_isolation(mcp_identity, monkeypatch):
    monkeypatch.setattr(settings(), "mcp_transport", "http")
    with transaction() as db:
        own = db.scalar(
            select(Record).where(Record.tenant == mcp_identity[0], Record.kind == "evidence")
        )
        other = uid()
        db.add(
            User(
                id=other,
                email="http-other@example.test",
                password_hash="unused-test-hash",
                profile={},
            )
        )
        db.flush()
        session, _ = issue_session(db, other)
    token = issue_tool_token(session, settings().portfolio_mcp_url)
    with TestClient(portfolio().streamable_http_app(), base_url="http://localhost:8001") as client:
        missing = call(client, token, "get_case_study", {"id": own.key})
        assert missing.status_code == 200 and missing.json()["result"]["isError"]
        encoded = json.dumps(missing.json())
        assert own.value["text"] not in encoded
        skills = call(client, token, "list_skills")
        assert skills.json()["result"]["structuredContent"]["result"] == []


def test_http_host_origin_and_shared_user_rate_limit(http_server, mcp_identity, monkeypatch):
    client, token = http_server
    assert call(client, token, Host="attacker.example").status_code == 421
    assert call(client, token, Origin="https://attacker.example").status_code == 403
    monkeypatch.setattr(settings(), "mcp_calls_per_minute", 2)
    assert not call(client, token).json()["result"].get("isError")
    other_token = issue_tool_token(mcp_identity[1], settings().marketplace_mcp_url)
    assert not call(client, other_token).json()["result"].get("isError")
    limited = call(client, token).json()["result"]
    assert limited["isError"] and "rate_limited" in limited["content"][0]["text"]
    with transaction() as db:
        assert db.scalar(
            select(Event).where(Event.tenant == mcp_identity[0], Event.name.like("%:rate_limited"))
        )
