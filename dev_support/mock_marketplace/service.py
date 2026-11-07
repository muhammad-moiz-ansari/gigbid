"""Durable, deterministic development marketplace. Never represents instructor GigSim."""

import math
from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import TypeAdapter
from sqlalchemy import select, text

from agent.handoffs import JobSpec, WriteRequest, WriteResult
from agent.marketplace_port import (
    AdapterReadiness,
    AmbiguousWrite,
    Capabilities,
    ClientHistory,
    ConnectsBalance,
    IdempotencyConflict,
    MarketplaceEvent,
    MarketplaceMessage,
    MarketplaceProposal,
    MarketplaceServerError,
    MarketplaceTimeout,
    NotFound,
    RateLimited,
    Unavailable,
)
from apps.api.db import Record, User, digest, get_record, now, put_record, transaction, uid
from dev_support.mock_marketplace.config import FaultScenario, SimulatorConfig


def _lock(db, tenant):
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
        user = db.get(User, tenant)
    else:
        user = db.scalar(select(User).where(User.id == tenant).with_for_update())
    if not user:
        raise PermissionError("Unknown marketplace tenant")
    return user


def _required(db, tenant, kind, key):
    record = get_record(db, tenant, kind, key)
    if not record:
        raise NotFound(f"{kind.capitalize()} not found")
    return record


def _week(timestamp):
    date = datetime.fromtimestamp(timestamp, timezone.utc).isocalendar()
    return f"{date.year}-W{date.week:02d}"


