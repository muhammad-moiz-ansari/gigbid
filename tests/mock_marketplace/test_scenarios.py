import pytest
from pydantic import ValidationError

from agent.marketplace_port import (
    MarketplaceServerError,
    MarketplaceTimeout,
    RateLimited,
    Unavailable,
)
from apps.api.db import get_record, transaction
from dev_support.mock_marketplace.config import FaultScenario, SimulatorConfig
from dev_support.mock_marketplace.seed import seed_marketplace
from dev_support.mock_marketplace.service import MockMarketplace


@pytest.mark.parametrize(
    "mode,error",
    [
        ("outage", Unavailable),
        ("rate_limit", RateLimited),
        ("server_error", MarketplaceServerError),
        ("timeout", MarketplaceTimeout),
    ],
)
def test_bounded_operation_faults_are_reproducible(world, mode, error):
    mock, tenant, _ = world
    scenario = FaultScenario(mode=mode, operations=["search"], remaining=2, retry_after=7)
    for _ in range(2):
        mock.set_fault(tenant, scenario)
        assert mock.balance(tenant)["balance"] == 100  # Unrelated operation unaffected.
        for _ in range(2):
            with pytest.raises(error) as exc:
                mock.search(tenant)
            if mode == "rate_limit":
                assert exc.value.status_code == 429 and exc.value.retry_after == 7
            elif mode == "server_error":
                assert exc.value.status_code == 503
        assert len(mock.search(tenant)) == 7


@pytest.mark.parametrize("mode", ["outage", "rate_limit", "server_error", "timeout"])
def test_prewrite_faults_have_no_external_effect(world, authorize, mode):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    mock.set_fault(tenant, FaultScenario(mode=mode, operations=["write"], remaining=1))
    with pytest.raises(Unavailable):
        mock.write(tenant, request)
    assert mock.balance(tenant)["spent"] == 0
    assert mock.reconcile(tenant, request.idempotency_key) is None
    assert not mock.events(tenant)
    assert mock.write(tenant, request).status == "submitted"


def test_preview_never_consumes_fault_plan(world, authorize):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    mock.set_fault(tenant, FaultScenario(mode="rate_limit", operations=["write"], remaining=1))
    for _ in range(2):
        with pytest.raises(RateLimited):
            mock.write(tenant, request.model_copy(update={"dry_run": True}))
        with transaction() as db:
            assert get_record(db, tenant, "mock_control", "fault").value["remaining"] == 1


def test_persistent_fault_clear_and_event_reconciliation_failure(world, authorize):
    mock, tenant, _ = world
    request = authorize(mock, tenant)
    mock.write(tenant, request)
    mock.set_fault(tenant, FaultScenario(mode="outage", operations=["events", "reconcile"]))
    for operation in (
        lambda: mock.events(tenant),
        lambda: mock.reconcile(tenant, request.idempotency_key),
    ):
        with pytest.raises(Unavailable):
            operation()
    seed_marketplace(tenant)  # Seeding must not silently clear outage settings.
    with pytest.raises(Unavailable):
        mock.events(tenant)
    mock.set_fault(tenant, FaultScenario())
    assert mock.reconcile(tenant, request.idempotency_key).status == "submitted"
    assert len(mock.events(tenant)) == 1


