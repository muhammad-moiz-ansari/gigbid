from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select

from apps.api.auth.service import current_user
from apps.api.config import settings
from apps.api.db import (
    Approval,
    Event,
    Record,
    Run,
    User,
    get_record,
    put_record,
    transaction,
    uid,
)
from apps.api.schemas.api import ApprovalDecision, FaultInput, MessageInput, RunView, Upload
from dev_support.seed import seed
from mcp_servers.marketplace.adapters import marketplace
from rag.ingest.loaders import delete_source, ingest_text, load_bytes

router = APIRouter(tags=["workflow"])


def owned_run(db, tenant, run_id):
    run = db.get(Run, run_id)
    if not run or run.tenant != tenant:
        raise HTTPException(404, "Run not found")
    return run


def view(run):
    return RunView(id=run.id, subject=run.subject, kind=run.kind, status=run.status,
                   state=run.state, trace_id=run.trace_id)


def enqueue(tenant, subject, kind="bid"):
    with transaction() as db:
        prior = db.scalar(select(Run).where(Run.tenant == tenant, Run.subject == subject,
                                            Run.kind == kind).order_by(Run.generation.desc()))
        if prior:
            return view(prior)
        run = Run(id=uid(), tenant=tenant, subject=subject, kind=kind, state={}, status="queued")
        db.add(run)
        db.flush()
        result = view(run)
    dispatch(result.id)
    return result


def dispatch(run_id):
    if settings().queue_mode == "celery":
        from worker.tasks import execute_run
        try:
            execute_run.delay(run_id)
        except Exception:
            # Durable DB outbox is drained by the periodic recovery task.
            pass


@router.post("/dev/seed")
def seed_data(user: User = Depends(current_user)) -> dict:
    if settings().marketplace_mode != "mock":
        raise HTTPException(409, "Synthetic seeding is allowed in mock mode only")
    seed(user.id)
    return {"synthetic": True, "message": "Original synthetic examples loaded; not official persona data"}


@router.put("/dev/fault")
def fault(data: FaultInput, user: User = Depends(current_user)) -> dict:
    if settings().marketplace_mode != "mock":
        raise HTTPException(409, "Fault controls are mock only")
    with transaction() as db:
        put_record(db, user.id, "mock_control", "fault", data.model_dump())
    return data.model_dump()


@router.get("/status")
def status(user: User = Depends(current_user)) -> dict:
    try:
        marketplace().balance(user.id)
        available, error = True, None
    except Exception as exc:
        available, error = False, str(exc)
    with transaction() as db:
        health = {r.key: r.value for r in db.scalars(select(Record).where(
            Record.tenant == user.id, Record.kind == "mcp_health"))}
    if health.get("marketplace", {}).get("available") is False:
        available = False
        error = "Marketplace MCP unavailable; queued work is retained. Retry after service recovery."
    return {"marketplace_mode": settings().marketplace_mode, "synthetic": settings().marketplace_mode == "mock",
            "marketplace_available": available, "error": error,
            "mcp_servers": health,
            "policy": "provisional-development-only", "model_profile": settings().model_profile}


@router.get("/jobs")
def jobs(query: str = "", user: User = Depends(current_user)) -> list[dict]:
    try:
        items = marketplace().search(user.id, query)
    except Exception as exc:
        raise HTTPException(503, str(exc)) from None
    with transaction() as db:
        runs = list(db.scalars(select(Run).where(Run.tenant == user.id, Run.kind == "bid")))
        by_subject = {r.subject: r for r in runs}
        result = []
        for job in items:
            run = by_subject.get(job.id)
            result.append({**job.model_dump(), "run_id": run.id if run else None,
                           "status": run.status if run else "new", "analysis": run.state if run else {}})
        return sorted(result, key=lambda j: j["analysis"].get("fit", {}).get("score", -1), reverse=True)


@router.get("/jobs/{job_id}")
def job(job_id: str, user: User = Depends(current_user)) -> dict:
    try:
        return marketplace().job(user.id, job_id).model_dump()
    except ValueError:
        raise HTTPException(404, "Job not found") from None


@router.post("/jobs/{job_id}/analyse", response_model=RunView)
def analyse(job_id: str, user: User = Depends(current_user)):
    marketplace().job(user.id, job_id)
    return enqueue(user.id, job_id)


@router.get("/runs", response_model=list[RunView])
def runs(user: User = Depends(current_user)):
    with transaction() as db:
        return [view(r) for r in db.scalars(select(Run).where(Run.tenant == user.id).order_by(Run.created.desc()))]


@router.get("/runs/{run_id}", response_model=RunView)
def run_detail(run_id: str, user: User = Depends(current_user)):
    with transaction() as db:
        return view(owned_run(db, user.id, run_id))


@router.post("/runs/{run_id}/retry", response_model=RunView)
def retry_run(run_id: str, user: User = Depends(current_user)):
    with transaction() as db:
        run = owned_run(db, user.id, run_id)
        if run.status not in ("recoverable", "needs_attention"):
            raise HTTPException(409, "Only failed or recoverable runs may be retried")
        run.status = "queued"
        run.lease_until = 0
        result = view(run)
    dispatch(run_id)
    return result


@router.get("/approvals")
def approvals(user: User = Depends(current_user)) -> list[dict]:
    with transaction() as db:
        return [{"id": a.id, "run_id": a.run_id, "decision": a.decision, "payload": a.payload}
                for a in db.scalars(select(Approval).where(Approval.tenant == user.id,
                                                           Approval.decision == "pending"))]


