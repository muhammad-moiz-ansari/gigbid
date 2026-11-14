import csv
import json

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from mcp.shared.exceptions import McpError
from sqlalchemy import select
from sqlalchemy.orm import object_session

from agent import budgets
from agent.marketplace_port import Unavailable
from apps.api.approvals import lock_decision
from apps.api.auth.service import current_user
from apps.api.config import settings
from apps.api.db import (
    Approval,
    Event,
    Record,
    Run,
    User,
    digest,
    now,
    put_record,
    transaction,
    uid,
)
from apps.api.schemas.api import (
    ApprovalDecision,
    FaultInput,
    GitHubImport,
    RunView,
    SkipInput,
    Upload,
)
from dev_support.instructor_jobs import DEFAULT_SOURCE, import_jobs, load_jobs
from dev_support.seed import seed
from mcp_servers.marketplace.adapters import marketplace
from rag.ingest.github import ingest_repository
from rag.ingest.loaders import delete_source, ingest_file, ingest_text
from rag.verify import paragraphs

router = APIRouter(tags=["workflow"])


def owned_run(db, tenant, run_id):
    run = db.get(Run, run_id)
    if not run or run.tenant != tenant:
        raise HTTPException(404, "Run not found")
    return run


def view(run):
    session = object_session(run)
    approval = session.get(Approval, run.state.get("approval_id")) if session and run.state.get("approval_id") else None
    return RunView(id=run.id, subject=run.subject, kind=run.kind, status=run.status,
                   state=run.state, trace_id=run.trace_id,
                   approval_status=approval.decision if approval and approval.tenant == run.tenant else None,
                   draft_paragraphs=paragraphs(run.state.get("draft", {}).get("text", "")))


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


@router.post("/dev/instructor-jobs")
def load_instructor_jobs(user: User = Depends(current_user)) -> dict[str, int]:
    if settings().marketplace_mode != "mock":
        raise HTTPException(409, "Historical jobs require simulation mode")
    try:
        jobs = load_jobs(DEFAULT_SOURCE, 100)
        if not jobs:
            raise ValueError("No usable fixed-price jobs in the instructor archive")
        import_jobs(user.id, jobs)
    except (OSError, ValueError, csv.Error) as exc:
        raise HTTPException(422, f"Instructor archive could not be imported: {exc}") from exc
    return {"count": len(jobs)}


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
        runs = {r.subject: r for r in db.scalars(select(Run).where(Run.tenant == user.id, Run.kind == "bid"))}
        skips = {r.key: r.value for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                                         Record.kind == "job_skip"))}
        dupes = {r.key: r.value["of"] for r in db.scalars(select(Record).where(Record.tenant == user.id,
                                                                               Record.kind == "duplicate_job"))}
        # Upwork's terms: in live mode GigBid neither ranks jobs nor archives them for you; you decide.
        live = settings().marketplace_mode == "upwork"
        auto_skip = user.profile.get("auto_skip", True) and not live
        result = []
        for job in items:
            run = runs.get(job.id)
            analysis = run.state if run else {}
            # Autonomy may archive skip recommendations automatically; it never sends anything.
            recommended = analysis.get("decision", {}).get("action") == "skip"
            reason = skips.get(job.id, {}).get("reason") or (analysis["decision"]["reason"] if recommended else None)
            result.append({**job.model_dump(), "run_id": run.id if run else None,
                           "status": run.status if run else "new", "analysis": analysis,
                           "duplicate_of": dupes.get(job.id), "skip_reason": reason,
                           "skipped": job.id in skips or (recommended and auto_skip),
                           "recommended_skip": recommended and not auto_skip and job.id not in skips})
        return result if live else sorted(result, key=lambda j: j["analysis"].get("fit", {}).get("score", -1), reverse=True)


@router.post("/jobs/{job_id}/skip")
def skip(job_id: str, data: SkipInput, user: User = Depends(current_user)) -> dict:
    with transaction() as db:
        put_record(db, user.id, "job_skip", job_id, {"reason": data.reason.strip() or "Skipped by you", "at": now()})
    return {"skipped": job_id}


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
        if owned_run(db, user.id, run_id).status not in ("recoverable", "needs_attention"):
            raise HTTPException(409, "Only failed or recoverable runs may be retried")
    budgets.acknowledge(user.id, run_id)  # The user accepts the unknown usage of an interrupted step.
    with transaction() as db:
        run = owned_run(db, user.id, run_id)
        run.status, run.lease_until = "queued", 0
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
        lock_decision(db, user.id)
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
        if data.decision == "regenerate" and data.paragraph >= len(paragraphs(
            run.state.get("draft", {}).get("text", ""))):
            raise HTTPException(422, "Select an existing draft paragraph")
        approval.decision = {"approve": "approved", "reject": "rejected", "edit": "invalidated", "regenerate": "invalidated"}[data.decision]
        approval.reason = data.reason
        run.resume = {**data.model_dump(), "approval_id": approval.id}
        put_record(db, user.id, "approval_receipt", approval.id,
                   {"decision": data.decision, "response_hash": digest(run.resume)})
        run.status = "queued"
        db.add(Event(tenant=user.id, run_id=run.id, trace_id=run.trace_id,
                     name=f"human:{data.decision}", payload={"approval_id": approval.id, "reason": data.reason}))
        result = view(run)
    dispatch(result.id)
    return result


@router.post("/runs/{run_id}/renew", response_model=RunView)
def renew(run_id: str, user: User = Depends(current_user)):
    with transaction() as db:
        lock_decision(db, user.id)
        run = owned_run(db, user.id, run_id)
        if run.status not in ("awaiting_approval", "recoverable") or not run.state.get("draft"):
            raise HTTPException(409, "No reviewable draft available to renew")
        for approval in db.scalars(select(Approval).where(Approval.tenant == user.id,
                                                         Approval.run_id == run_id,
                                                         Approval.consumed.is_(False))):
            approval.decision = "invalidated"
        run.resume, run.status, run.lease_until = {
            "decision": "renew", "version": run.state["draft"]["version"] + 1}, "queued", 0
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
async def upload_file(file: UploadFile, metadata: str = Form(default="{}"), user: User = Depends(current_user)) -> list[dict]:
    content = await file.read(settings().max_upload_bytes + 1)
    if len(content) > settings().max_upload_bytes:
        raise HTTPException(413, "Portfolio file exceeds upload limit")
    try:
        fields = json.loads(metadata)
        if not isinstance(fields, dict):
            raise ValueError("File metadata must be a JSON object")
        return ingest_file(user.id, content, file.filename or "upload.txt", fields)
    except (ValueError, UnicodeError):
        raise HTTPException(422, "Cannot parse uploaded file") from None


@router.post("/evidence/github")
async def import_repository(data: GitHubImport, user: User = Depends(current_user)) -> list[dict]:
    try:
        return await ingest_repository(user.id, data.repository, user.profile.get("persona", "own"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except (Unavailable, McpError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc) or "GitHub MCP is unavailable") from None


@router.get("/evidence/index")
def evidence_index(user: User = Depends(current_user)) -> dict:
    from rag.index.corpus import status
    return status(user.id)


@router.delete("/evidence/source/{source:path}")
def remove_source(source: str, user: User = Depends(current_user)) -> dict:
    delete_source(user.id, source)
    return {"deleted": source, "pending_approvals_invalidated": True}
