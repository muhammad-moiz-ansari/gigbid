import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from apps.api.auth import upwork
from apps.api.config import settings
from apps.api.db import get_record, put_record, transaction

META = {"authorization_endpoint": "https://upwork.test/authorize", "token_endpoint": "https://upwork.test/token",
        "registration_endpoint": "https://upwork.test/register", "revocation_endpoint": "https://upwork.test/revoke"}


@pytest.fixture
def upwork_server(monkeypatch):
    """A stand-in for Upwork's OAuth endpoints that records every request."""
    calls = []

    def respond(request):
        body = parse_qs(request.content.decode()) if request.method == "POST" and request.url.path != "/register" else {}
        calls.append((request.url.path, body))
        if request.url.path.endswith("oauth-authorization-server"):
            return httpx.Response(200, json=META)
        if request.url.path == "/register":
            return httpx.Response(201, json={"client_id": "gigbid-client"})
        if request.url.path == "/token" and body["grant_type"] == ["authorization_code"]:
            assert body["code_verifier"] and body["resource"] == ["https://mcp.upwork.com/mcp"]
            return httpx.Response(200, json={"access_token": "access-123", "refresh_token": "refresh-123", "expires_in": 3600})
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "access-456", "expires_in": 3600})
        return httpx.Response(200, json={})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(settings(), "token_encryption_key", Fernet.generate_key().decode())
    with transaction() as db:
        registered = get_record(db, upwork.SYSTEM, "upwork_client", settings().upwork_redirect_uri)
        if registered:
            db.delete(registered)
    return calls


def sign_in(client):
    url = client.post("/integrations/upwork/connect").json()["authorize_url"]
    return url, parse_qs(urlsplit(url).query)


def test_sign_in_registers_once_and_stores_tokens_encrypted(client, account, upwork_server):
    url, query = sign_in(client)
    assert url.startswith("https://upwork.test/authorize?") and query["client_id"] == ["gigbid-client"]
    assert query["code_challenge_method"] == ["S256"] and query["resource"] == ["https://mcp.upwork.com/mcp"]
    sign_in(client)
    assert [path for path, _ in upwork_server].count("/register") == 1
    back = client.get(f"/integrations/upwork/callback?code=abc&state={query['state'][0]}", follow_redirects=False)
    assert back.status_code == 307 and back.headers["location"].endswith("/settings?upwork=connected")
    with transaction() as db:
        sealed = get_record(db, account["id"], "oauth_token", "upwork").value
    assert "access-123" not in json.dumps(sealed) and "refresh-123" not in json.dumps(sealed)
    assert client.get("/integrations/upwork").json()["connected"] is True


def test_callback_refuses_a_state_this_account_did_not_start(client, account, upwork_server):
    back = client.get("/integrations/upwork/callback?code=abc&state=forged", follow_redirects=False)
    assert "upwork=error" in back.headers["location"]
    assert client.get("/integrations/upwork").json()["connected"] is False


async def test_expired_token_refreshes_and_disconnect_revokes(client, account, upwork_server):
    _, query = sign_in(client)
    client.get(f"/integrations/upwork/callback?code=abc&state={query['state'][0]}", follow_redirects=False)
    from apps.api.auth.tokens import load_tokens, save_tokens
    save_tokens(account["id"], "upwork", {**load_tokens(account["id"], "upwork"), "expires_at": time.time() - 5})
    assert await upwork.access_token(account["id"]) == "access-456"
    assert load_tokens(account["id"], "upwork")["refresh_token"] == "refresh-123"
    assert client.delete("/integrations/upwork").json() == {"connected": False}
    assert ("/revoke", {"token": ["refresh-123"], "token_type_hint": ["refresh_token"], "client_id": ["gigbid-client"]}) in upwork_server
    assert client.get("/integrations/upwork").json()["connected"] is False


def test_tokens_need_an_encryption_key(account, monkeypatch):
    monkeypatch.setattr(settings(), "token_encryption_key", "")
    with transaction() as db:
        put_record(db, account["id"], "oauth_token", "upwork", {"sealed": "x"})
    from apps.api.auth.tokens import load_tokens
    with pytest.raises(RuntimeError, match="TOKEN_ENCRYPTION_KEY"):
        load_tokens(account["id"], "upwork")
