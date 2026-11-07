from datetime import datetime, timezone

import pytest

from agent.handoffs import Action, WriteRequest
from apps.api.approvals import stage_approval
from apps.api.db import Run, User, transaction, uid
from dev_support.mock_marketplace.seed import seed_marketplace
from dev_support.mock_marketplace.service import MockMarketplace


@pytest.fixture
def world():
    with transaction() as db:
        tenant = uid()
        db.add(
            User(
                id=tenant,
                email=f"{tenant}@example.test",
                password_hash="unused-test-hash",
                profile={"weekly_connects": 50},
            )
        )
    seed_marketplace(tenant)
    clock = [datetime(2026, 11, 2, 12, tzinfo=timezone.utc).timestamp()]
    return MockMarketplace(clock=lambda: clock[0]), tenant, clock


@pytest.fixture
def authorize():
    """Stage real approval records without starting any later-phase graph or worker."""

    def create(mock, tenant, *, kind="proposal", destination="mock-api", key=None, text=None):
        run_id = uid()
        request = WriteRequest(
            action=Action(
                kind=kind,
                destination=destination,
                text=text or "Proposed approach: Start with a scoped API.",
                price=500,
            ),
            run_id=run_id,
            idempotency_key=key or uid(),
        )
        preview = mock.write(tenant, request).model_dump(exclude={"effect_id"})
        with transaction() as db:
            db.add(Run(id=run_id, tenant=tenant, kind="bid", subject=uid(), status="running"))
            db.flush()
            approval = stage_approval(db, tenant, run_id, preview)
            approval.decision = "approved"
            approval_id = approval.id
        return request.model_copy(update={"approval_id": approval_id, "dry_run": False})

    return create
