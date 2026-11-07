from sqlalchemy import select, text

from agent.handoffs import JobSpec, WriteRequest
from agent.model import config
from apps.api.db import Approval, Run, User, digest, get_record, put_record, transaction, uid


def lock_decision(db, tenant):
    # Match the marketplace tenant lock before touching approval/run rows.
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    else:
        db.scalar(select(User).where(User.id == tenant).with_for_update())


def binding(run_id, preview, context=None):
    value = {"run_id": run_id, "preview": preview}
    if context is not None:
        value["context"] = context
    return digest(value)


def stage_approval(db, tenant, run_id, preview, context=None):
    bound = binding(run_id, preview, context)
    approval = db.scalar(select(Approval).where(Approval.tenant == tenant,
                                              Approval.run_id == run_id,
                                              Approval.binding == bound,
                                              Approval.decision != "invalidated"))
    if not approval:
        for old in db.scalars(select(Approval).where(Approval.tenant == tenant,
                                                     Approval.run_id == run_id,
                                                     Approval.consumed.is_(False))):
            old.decision = "invalidated"
        approval = Approval(id=uid(), tenant=tenant, run_id=run_id, binding=bound, payload=preview)
        db.add(approval)
        if context is not None:
            put_record(db, tenant, "approval_context", approval.id, context)
    return approval


def validate_approval(db, tenant: str, request: WriteRequest, preview: dict):
    approval = db.get(Approval, request.approval_id or "")
    if not approval or approval.tenant != tenant or approval.run_id != request.run_id:
        raise PermissionError("A tenant-bound approval is required")
    if approval.decision != "approved" or approval.consumed:
        raise PermissionError("Approval is not active")
    context_row = get_record(db, tenant, "approval_context", approval.id)
    context = context_row.value if context_row else None
    if approval.binding != binding(request.run_id, preview, context):
        raise PermissionError("Draft, destination, price or cost changed; renewed approval required")
    run = db.get(Run, request.run_id)
    if not run or run.tenant != tenant or run.status not in ("queued", "running", "awaiting_approval", "recoverable"):
        raise PermissionError("Run is not executable")
    if context is not None:
        receipt = get_record(db, tenant, "approval_receipt", approval.id)
        if not receipt or receipt.value["decision"] != "approve":
            raise PermissionError("A persisted human decision is required")
        user = db.get(User, tenant)
        if (context["thread"] != f"{tenant}:{request.run_id}"
            or context["policy"] != digest(config()["policy"])
            or context["profile"] != digest(user.profile)):
            raise PermissionError("Approval context changed; renewed review required")
        if request.action.kind == "proposal":
            job = get_record(db, tenant, "job", request.action.destination)
            if not job or context["job"] != digest(JobSpec.model_validate(job.value).model_dump()):
                raise PermissionError("Job changed; renewed analysis required")
    for evidence_id, expected in request.action.evidence_hashes.items():
        record = get_record(db, tenant, "evidence", evidence_id)
        if not record or record.value["content_hash"] != expected:
            raise PermissionError("Evidence changed or was deleted; renew approval")
    return approval


def approval_context(state):
    return {"thread": f"{state['tenant']}:{state['run_id']}",
            "policy": digest(config()["policy"]), "profile": digest(state["profile"]),
            "job": digest(JobSpec.model_validate(state["job"]).model_dump()) if not state.get("conversation") else None}


def validate_resume(state, response):
    """An interrupt payload is data, not proof that an authorized human decided."""
    with transaction() as db:
        approval = db.get(Approval, state["approval_id"])
        receipt = get_record(db, state["tenant"], "approval_receipt", state["approval_id"])
        context = get_record(db, state["tenant"], "approval_context", state["approval_id"])
        expected = {"approve": "approved", "reject": "rejected", "edit": "invalidated", "regenerate": "invalidated"}
        if (not approval or approval.tenant != state["tenant"] or approval.run_id != state["run_id"]
            or not receipt or receipt.value.get("response_hash") != digest(response)
            or approval.decision != expected.get(response.get("decision"))
            or not context or approval.binding != binding(state["run_id"], state["preview"], context.value)):
            raise PermissionError("Interrupt resume requires the matching persisted human decision")
