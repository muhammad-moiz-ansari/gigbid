import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from apps.api.auth.service import current_user
from apps.api.db import Event, User, transaction
from apps.api.routers.workflow import owned_run

router = APIRouter()


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, after: int = 0, user: User = Depends(current_user)):
    with transaction() as db:
        owned_run(db, user.id, run_id)
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        cursor = after

    async def events():
        nonlocal cursor
        while not await request.is_disconnected():
            with transaction() as db:
                rows = list(db.scalars(select(Event).where(Event.tenant == user.id,
                    Event.run_id == run_id, Event.id > cursor).order_by(Event.id).limit(100)))
            for event in rows:
                cursor = event.id
                payload = {"id": event.id, "name": event.name, "payload": event.payload,
                           "created": event.created, "trace_id": event.trace_id}
                yield f"id: {event.id}\ndata: {json.dumps(payload)}\n\n"
            if not rows:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.75)
    return StreamingResponse(events(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
