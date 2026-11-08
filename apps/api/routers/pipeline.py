from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from apps.api.auth.service import current_user
from apps.api.config import settings
from apps.api.db import Record, User, transaction, uid
from dev_support.mock_marketplace.service import MockMarketplace
from worker.pipeline import cursor, handle

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline")
def pipeline(user: User = Depends(current_user)) -> list[dict]:
    with transaction() as db:
        return [r.value for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                                 Record.kind == "pipeline"))]


@router.post("/dev/advance")
def advance(user: User = Depends(current_user)) -> dict:
    """Mock only: advances simulated client outcomes now and applies the resulting events."""
    if settings().marketplace_mode != "mock":
        raise HTTPException(409, "Simulated outcomes are mock only")
    mock = MockMarketplace()
    outcomes = mock.advance(user.id, uid())
    handle(user.id, mock.events(user.id, cursor(user.id)))
    return {"synthetic": True, "advanced": len(outcomes)}
