"""Sign-in to Upwork's official MCP server: OAuth 2.1 with PKCE and dynamic client registration."""
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.model import config
from apps.api.auth.tokens import delete_tokens, load_tokens, save_tokens
from apps.api.config import settings
from apps.api.db import get_record, put_record, transaction

SYSTEM = "system"  # Owner of app-wide records such as the client registration.


class UpworkError(RuntimeError):
    pass


async def _post(url, **kwargs):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, **kwargs)
    if response.status_code >= 400:
        raise UpworkError(f"Upwork refused the request ({response.status_code}): {response.text[:200]}")
    return response.json()


async def metadata():
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(config()["upwork"]["metadata_url"])
    response.raise_for_status()
    return response.json()


async def client_id(meta):
    """Registers GigBid once per callback address and reuses the client id."""
    redirect = settings().upwork_redirect_uri
    with transaction() as db:
        saved = get_record(db, SYSTEM, "upwork_client", redirect)
        if saved:
            return saved.value["client_id"]
    registered = await _post(meta["registration_endpoint"], json={
        "client_name": "GigBid", "redirect_uris": [redirect], "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "none"})
    with transaction() as db:
        put_record(db, SYSTEM, "upwork_client", redirect, {"client_id": registered["client_id"]})
    return registered["client_id"]


async def start(tenant):
    """The Upwork sign-in address for this user, with a one-time state and a PKCE challenge."""
    meta = await metadata()
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with transaction() as db:
        put_record(db, tenant, "upwork_state", state, {"verifier": verifier, "at": time.time()})
    return meta["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": await client_id(meta), "redirect_uri": settings().upwork_redirect_uri,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
        "resource": config()["upwork"]["mcp_url"]})


def _keep(tokens):
    return {"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token"),
            "expires_at": time.time() + int(tokens.get("expires_in", 3600))}


async def finish(tenant, code, state):
    """Exchanges the code for tokens; the state must belong to the user who started the sign-in."""
    with transaction() as db:
        saved = get_record(db, tenant, "upwork_state", state)
        verifier = saved.value["verifier"] if saved and time.time() - saved.value["at"] < 600 else None
        if saved:
            db.delete(saved)
    if not verifier or not code:
        raise UpworkError("This Upwork sign-in expired or was not started from this account")
    meta = await metadata()
    tokens = await _post(meta["token_endpoint"], data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": settings().upwork_redirect_uri,
        "client_id": await client_id(meta), "code_verifier": verifier, "resource": config()["upwork"]["mcp_url"]})
    save_tokens(tenant, "upwork", _keep(tokens))


async def access_token(tenant):
    """A current access token, refreshed when it is about to expire."""
    tokens = load_tokens(tenant, "upwork")
    if not tokens:
        raise UpworkError("Upwork is not connected")
    if tokens["expires_at"] - time.time() < 60 and tokens.get("refresh_token"):
        meta = await metadata()
        fresh = await _post(meta["token_endpoint"], data={
            "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": await client_id(meta)})
        tokens = {**_keep(fresh), "refresh_token": fresh.get("refresh_token") or tokens["refresh_token"]}
        save_tokens(tenant, "upwork", tokens)
    return tokens["access_token"]


async def tools(tenant):
    """Lists the tools Upwork's MCP server offers this account; read-only, no side effects."""
    client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": config()["upwork"]["mcp_url"],
                                              "headers": {"Authorization": f"Bearer {await access_token(tenant)}"}}})
    try:
        async with client.session("upwork") as session:
            listed = (await session.list_tools()).tools
    except ExceptionGroup as group:
        raise group.exceptions[0] from None
    names = sorted(t.name for t in listed)
    with transaction() as db:
        put_record(db, tenant, "upwork_tools", "latest", {"names": names, "at": time.time()})
    return names


async def disconnect(tenant):
    """Revokes the refresh token at Upwork, deletes the stored tokens and, in live mode, Upwork-derived data."""
    tokens = load_tokens(tenant, "upwork")
    if tokens and tokens.get("refresh_token"):
        meta = await metadata()
        async with httpx.AsyncClient(timeout=20) as client:
            await client.post(meta["revocation_endpoint"], data={
                "token": tokens["refresh_token"], "token_type_hint": "refresh_token", "client_id": await client_id(meta)})
    delete_tokens(tenant, "upwork")
    if settings().marketplace_mode == "upwork":
        from worker.retention import purge
        await purge(tenant)


def status(tenant):
    with transaction() as db:
        saved = get_record(db, tenant, "upwork_tools", "latest")
        connected = bool(get_record(db, tenant, "oauth_token", "upwork"))
        return {"connected": connected, "tools": saved.value["names"] if saved and connected else []}
