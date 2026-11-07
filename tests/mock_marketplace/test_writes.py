import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from agent.handoffs import Action, WriteRequest
from agent.marketplace_port import AmbiguousWrite, IdempotencyConflict
from apps.api.db import Approval, Record, User, get_record, transaction
from dev_support.mock_marketplace.config import FaultScenario
from dev_support.mock_marketplace.seed import seed_marketplace
from dev_support.mock_marketplace.service import MockMarketplace


def snapshot(tenant):
    with transaction() as db:
        records = [
            (r.kind, r.key, r.value)
            for r in db.scalars(
                select(Record).where(Record.tenant == tenant).order_by(Record.kind, Record.key)
            )
        ]
        approvals = [
            (a.id, a.decision, a.consumed)
            for a in db.scalars(
                select(Approval).where(Approval.tenant == tenant).order_by(Approval.id)
            )
        ]
        return records, approvals


def test_dry_run_is_exact_and_side_effect_free(world, authorize):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    before = snapshot(tenant)
    preview = mock.write(tenant, request.model_copy(update={"dry_run": True}))
    assert snapshot(tenant) == before
    assert preview.payload == request.action.model_dump()
    assert preview.connects_cost == 8 and preview.effect_id is None
    assert mock.reconcile(tenant, request.idempotency_key) is None
    with transaction() as db:
        db.get(Approval, request.approval_id).decision = "pending"
    with pytest.raises(PermissionError, match="not active"):
        mock.write(tenant, request)
    assert mock.balance(tenant)["spent"] == 0


def test_replay_survives_reopen_and_changed_job(world, authorize):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    first = mock.write(tenant, request)
    with transaction() as db:
        db.delete(get_record(db, tenant, "job", "mock-api"))
    reopened = MockMarketplace()
    assert reopened.write(tenant, request) == first
    assert reopened.reconcile(tenant, request.idempotency_key) == first
    assert len(reopened.events(tenant)) == 1
    assert reopened.balance(tenant)["spent"] == 8
    code = (
        "from dev_support.mock_marketplace.service import MockMarketplace; "
        f"print(MockMarketplace().reconcile({tenant!r}, {request.idempotency_key!r}).effect_id)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True, timeout=30
    )
    assert result.stdout.strip() == first.effect_id


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", "Changed text"),
        ("price", 250),
        ("destination", "mock-web"),
        ("version", 2),
        ("kind", "draft"),
    ],
)
def test_payload_conflicts_do_not_repeat_effects(world, authorize, field, value):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    mock.write(tenant, request)
    changed = request.model_copy(
        update={"action": request.action.model_copy(update={field: value})}
    )
    with pytest.raises(IdempotencyConflict, match="different payload"):
        mock.write(tenant, changed)
    with pytest.raises(IdempotencyConflict):
        mock.write(tenant, request.model_copy(update={"run_id": "different-run"}))
    assert mock.balance(tenant)["spent"] == 8
    assert len(mock.events(tenant)) == 1


def test_concurrent_retries_charge_once(world, authorize):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: MockMarketplace().write(tenant, request), range(8)))
    assert len({r.effect_id for r in results}) == 1
    assert mock.balance(tenant)["spent"] == 8
    assert len(mock.events(tenant)) == 1


def test_different_keys_cannot_resubmit_same_job(world, authorize):
    mock, tenant, _ = world
    first, second = authorize(mock, tenant), authorize(mock, tenant)
    mock.write(tenant, first)
    with pytest.raises(ValueError, match="already been submitted"):
        mock.write(tenant, second)
    assert mock.balance(tenant)["spent"] == 8


def test_ambiguous_result_is_reconciled_without_second_charge(world, authorize):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    mock.set_fault(tenant, FaultScenario(mode="ambiguous_write", remaining=1))
    with pytest.raises(AmbiguousWrite) as error:
        mock.write(tenant, request)
    assert error.value.idempotency_key == request.idempotency_key
    result = MockMarketplace().reconcile(tenant, request.idempotency_key)
    assert result and result.status == "submitted"
    assert mock.write(tenant, request) == result
    assert mock.balance(tenant)["spent"] == 8


def test_transaction_failure_rolls_back_charge_approval_and_effect(world, authorize, monkeypatch):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    before = snapshot(tenant)

    def crash(*args):
        raise RuntimeError("Simulated crash after charge but before commit")

    monkeypatch.setattr(mock, "_event", crash)
    with pytest.raises(RuntimeError, match="Simulated crash"):
        mock.write(tenant, request)
    assert snapshot(tenant) == before
    assert MockMarketplace().write(tenant, request).connects_cost == 8


@pytest.mark.parametrize("limit,balance", [(7, 100), (100, 7)])
def test_budget_failures_do_not_consume_approval(world, authorize, limit, balance):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    with transaction() as db:
        db.get(User, tenant).profile = {"weekly_connects": limit}
        account = get_record(db, tenant, "account", "connects")
        account.value = {**account.value, "balance": balance}
    before = snapshot(tenant)
    with pytest.raises(ValueError, match="Insufficient"):
        mock.write(tenant, request)
    assert snapshot(tenant) == before


def test_weekly_rollover_and_reseed_preserve_accounting(world, authorize):
    mock, tenant, clock = world
    with transaction() as db:
        db.get(User, tenant).profile = {"weekly_connects": 10}
    mock.write(tenant, authorize(mock, tenant))
    second = authorize(mock, tenant, destination="mock-web")
    with pytest.raises(ValueError, match="weekly"):
        mock.write(tenant, second)
    clock[0] += 7 * 86400
    assert mock.balance(tenant)["weekly_spent"] == 0
    mock.write(tenant, second)
    seed_marketplace(tenant)
    assert mock.balance(tenant)["weekly_spent"] == 10
    assert mock.balance(tenant)["spent"] == 18
    assert mock.balance(tenant)["balance"] == 82


def test_changed_cost_requires_renewed_approval(world, authorize):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    with transaction() as db:
        job = get_record(db, tenant, "job", "mock-api")
        job.value = {**job.value, "connects": 9}
    with pytest.raises(PermissionError, match="cost changed"):
        mock.write(tenant, request)
    assert mock.balance(tenant)["spent"] == 0


def test_drafts_and_messages_are_idempotent_and_free(world, authorize):
    mock, tenant, _ = world
    draft = authorize(mock, tenant, kind="draft")
    first = mock.write(tenant, draft)
    assert first.status == "drafted" and mock.write(tenant, draft) == first
    mock.write(tenant, authorize(mock, tenant))
    message = authorize(mock, tenant, kind="message")
    reply = mock.write(tenant, message)
    assert reply.status == "sent" and mock.write(tenant, message) == reply
    assert len(mock.messages(tenant, "mock-api")) == 1
    assert mock.balance(tenant)["spent"] == 8
    event = mock.events(tenant)[-1]
    assert event["kind"] == "message" and event["status"] == "sent"
    assert event["message_id"] == reply.effect_id and event["proposal_id"] is None
    invalid = WriteRequest(
        action=Action(kind="hold", destination="slot", text="hold"),
        run_id="test",
        idempotency_key="unsupported-kind",
    )
    with pytest.raises(ValueError, match="only supports"):
        mock.write(tenant, invalid)
