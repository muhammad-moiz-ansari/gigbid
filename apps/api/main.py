import json
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from apps.api.config import settings
from apps.api.db import engine
from apps.api.routers import auth, workflow
from apps.api.safety import redact
from apps.api.streaming import router as streaming_router

app = FastAPI(title="GigBid API", version="0.1.0", description="Local mock mode; official integrations pending")
app.add_middleware(CORSMiddleware, allow_origins=[settings().web_origin], allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE"],
                   allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "X-Trace-ID", "Last-Event-ID"])
log = logging.getLogger("gigbid")


@app.middleware("http")
async def trace(request: Request, call_next):
    trace_id = str(uuid4())
    request.state.trace_id = trace_id
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    # Paths, request bodies and credentials deliberately excluded.
    log.info(json.dumps(redact({"event": "http_request", "method": request.method,
                               "status": response.status_code, "trace_id": trace_id,
                               "seconds": time.monotonic() - started})))
    return response


@app.exception_handler(PermissionError)
async def forbidden(request, exc):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"ok": True, "mode": settings().marketplace_mode}


@app.get("/ready")
def ready() -> dict:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1 FROM users LIMIT 1"))
    return {"database": "ready", "marketplace_mode": settings().marketplace_mode,
            "official_integrations": "pending", "models": "check Ollama /api/tags separately"}


app.include_router(auth.router)
app.include_router(workflow.router)
app.include_router(streaming_router)