@router.post("/approvals/{approval_id}/decision", response_model=RunView)
def decide(approval_id: str, data: ApprovalDecision, user: User = Depends(current_user)):
    with transaction() as db:
        approval = db.scalar(select(Approval).where(Approval.id == approval_id,
                                                   Approval.tenant == user.id).with_for_update())
        if not approval:
            raise HTTPException(404, "Approval not found")
        run = owned_run(db, user.id, approval.run_id)
        if approval.decision != "pending" or run.status != "awaiting_approval":
            raise HTTPException(409, "Approval is stale or already resolved")
        if data.decision == "reject" and not data.reason.strip():
            raise HTTPException(422, "A rejection reason is required")
        if data.decision == "edit" and not (data.text or "").strip():
            raise HTTPException(422, "Edited draft text is required")
        approval.decision = {"approve": "approved", "reject": "rejected", "edit": "invalidated", "regenerate": "invalidated"}[data.decision]
        approval.reason = data.reason
        run.resume = data.model_dump()
        run.status = "queued"
        db.add(Event(tenant=user.id, run_id=run.id, trace_id=run.trace_id,
                     name=f"human:{data.decision}", payload={"approval_id": approval.id, "reason": data.reason}))
        result = view(run)
    dispatch(result.id)
    return result


@router.post("/runs/{run_id}/renew", response_model=RunView)
def renew(run_id: str, user: User = Depends(current_user)):
    with transaction() as db:
        run = owned_run(db, user.id, run_id)
        if run.status not in ("awaiting_approval", "recoverable") or not run.state.get("draft"):
            raise HTTPException(409, "No reviewable draft available to renew")
        for approval in db.scalars(select(Approval).where(Approval.tenant == user.id,
                                                         Approval.run_id == run_id,
                                                         Approval.consumed.is_(False))):
            approval.decision = "invalidated"
        run.resume, run.status, run.lease_until = {"decision": "renew"}, "queued", 0
        result = view(run)
    dispatch(run_id)
    return result


@router.get("/evidence")
def evidence(user: User = Depends(current_user)) -> list[dict]:
    with transaction() as db:
        return [r.value for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                                Record.kind == "evidence"))]


@router.post("/evidence")
def upload(data: Upload, user: User = Depends(current_user)) -> list[dict]:
    metadata = data.model_dump(exclude={"text"})
    return ingest_text(user.id, data.text, metadata)


@router.post("/evidence/file")
async def upload_file(file: UploadFile, user: User = Depends(current_user)) -> list[dict]:
    content = await file.read(settings().max_upload_bytes + 1)
    if len(content) > settings().max_upload_bytes:
        raise HTTPException(413, "Portfolio file exceeds upload limit")
    try:
        text = load_bytes(content, file.filename or "upload.txt")
        return ingest_text(user.id, text, {"source": file.filename or "upload.txt", "type": "cv"})
    except (ValueError, UnicodeError):
        raise HTTPException(422, "Cannot parse uploaded file") from None


@router.delete("/evidence/source/{source:path}")
def remove_source(source: str, user: User = Depends(current_user)) -> dict:
    delete_source(user.id, source)
    return {"deleted": source, "pending_approvals_invalidated": True}


@router.get("/messages")
def messages(user: User = Depends(current_user)) -> list[dict]:
    with transaction() as db:
        return [r.value for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                                 Record.kind == "message").order_by(Record.created))]


@router.post("/dev/client-message")
def mock_client(data: MessageInput, user: User = Depends(current_user)) -> dict:
    if settings().marketplace_mode != "mock":
        raise HTTPException(409, "Mock client controls unavailable in live mode")
    with transaction() as db:
        key = uid()
        value = {"id": key, "conversation": data.conversation, "text": data.text,
                 "direction": "inbound", "synthetic": True}
        put_record(db, user.id, "message", key, value)
    return value


@router.post("/messages/{conversation}/draft", response_model=RunView)
def reply(conversation: str, user: User = Depends(current_user)):
    with transaction() as db:
        incoming = [r for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                              Record.kind == "message"))
                    if r.value["conversation"] == conversation and r.value.get("direction") == "inbound"]
        if not incoming:
            raise HTTPException(404, "No client conversation found")
    return enqueue(user.id, conversation, "conversation")


@router.get("/pipeline")
def pipeline(user: User = Depends(current_user)) -> list[dict]:
    with transaction() as db:
        return [r.value for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                                 Record.kind == "pipeline"))]


@router.get("/analytics")
def analytics(user: User = Depends(current_user)) -> dict:
    with transaction() as db:
        recorded = [r.value for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                                    Record.kind == "pipeline"))]
        submitted = sum(r["status"] != "drafted" for r in recorded)
        replies = sum(r["status"] in ("replied", "interview", "hired") for r in recorded)
        hired = sum(r["status"] == "hired" for r in recorded)
        runs = list(db.scalars(select(Run).where(Run.tenant == user.id)))
        account = get_record(db, user.id, "account", "connects")
        return {"mode": settings().marketplace_mode, "synthetic": settings().marketplace_mode == "mock",
                "submitted": submitted, "replied": replies, "hired": hired,
                "reply_rate": replies / submitted if submitted else None,
                "hire_rate": hired / submitted if submitted else None,
                "connects": account.value if account else {},
                "runs": len(runs), "usage": [u for r in runs for u in r.state.get("usage", [])],
                "official_outcomes": "pending instructor simulator"}


@router.get("/memory")
def memory(user: User = Depends(current_user)) -> list[dict]:
    from agent.memory.store import list_memory
    return list_memory(user.id)


@router.delete("/memory/{memory_id}")
def forget(memory_id: str, user: User = Depends(current_user)) -> dict:
    from agent.memory.store import delete_memory
    delete_memory(user.id, memory_id)
    return {"deleted": memory_id}
