from datetime import datetime, timedelta, timezone

from agent.handoffs import WriteRequest, WriteResult
from apps.api.approvals import validate_approval
from apps.api.db import digest, get_record, put_record, transaction, uid
from mcp_servers.common import READ, WRITE, audited, make_server, serve

mcp = make_server("GigBid Workspace (local mock)", 8003)


@mcp.tool(annotations=READ)
def free_slots() -> list[dict]:
    """Read synthetic calendar slots; these are not connected calendar availability."""
    with audited("free_slots", {}) as tenant:
        start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        slots = [{"start": (start + timedelta(hours=i)).isoformat(), "minutes": 30,
                  "synthetic": True} for i in range(3)]
        with transaction() as db:
            return [s for s in slots if not get_record(db, tenant, "workspace_hold", s["start"])]


def _write(request, kind):
    if request.action.kind != kind:
        raise ValueError("Wrong workspace action kind")
    with audited(f"workspace_{kind}", request.model_dump()) as tenant:
        preview = WriteResult(mode="workspace-mock", dry_run=True, payload=request.action.model_dump())
        if request.dry_run:
            return preview
        with transaction() as db:
            key = "workspace:" + request.idempotency_key
            prior = get_record(db, tenant, "idempotency", key)
            fingerprint = digest(request.action.model_dump())
            if prior:
                if prior.value["fingerprint"] != fingerprint:
                    raise ValueError("Idempotency conflict")
                return WriteResult.model_validate(prior.value["result"])
            approval = validate_approval(db, tenant, request, preview.model_dump(exclude={"effect_id"}))
            result = WriteResult(mode="workspace-mock", dry_run=False, payload=request.action.model_dump(),
                                 effect_id=uid(), status="tentative" if kind == "hold" else "drafted")
            put_record(db, tenant, "workspace_hold" if kind == "hold" else "email_draft",
                       request.action.destination, result.model_dump())
            put_record(db, tenant, "idempotency", key, {"fingerprint": fingerprint, "result": result.model_dump()})
            approval.consumed = True
            return result


@mcp.tool(annotations=WRITE)
def create_interview_hold(request: WriteRequest) -> WriteResult:
    """Preview or create an approved tentative hold in the local mock calendar."""
    return _write(request, "hold")


@mcp.tool(annotations=WRITE)
def create_email_draft(request: WriteRequest) -> WriteResult:
    """Preview or save an approved local email draft; never sends email."""
    return _write(request, "email")


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
