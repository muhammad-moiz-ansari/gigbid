from sqlalchemy import select

from agent.handoffs import WriteRequest
from apps.api.db import Approval, Run, digest, get_record, uid


def binding(run_id, preview):
    return digest({"run_id": run_id, "preview": preview})


def stage_approval(db, tenant, run_id, preview):
    bound = binding(run_id, preview)
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
    return approval


def validate_approval(db, tenant: str, request: WriteRequest, preview: dict):
    approval = db.get(Approval, request.approval_id or "")
    if not approval or approval.tenant != tenant or approval.run_id != request.run_id:
        raise PermissionError("A tenant-bound approval is required")
    if approval.decision != "approved" or approval.consumed:
        raise PermissionError("Approval is not active")
    if approval.binding != binding(request.run_id, preview):
        raise PermissionError("Draft, destination, price or cost changed; renewed approval required")
    run = db.get(Run, request.run_id)
    if not run or run.tenant != tenant or run.status not in ("queued", "running", "awaiting_approval", "recoverable"):
        raise PermissionError("Run is not executable")
    for evidence_id, expected in request.action.evidence_hashes.items():
        record = get_record(db, tenant, "evidence", evidence_id)
        if not record or record.value["content_hash"] != expected:
            raise PermissionError("Evidence changed or was deleted; renew approval")
    return approval
