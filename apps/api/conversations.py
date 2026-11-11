"""Conversation turns: each new client message continues the same durable thread."""
from sqlalchemy import select

from apps.api.db import Approval, Record, Run, transaction, uid
from apps.api.routers.workflow import dispatch, view


def latest_inbound(db, tenant, conversation):
    inbound = [r.value["id"] for r in db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == "message")
                                                  .order_by(Record.created))
               if r.value["conversation"] == conversation and r.value.get("direction") == "inbound"]
    return inbound[-1] if inbound else None


def queue_reply(tenant, conversation):
    """Queues a reply turn unless the latest client message is already being answered."""
    with transaction() as db:
        latest = latest_inbound(db, tenant, conversation)
        if not latest:
            return None
        run = db.scalar(select(Run).where(Run.tenant == tenant, Run.kind == "conversation",
                                          Run.subject == conversation))
        if not run:
            run = Run(id=uid(), tenant=tenant, kind="conversation", subject=conversation, state={}, status="queued")
            db.add(run)
            db.flush()
        elif run.status in ("queued", "running") or run.state.get("reply_to") == latest:
            return view(run)
        else:
            # A newer client message makes any pending review of the old reply stale.
            for approval in db.scalars(select(Approval).where(Approval.tenant == tenant, Approval.run_id == run.id,
                                                              Approval.consumed.is_(False))):
                approval.decision = "invalidated"
            run.resume, run.status, run.lease_until = {"decision": "new_message"}, "queued", 0
        result = view(run)
    dispatch(result.id)
    return result
