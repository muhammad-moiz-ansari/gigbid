import json

from agent.handoffs import JobSpec
from apps.api.config import ROOT
from apps.api.db import get_record, put_record, transaction
from dev_support.mock_marketplace.config import SimulatorConfig
from dev_support.mock_marketplace.service import _lock


def seed_marketplace(tenant: str, *, jobs=None, clients=None):
    """Seed original local data without resetting balances, outcomes or fault state."""
    if jobs is None:
        jobs = json.loads((ROOT / "dev_support/fixtures/jobs.json").read_text())
    if clients is None:
        clients = json.loads((ROOT / "dev_support/fixtures/clients.json").read_text())
    config = SimulatorConfig.model_validate_json(
        (ROOT / "dev_support/fixtures/simulator.json").read_text()
    )
    with transaction() as db:
        _lock(db, tenant)
        for job in jobs:
            validated = JobSpec.model_validate(job).model_dump()
            if not get_record(db, tenant, "job", job["id"]):
                put_record(db, tenant, "job", job["id"], validated)
        for client in clients:
            if not get_record(db, tenant, "client", client["id"]):
                put_record(db, tenant, "client", client["id"], client)
        if not get_record(db, tenant, "account", "connects"):
            put_record(db, tenant, "account", "connects", {"balance": 100, "spent": 0})
        if not get_record(db, tenant, "mock_control", "config"):
            put_record(db, tenant, "mock_control", "config", config.model_dump())
