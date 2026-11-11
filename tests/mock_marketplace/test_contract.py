from dataclasses import asdict

import pytest
from pydantic import TypeAdapter

from agent.handoffs import Action, WriteRequest
from agent.marketplace_port import (
    ClientHistory,
    ConnectsBalance,
    MarketplaceEvent,
    MarketplaceMessage,
    MarketplacePort,
    MarketplaceProposal,
    Unavailable,
)
from apps.api.db import User, transaction, uid
from dev_support.mock_marketplace.seed import seed_marketplace
from mcp_servers.marketplace.adapters import marketplace


@pytest.mark.parametrize("mode", ["mock", "gigsim", "upwork"])
def test_every_adapter_has_explicit_port_and_accurate_readiness(mode):
    adapter = marketplace(mode)
    assert isinstance(adapter, MarketplacePort)
    assert adapter.readiness.mode == mode
    assert adapter.readiness.synthetic is (mode == "mock")
    assert adapter.readiness.implemented is (mode != "gigsim")
    assert not adapter.readiness.externally_verified
    if mode == "gigsim":
        assert not any(asdict(adapter.capabilities).values())
        request = WriteRequest(
            action=Action(kind="proposal", destination="unknown", text="test"),
            run_id="test",
            idempotency_key="test-key",
        )
        operations = [
            lambda: adapter.search("t"),
            lambda: adapter.job("t", "job"),
            lambda: adapter.client_history("t", "client"),
            lambda: adapter.balance("t"),
            lambda: adapter.proposal("t", "proposal"),
            lambda: adapter.messages("t", "c"),
            lambda: adapter.events("t"),
            lambda: adapter.write("t", request),
            lambda: adapter.reconcile("t", "key"),
        ]
        for operation in operations:
            with pytest.raises(Unavailable):
                operation()
        with pytest.raises(AttributeError):
            getattr(adapter, "invented_operation")


def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="Unknown marketplace mode"):
        marketplace("invented-platform")


def test_read_contracts_duplicates_and_untrusted_fixtures(world, authorize):
    mock, tenant, _ = world
    jobs = mock.search(tenant)
    assert len(jobs) == 7
    assert mock.job(tenant, "mock-api").model_dump(exclude={"id"}) == mock.job(
        tenant, "mock-api-duplicate"
    ).model_dump(exclude={"id"})
    assert "Telegram" in mock.job(tenant, "mock-scam").description
    assert "bypass approval" in mock.job(tenant, "mock-injection").description
    assert mock.search(tenant, "FASTAPI postgres")
    assert mock.search(tenant, "not-present-at-all") == []
    TypeAdapter(ClientHistory).validate_python(mock.client_history(tenant, "mock-client-1"))
    TypeAdapter(ConnectsBalance).validate_python(mock.balance(tenant))
    result = mock.write(tenant, authorize(mock, tenant))
    TypeAdapter(MarketplaceProposal).validate_python(mock.proposal(tenant, result.effect_id))
    reply = authorize(mock, tenant, kind="message", destination="mock-api")
    mock.write(tenant, reply)
    TypeAdapter(list[MarketplaceMessage]).validate_python(mock.messages(tenant, "mock-api"))
    TypeAdapter(list[MarketplaceEvent]).validate_python(mock.events(tenant))
    assert mock.events(tenant, after=mock.events(tenant)[-1]["sequence"]) == []
    with pytest.raises(ValueError, match="negative"):
        mock.events(tenant, after=-1)


def test_cross_tenant_reads_keys_and_approval_are_isolated(world, authorize):
    mock, tenant, _ = world
    request = authorize(mock, tenant, key="shared-stable-key")
    result = mock.write(tenant, request)
    with transaction() as db:
        other = uid()
        db.add(
            User(id=other, email="other@example.test", password_hash="unused-test-hash", profile={})
        )
    seed_marketplace(other)
    assert mock.reconcile(other, request.idempotency_key) is None
    assert mock.messages(other, "mock-api") == []
    assert mock.events(other) == []
    with pytest.raises(ValueError, match="not found"):
        mock.proposal(other, result.effect_id)
    with pytest.raises(PermissionError):
        mock.write(other, request)
    own = authorize(mock, other, key=request.idempotency_key)
    other_result = mock.write(other, own)
    assert other_result.effect_id != result.effect_id
    assert mock.balance(other)["spent"] == mock.balance(tenant)["spent"] == 8


def test_missing_objects_fail_explicitly(world):
    mock, tenant, _ = world
    for operation in (
        lambda: mock.job(tenant, "missing"),
        lambda: mock.client_history(tenant, "missing"),
        lambda: mock.proposal(tenant, "missing"),
    ):
        with pytest.raises(ValueError, match="not found"):
            operation()
    with pytest.raises(PermissionError, match="Unknown marketplace tenant"):
        mock.balance("unknown-tenant")


def test_new_unseeded_tenant_has_zero_balance_without_fake_history(world):
    mock, _, _ = world
    with transaction() as db:
        tenant = uid()
        db.add(
            User(
                id=tenant,
                email="unseeded@example.test",
                password_hash="unused-test-hash",
                profile={},
            )
        )
    assert mock.balance(tenant)["balance"] == 0
    assert mock.search(tenant) == []
    assert mock.events(tenant) == []