class MockMarketplace:
    capabilities = Capabilities(
        search=True,
        drafts=True,
        submit=True,
        messages=True,
        reconciliation=True,
        client_history=True,
        connects=True,
        proposals=True,
        events=True,
    )
    readiness = AdapterReadiness(
        mode="mock",
        implemented=True,
        contract_verified=True,
        externally_verified=False,
        synthetic=True,
        detail="Original local simulator; its contract is provisional, not GigSim",
    )

    def __init__(self, clock: Callable[[], float] = now):
        self.clock = clock

    def configure(self, tenant: str, config: SimulatorConfig):
        """Local-only control. New proposals snapshot these settings for reproducibility."""
        config = SimulatorConfig.model_validate(config)
        with transaction() as db:
            _lock(db, tenant)
            put_record(db, tenant, "mock_control", "config", config.model_dump())

    def set_fault(self, tenant: str, scenario: FaultScenario):
        scenario = FaultScenario.model_validate(scenario)
        with transaction() as db:
            _lock(db, tenant)
            put_record(db, tenant, "mock_control", "fault", scenario.model_dump())

    def _fault(self, tenant: str, operation: str, consume=True):
        with transaction() as db:
            if consume:
                _lock(db, tenant)
            elif not db.get(User, tenant):
                raise PermissionError("Unknown marketplace tenant")
            record = get_record(db, tenant, "mock_control", "fault")
            scenario = FaultScenario.model_validate(record.value if record else {})
            applies = not scenario.operations or operation in scenario.operations
            applies &= scenario.remaining != 0
            # A lost response affects executed writes, never reads or previews.
            if scenario.mode == "ambiguous_write" and (operation != "write" or not consume):
                applies = False
            if not applies:
                return "none"
            if consume and scenario.remaining is not None and scenario.mode != "none":
                record.value = {**record.value, "remaining": scenario.remaining - 1}
            mode, retry_after = scenario.mode, scenario.retry_after
        if mode == "outage":
            raise Unavailable("Synthetic marketplace outage; queued work may be retried")
        if mode == "rate_limit":
            raise RateLimited(retry_after)
        if mode == "server_error":
            raise MarketplaceServerError("Synthetic marketplace 503 server error")
        if mode == "timeout":
            raise MarketplaceTimeout("Synthetic marketplace timeout; no effect was performed")
        return mode

    def search(self, tenant: str, query: str = "") -> list[JobSpec]:
        self._fault(tenant, "search")
        words = query.casefold().split()
        with transaction() as db:
            items = db.scalars(
                select(Record)
                .where(Record.tenant == tenant, Record.kind == "job")
                .order_by(Record.key)
            )
            return [
                JobSpec.model_validate(r.value)
                for r in items
                if all(
                    word
                    in (
                        r.value["title"]
                        + " "
                        + r.value["description"]
                        + " "
                        + " ".join(r.value["skills"])
                    ).casefold()
                    for word in words
                )
            ]

    def job(self, tenant: str, job_id: str) -> JobSpec:
        self._fault(tenant, "job")
        with transaction() as db:
            return JobSpec.model_validate(_required(db, tenant, "job", job_id).value)

    def client_history(self, tenant: str, client_id: str) -> ClientHistory:
        self._fault(tenant, "client_history")
        with transaction() as db:
            return TypeAdapter(ClientHistory).validate_python(
                _required(db, tenant, "client", client_id).value
            )

    def balance(self, tenant: str) -> ConnectsBalance:
        self._fault(tenant, "balance")
        with transaction() as db:
            account = get_record(db, tenant, "account", "connects")
            value = account.value if account else {"balance": 0, "spent": 0}
            user = db.get(User, tenant)
            week = _week(self.clock())
            return {
                "balance": value["balance"],
                "spent": value["spent"],
                "week": week,
                "weekly_spent": value.get("weekly_spent", 0) if value.get("week") == week else 0,
                "weekly_limit": user.profile.get("weekly_connects", 50),
            }

    def proposal(self, tenant: str, proposal_id: str) -> MarketplaceProposal:
        self._fault(tenant, "proposal")
        with transaction() as db:
            return TypeAdapter(MarketplaceProposal).validate_python(
                _required(db, tenant, "proposal", proposal_id).value
            )

    def messages(self, tenant: str, conversation: str) -> list[MarketplaceMessage]:
        self._fault(tenant, "messages")
        with transaction() as db:
            records = db.scalars(
                select(Record)
                .where(Record.tenant == tenant, Record.kind == "message")
                .order_by(Record.created, Record.key)
            )
            return [
                TypeAdapter(MarketplaceMessage).validate_python(r.value)
                for r in records
                if r.value["conversation"] == conversation
            ]

    def events(self, tenant: str, after: int = 0) -> list[MarketplaceEvent]:
        if after < 0:
            raise ValueError("Event cursor cannot be negative")
        self._fault(tenant, "events")
        with transaction() as db:
            records = db.scalars(
                select(Record).where(Record.tenant == tenant, Record.kind == "market_event")
            )
            rows = [
                TypeAdapter(MarketplaceEvent).validate_python(
                    {"proposal_id": "legacy", "kind": "proposal", **r.value}
                )
                for r in records
                if r.value["sequence"] > after
            ]
            return sorted(rows, key=lambda row: row["sequence"])

    def _event(self, db, tenant, subject, proposal_id, status, message_id=None):
        counter = get_record(db, tenant, "market_counter", "events")
        # Compatibility with existing databases containing events but no counter.
        initial = (
            max(
                (
                    r.value["sequence"]
                    for r in db.scalars(
                        select(Record).where(Record.tenant == tenant, Record.kind == "market_event")
                    )
                ),
                default=0,
            )
            if not counter
            else 0
        )
        sequence = (counter.value["sequence"] if counter else initial) + 1
        put_record(db, tenant, "market_counter", "events", {"sequence": sequence})
        identity = uid()
        value = {
            "id": identity,
            "sequence": sequence,
            "subject": subject,
            "proposal_id": proposal_id,
            "status": status,
            "synthetic": True,
            "kind": "message" if message_id else "proposal",
        }
        if message_id:
            value["message_id"] = message_id
        put_record(db, tenant, "market_event", identity, value)

    def _preview(self, db, tenant, request):
        action = request.action
        if action.kind not in ("draft", "proposal", "message"):
            raise ValueError("Marketplace only supports draft, proposal and message actions")
        if not math.isfinite(action.price):
            raise ValueError("Price must be finite")
        cost = 0
        if action.kind in ("draft", "proposal"):
            job = JobSpec.model_validate(_required(db, tenant, "job", action.destination).value)
            cost = job.connects if action.kind == "proposal" else 0
        else:
            owned = get_record(db, tenant, "conversation", action.destination)
            if not owned:
                # Accept inbound conversations already recorded by the local API.
                owned = any(
                    r.value["conversation"] == action.destination
                    for r in db.scalars(
                        select(Record).where(Record.tenant == tenant, Record.kind == "message")
                    )
                )
            if not owned:
                raise NotFound("Conversation not found")
        return {
            "mode": "mock",
            "dry_run": True,
            "payload": action.model_dump(),
            "connects_cost": cost,
            "status": "preview",
        }

    def write(self, tenant: str, request: WriteRequest) -> WriteResult:
        from apps.api.approvals import validate_approval

        request = WriteRequest.model_validate(request)
        fault = self._fault(tenant, "write", consume=not request.dry_run)
        if request.dry_run:
            with transaction() as db:
                return WriteResult(**self._preview(db, tenant, request))
        action = request.action
        with transaction() as db:
            user = _lock(db, tenant)
            fingerprint = digest({"run_id": request.run_id, "action": action.model_dump()})
            prior = get_record(db, tenant, "idempotency", request.idempotency_key)
            # Replays precede mutable-cost, existence and consumed-approval checks.
            if prior:
                if prior.value["fingerprint"] != fingerprint:
                    raise IdempotencyConflict("Idempotency key reused with different payload")
                return WriteResult.model_validate(prior.value["result"])
            preview = self._preview(db, tenant, request)
            approval = validate_approval(db, tenant, request, preview)
            cost = preview["connects_cost"]
            if action.kind == "proposal" and get_record(
                db, tenant, "submitted_job", action.destination
            ):
                raise ValueError("A proposal has already been submitted for this job")
            if cost:
                account = _required(db, tenant, "account", "connects")
                values = account.value
                cap, week = user.profile.get("weekly_connects", 50), _week(self.clock())
                weekly = values.get("weekly_spent", 0) if values.get("week") == week else 0
                if values["balance"] < cost or weekly + cost > cap:
                    raise ValueError("Insufficient balance or weekly Connects budget")
                account.value = {
                    **values,
                    "balance": values["balance"] - cost,
                    "spent": values["spent"] + cost,
                    "weekly_spent": weekly + cost,
                    "week": week,
                }
            effect_id = uid()
            status = (
                "submitted"
                if action.kind == "proposal"
                else "sent"
                if action.kind == "message"
                else "drafted"
            )
            result = WriteResult(
                mode="mock",
                dry_run=False,
                payload=action.model_dump(),
                connects_cost=cost,
                effect_id=effect_id,
                status=status,
            )
            put_record(
                db,
                tenant,
                "idempotency",
                request.idempotency_key,
                {"fingerprint": fingerprint, "result": result.model_dump()},
            )
            if action.kind == "message":
                put_record(
                    db,
                    tenant,
                    "message",
                    effect_id,
                    {
                        "id": effect_id,
                        "text": action.text,
                        "conversation": action.destination,
                        "direction": "outbound",
                        "synthetic": True,
                    },
                )
                self._event(db, tenant, action.destination, None, "sent", message_id=effect_id)
            else:
                cfg = get_record(db, tenant, "mock_control", "config")
                simulation = SimulatorConfig.model_validate(cfg.value if cfg else {}).model_dump()
                put_record(
                    db,
                    tenant,
                    "proposal",
                    effect_id,
                    {
                        **action.model_dump(),
                        "id": effect_id,
                        "status": status,
                        "synthetic": True,
                        "run_id": request.run_id,
                        "simulation": simulation,
                    },
                )
                if action.kind == "proposal":
                    put_record(
                        db, tenant, "submitted_job", action.destination, {"proposal_id": effect_id}
                    )
                    put_record(
                        db,
                        tenant,
                        "conversation",
                        action.destination,
                        {"id": action.destination, "job_id": action.destination, "synthetic": True},
                    )
                self._event(db, tenant, action.destination, effect_id, status)
            approval.consumed = True
        if fault == "ambiguous_write":
            raise AmbiguousWrite(request.idempotency_key)
        return result

    def reconcile(self, tenant: str, key: str) -> WriteResult | None:
        self._fault(tenant, "reconcile")
        with transaction() as db:
            prior = get_record(db, tenant, "idempotency", key)
            return WriteResult.model_validate(prior.value["result"]) if prior else None

    def advance(self, tenant: str, tick_key: str) -> list[MarketplaceProposal]:
        """Explicit local tick; a repeated tick key never advances twice.

        No freelancer messages are sent or Connects spent. Outcomes use hash draws,
        not LLM clients or official GigSim preferences.
        """
        if not 8 <= len(tick_key) <= 200:
            raise ValueError("Tick key must contain 8 to 200 characters")
        with transaction() as db:
            _lock(db, tenant)
            prior = get_record(db, tenant, "simulation_tick", tick_key)
            if prior:
                return prior.value["results"]
            results = []
            records = list(
                db.scalars(
                    select(Record)
                    .where(Record.tenant == tenant, Record.kind == "proposal")
                    .order_by(Record.key)
                )
            )
            for record in records:
                proposal = record.value
                current = proposal["status"]
                if current not in ("submitted", "viewed", "replied", "interview"):
                    continue
                cfg = SimulatorConfig.model_validate(proposal.get("simulation", {}))
                context = {
                    "seed": cfg.seed,
                    "job": proposal["destination"],
                    "text": proposal["text"],
                    "price": proposal["price"],
                    "stage": current,
                }
                draw = int(digest(context)[:16], 16) / 2**64
                transitions = {
                    "viewed": ("replied", cfg.reply_probability),
                    "replied": ("interview", cfg.interview_probability),
                    "interview": ("hired", cfg.hire_probability),
                }
                if current == "submitted":
                    next_status = "viewed"
                else:
                    target, probability = transitions[current]
                    next_status = target if draw < probability else "lost"
                record.value = {**proposal, "status": next_status}
                self._event(db, tenant, proposal["destination"], proposal["id"], next_status)
                if next_status in ("replied", "interview", "hired"):
                    messages = {
                        "replied": "Could you explain your approach to this scope?",
                        "interview": "Are you available for an interview?",
                        "hired": "We would like to proceed with this synthetic project.",
                    }
                    identity = uid()
                    put_record(
                        db,
                        tenant,
                        "message",
                        identity,
                        {
                            "id": identity,
                            "conversation": proposal["destination"],
                            "text": messages[next_status],
                            "direction": "inbound",
                            "synthetic": True,
                        },
                    )
                results.append(TypeAdapter(MarketplaceProposal).validate_python(record.value))
            put_record(db, tenant, "simulation_tick", tick_key, {"results": results})
            return results
