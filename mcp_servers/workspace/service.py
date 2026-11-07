"""Local calendar/email drafts only. No external accounts, invitations or email sends."""

from datetime import datetime, timedelta, timezone

from agent.handoffs import WriteRequest, WriteResult
from apps.api.approvals import validate_approval
from apps.api.db import digest, get_record, put_record, transaction, uid
from dev_support.mock_marketplace.service import _lock
from mcp_servers.schemas import CalendarSlot


def free_slots(tenant):
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    slots = [CalendarSlot(start=(start + timedelta(hours=i)).isoformat()) for i in range(3)]
    with transaction() as db:
        return [s for s in slots if not get_record(db, tenant, "workspace_hold", s.start)]


def validate_action(tenant, action, db):
    if action.price != 0:
        raise ValueError("Workspace drafts/holds have no marketplace price or Connects cost")
    if not action.text.strip():
        raise ValueError("Workspace action text cannot be blank")
    if action.kind == "hold":
        try:
            start = datetime.fromisoformat(action.destination)
        except ValueError:
            raise ValueError("Hold destination must be an ISO datetime") from None
        if not start.tzinfo:
            raise ValueError("Hold start must have an explicit timezone")
        # Canonical UTC prevents equivalent timestamps reserving the same slot twice.
        if start.astimezone(timezone.utc).isoformat() != action.destination:
            raise ValueError("Use the exact canonical UTC slot returned by free_slots")
        if start <= datetime.now(timezone.utc):
            raise ValueError("Hold slot is no longer in the future; renew approval")
        if get_record(db, tenant, "workspace_hold", action.destination):
            raise ValueError("Hold slot was reserved; renew approval")
        if action.destination not in {slot.start for slot in free_slots(tenant)}:
            raise ValueError("Hold must match a currently offered local mock slot")
    elif action.kind == "email":
        import re

        from apps.api.safety import EMAIL

        if not re.fullmatch(EMAIL, action.destination):
            raise ValueError("Email draft destination must be a valid email address")
    else:
        raise ValueError("Wrong workspace action kind")


def write(tenant: str, request: WriteRequest) -> WriteResult:
    action = request.action
    preview = WriteResult(mode="workspace-mock", dry_run=True, payload=action.model_dump())
    with transaction() as db:
        if not request.dry_run:
            _lock(db, tenant)
            key = "workspace:" + request.idempotency_key
            fingerprint = digest({"run_id": request.run_id, "action": action.model_dump()})
            prior = get_record(db, tenant, "idempotency", key)
            if prior:
                if prior.value["fingerprint"] != fingerprint:
                    raise ValueError("Idempotency conflict")
                return WriteResult.model_validate(prior.value["result"])
        validate_action(tenant, action, db)
        if request.dry_run:
            return preview
        approval = validate_approval(db, tenant, request, preview.model_dump(exclude={"effect_id"}))
        result = WriteResult(
            mode="workspace-mock",
            dry_run=False,
            payload=action.model_dump(),
            effect_id=uid(),
            status="tentative" if action.kind == "hold" else "drafted",
        )
        put_record(
            db,
            tenant,
            "workspace_hold" if action.kind == "hold" else "email_draft",
            action.destination if action.kind == "hold" else result.effect_id,
            result.model_dump(),
        )
        put_record(
            db,
            tenant,
            "idempotency",
            key,
            {"fingerprint": fingerprint, "result": result.model_dump()},
        )
        approval.consumed = True
        return result
