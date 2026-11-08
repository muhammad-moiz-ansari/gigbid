import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from apps.api.auth.service import current_session, current_user
from apps.api.db import Event, User, transaction
from apps.api.routers.workflow import owned_run
from apps.api.safety import redact
from apps.api.schemas.api import EventPage, RunEvent

router = APIRouter()


def event_page(tenant, run_id, after, limit=100):
    with transaction() as db:
        owned_run(db, tenant, run_id)
        rows = list(db.scalars(select(Event).where(Event.tenant == tenant,
            Event.run_id == run_id, Event.id > after).order_by(Event.id).limit(limit + 1)))
        return EventPage(events=[RunEvent(id=e.id, name=e.name, payload=redact(e.payload),
                                         created=e.created, trace_id=e.trace_id) for e in rows[:limit]],
                         next_cursor=rows[min(len(rows), limit) - 1].id if rows else after,
                         has_more=len(rows) > limit)


@router.get("/runs/{run_id}/history", response_model=EventPage)
def run_history(run_id: str, after: int = Query(default=0, ge=0, le=2**63-1),
                limit: int = Query(default=100, ge=1, le=500), user: User = Depends(current_user)):
    return event_page(user.id, run_id, after, limit)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, after: int = Query(default=0, ge=0, le=2**63-1),
                     user: User = Depends(current_user)):
    with transaction() as db:
        owned_run(db, user.id, run_id)
    try:
        last = int(request.headers.get("last-event-id", "0"))
        if not 0 <= last <= 2**63-1:
            raise ValueError()
        cursor = max(after, last)
    except ValueError:
        raise HTTPException(422, "Invalid event cursor") from None

    async def events():
        nonlocal cursor
        yield "retry: 1500\n\n"
        while not await request.is_disconnected():
            try:
                current_session(request)
            except HTTPException:
                yield 'event: session-expired\ndata: {}\n\n'
                return
            with transaction() as db:
                exists = db.get(User, user.id) is not None
            if not exists:
                yield 'event: session-expired\ndata: {}\n\n'
                return
            page = event_page(user.id, run_id, cursor)
            for event in page.events:
                cursor = event.id
                yield f"id: {event.id}\ndata: {json.dumps(event.model_dump())}\n\n"
            if not page.events:
                yield ": heartbeat\n\n"
            if not page.has_more:
                await asyncio.sleep(0.75)
    return StreamingResponse(events(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
