from sqlalchemy import select, text

from agent.handoffs import JobSpec, WriteRequest, WriteResult
from agent.marketplace_port import Capabilities, Unavailable
from apps.api.db import (
    Record,
    User,
    digest,
    get_record,
    now,
    put_record,
    transaction,
    uid,
)


class MockMarketplace:
    """Original deterministic substitute, not instructor GigSim or a production mapping."""
    capabilities = Capabilities(True, True, True, True, True)

    def _fault(self, tenant, write=False):
        with transaction() as db:
            fault = get_record(db, tenant, "mock_control", "fault")
            mode = fault.value.get("mode") if fault else None
        if mode in ("outage", "rate_limit", "timeout"):
            raise Unavailable(f"Synthetic marketplace {mode}; work can be retried")
        return mode

    def search(self, tenant, query=""):
        self._fault(tenant)
        with transaction() as db:
            items = db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == "job"))
            return [JobSpec.model_validate(r.value) for r in items
                    if query.lower() in str(r.value).lower()]

    def job(self, tenant, job_id):
        self._fault(tenant)
        with transaction() as db:
            record = get_record(db, tenant, "job", job_id)
            if not record:
                raise ValueError("Job not found")
            return JobSpec.model_validate(record.value)

    def client_history(self, tenant, client_id):
        self._fault(tenant)
        with transaction() as db:
            record = get_record(db, tenant, "client", client_id)
            return record.value if record else {"verified": False, "spend": 0, "hires": 0}

    def balance(self, tenant):
        self._fault(tenant)
        with transaction() as db:
            record = get_record(db, tenant, "account", "connects")
            return record.value if record else {"balance": 0, "spent": 0}

    def messages(self, tenant, conversation):
        self._fault(tenant)
        with transaction() as db:
            records = db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == "message"))
            return [r.value for r in records if r.value["conversation"] == conversation]

    def events(self, tenant, after=0):
        with transaction() as db:
            records = db.scalars(select(Record).where(Record.tenant == tenant,
                                                     Record.kind == "market_event").order_by(Record.created))
            return [r.value for r in records if r.value["sequence"] > after]

    def write(self, tenant, request: WriteRequest):
        from apps.api.approvals import validate_approval
        fault = self._fault(tenant, write=True)
        action = request.action
        cost = self.job(tenant, action.destination).connects if action.kind == "proposal" else 0
        preview = {"mode": "mock", "dry_run": True, "payload": action.model_dump(),
                   "connects_cost": cost, "status": "preview"}
        if request.dry_run:
            return WriteResult(**preview)
        # Serialize SQLite writers before any reads; row locks cover Postgres balances.
        with transaction() as db:
            if db.bind.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            else:
                db.execute(select(User).where(User.id == tenant).with_for_update())
            fingerprint = digest({"run_id": request.run_id, "action": action.model_dump()})
            prior = get_record(db, tenant, "idempotency", request.idempotency_key)
            if prior:
                if prior.value["fingerprint"] != fingerprint:
                    raise ValueError("Idempotency key reused with different payload")
                return WriteResult.model_validate(prior.value["result"])
            approval = validate_approval(db, tenant, request, preview)
            account = get_record(db, tenant, "account", "connects")
            user = db.get(User, tenant)
            cap = user.profile.get("weekly_connects", 50)
            week = int(now() // (7 * 86400))
            values = account.value if account else {"balance": 0, "spent": 0}
            weekly = values.get("weekly_spent", 0) if values.get("week") == week else 0
            if values["balance"] < cost or weekly + cost > cap:
                raise ValueError("Insufficient balance or weekly Connects budget")
            if cost:
                account.value = {**values, "balance": values["balance"] - cost,
                                 "spent": values["spent"] + cost,
                                 "weekly_spent": weekly + cost, "week": week}
            effect_id = uid()
            status = "submitted" if action.kind == "proposal" else "sent" if action.kind == "message" else "drafted"
            result = WriteResult(mode="mock", dry_run=False, payload=action.model_dump(),
                                 connects_cost=cost, effect_id=effect_id, status=status)
            put_record(db, tenant, "idempotency", request.idempotency_key,
                       {"fingerprint": fingerprint, "result": result.model_dump()})
            put_record(db, tenant, "proposal" if action.kind in ("proposal", "draft") else "message",
                       effect_id, {**action.model_dump(), "id": effect_id, "status": status,
                                   "conversation": action.destination, "synthetic": True,
                                   "direction": "outbound", "run_id": request.run_id})
            existing = list(db.scalars(select(Record).where(Record.tenant == tenant,
                                                           Record.kind == "market_event")))
            put_record(db, tenant, "market_event", effect_id,
                       {"id": effect_id, "sequence": len(existing) + 1,
                        "subject": action.destination, "status": status, "synthetic": True})
            approval.consumed = True
        if fault == "ambiguous_write":
            raise Unavailable("Synthetic response lost after write; reconcile stable key")
        return result

    def reconcile(self, tenant, key):
        with transaction() as db:
            prior = get_record(db, tenant, "idempotency", key)
            return WriteResult.model_validate(prior.value["result"]) if prior else None
