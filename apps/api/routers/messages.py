from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from apps.api.auth.service import current_user
from apps.api.config import settings
from apps.api.conversations import queue_reply
from apps.api.db import Record, User, transaction
from apps.api.schemas.api import MessageInput, RunView
from dev_support.mock_marketplace.service import MockMarketplace

router = APIRouter(tags=["messages"])


@router.get("/messages")
def messages(user: User = Depends(current_user)) -> list[dict]:
    with transaction() as db:
        return [r.value for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                                 Record.kind == "message").order_by(Record.created))]


@router.post("/dev/client-message")
def mock_client(data: MessageInput, user: User = Depends(current_user)) -> dict:
    if settings().marketplace_mode != "mock":
        raise HTTPException(409, "Mock client controls unavailable in live mode")
    message = MockMarketplace().receive_message(user.id, data.conversation, data.text)
    queue_reply(user.id, data.conversation)
    return message


@router.post("/messages/{conversation}/draft", response_model=RunView)
def reply(conversation: str, user: User = Depends(current_user)):
    result = queue_reply(user.id, conversation)
    if not result:
        raise HTTPException(404, "No client conversation found")
    return result
