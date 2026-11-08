"""Connected accounts: Upwork sign-in for live mode. Writes to Upwork still need approval in GigBid."""
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from mcp.shared.exceptions import McpError

from apps.api.auth import upwork
from apps.api.auth.service import current_user
from apps.api.config import settings
from apps.api.db import User
from mcp_servers.marketplace.adapters.upwork_live import UpworkAdapter

router = APIRouter(tags=["integrations"])
FAILURES = (upwork.UpworkError, McpError, httpx.HTTPError, RuntimeError)


@router.get("/integrations/upwork")
def upwork_status(user: User = Depends(current_user)) -> dict:
    return upwork.status(user.id)


@router.post("/integrations/upwork/connect")
async def upwork_connect(user: User = Depends(current_user)) -> dict:
    try:
        return {"authorize_url": await upwork.start(user.id)}
    except FAILURES as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/integrations/upwork/callback")
async def upwork_callback(code: str = "", state: str = "", error: str = "", user: User = Depends(current_user)):
    target = f"{settings().web_origin}/settings?upwork="
    if error:
        return RedirectResponse(target + "error&reason=" + quote(error[:80]))
    try:
        await upwork.finish(user.id, code, state)
    except FAILURES as exc:
        return RedirectResponse(target + "error&reason=" + quote(str(exc)[:120]))
    return RedirectResponse(target + "connected")


@router.post("/integrations/upwork/check")
async def upwork_check(user: User = Depends(current_user)) -> dict:
    try:
        return {"tools": await upwork.tools(user.id)}
    except FAILURES as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/integrations/upwork/acknowledge-policy")
def upwork_acknowledge_policy(user: User = Depends(current_user)) -> dict:
    """Records Upwork's payment-policy acknowledgement; the Settings button sends it only on the user's click."""
    try:
        UpworkAdapter().acknowledge_policy(user.id)
    except FAILURES as exc:
        raise HTTPException(503, str(exc)) from None
    return {"acknowledged": True}


@router.delete("/integrations/upwork")
async def upwork_disconnect(user: User = Depends(current_user)) -> dict:
    await upwork.disconnect(user.id)
    return {"connected": False}