def test_all_success_outcomes_messages_and_monotonic_events(world, authorize):
    mock, tenant, _ = world
    mock.configure(
        tenant, SimulatorConfig(reply_probability=1, interview_probability=1, hire_probability=1)
    )
    submitted = mock.write(tenant, authorize(mock, tenant))
    # Existing proposals keep their captured config, even if future defaults change.
    mock.configure(
        tenant, SimulatorConfig(reply_probability=0, interview_probability=0, hire_probability=0)
    )
    for i, status in enumerate(("viewed", "replied", "interview", "hired")):
        results = mock.advance(tenant, f"success-tick-{i}")
        assert results[0]["status"] == status
        assert MockMarketplace().advance(tenant, f"success-tick-{i}") == results
    assert mock.advance(tenant, "finished-tick") == []
    events = mock.events(tenant)
    assert [e["status"] for e in events] == ["submitted", "viewed", "replied", "interview", "hired"]
    assert [e["sequence"] for e in events] == list(range(1, 6))
    assert len({e["id"] for e in events}) == 5
    assert all(e["synthetic"] and e["proposal_id"] == submitted.effect_id for e in events)
    assert mock.proposal(tenant, submitted.effect_id)["status"] == "hired"
    assert len(mock.messages(tenant, "mock-api")) == 3
    assert all(
        m["direction"] == "inbound" and m["synthetic"] for m in mock.messages(tenant, "mock-api")
    )
    assert mock.balance(tenant)["spent"] == 8


def test_nonreply_is_terminal_lost_and_drafts_do_not_advance(world, authorize):
    mock, tenant, _ = world
    mock.configure(tenant, SimulatorConfig(reply_probability=0))
    draft = mock.write(tenant, authorize(mock, tenant, kind="draft", destination="mock-web"))
    submitted = mock.write(tenant, authorize(mock, tenant))
    mock.advance(tenant, "failure-tick-1")
    assert mock.advance(tenant, "failure-tick-2")[0]["status"] == "lost"
    assert mock.advance(tenant, "failure-tick-3") == []
    assert mock.proposal(tenant, draft.effect_id)["status"] == "drafted"
    assert mock.proposal(tenant, submitted.effect_id)["status"] == "lost"
    assert not mock.messages(tenant, "mock-api")


def test_same_seed_and_content_reproduce_outcomes_across_tenants(world, authorize):
    from apps.api.db import User, uid

    mock, tenant, _ = world
    with transaction() as db:
        other = uid()
        db.add(
            User(
                id=other,
                email="reproducible@example.test",
                password_hash="unused-test-hash",
                profile={},
            )
        )
    seed_marketplace(other)
    # IDs/run UUIDs/wall time differ but do not affect the outcome draw.
    mock.write(tenant, authorize(mock, tenant))
    mock.write(other, authorize(mock, other))
    for i in range(4):
        one = mock.advance(tenant, f"same-seed-{i}")
        two = MockMarketplace().advance(other, f"same-seed-{i}")
        assert [p["status"] for p in one] == [p["status"] for p in two]


def test_simulator_settings_are_validated():
    for data in (
        {"reply_probability": -0.1},
        {"hire_probability": 1.1},
        {"seed": 1, "invented": True},
        {"reply_probability": float("nan")},
    ):
        with pytest.raises(ValidationError):
            SimulatorConfig.model_validate(data)
    for data in ({"remaining": -1}, {"operations": ["invented"]}, {"mode": "invented"}):
        with pytest.raises(ValidationError):
            FaultScenario.model_validate(data)


def test_simulator_tick_transaction_rolls_back(world, authorize, monkeypatch):
    mock, tenant, _ = world
    result = mock.write(tenant, authorize(mock, tenant))

    def crash(*args):
        raise RuntimeError("Simulated outcome crash")

    monkeypatch.setattr(mock, "_event", crash)
    with pytest.raises(RuntimeError, match="outcome crash"):
        mock.advance(tenant, "rollback-tick")
    assert MockMarketplace().proposal(tenant, result.effect_id)["status"] == "submitted"
    assert MockMarketplace().advance(tenant, "rollback-tick")[0]["status"] == "viewed"


def test_concurrent_tick_retries_do_not_advance_twice(world, authorize):
    from concurrent.futures import ThreadPoolExecutor

    mock, tenant, _ = world
    proposal = mock.write(tenant, authorize(mock, tenant))
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(
            pool.map(lambda _: MockMarketplace().advance(tenant, "same-concurrent-tick"), range(6))
        )
    assert all(result == outcomes[0] for result in outcomes)
    assert mock.proposal(tenant, proposal.effect_id)["status"] == "viewed"
    assert len(mock.events(tenant)) == 2
