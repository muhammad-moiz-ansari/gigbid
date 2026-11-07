import json

from apps.api.config import ROOT
from apps.api.db import get_record, put_record, transaction
from rag.ingest.loaders import ingest_text


def seed(tenant: str):
    with transaction() as db:
        for job in json.loads((ROOT / "dev_support/fixtures/jobs.json").read_text()):
            put_record(db, tenant, "job", job["id"], job)
        if not get_record(db, tenant, "account", "connects"):
            put_record(db, tenant, "account", "connects", {"balance": 100, "spent": 0})
        for i in range(1, 4):
            put_record(db, tenant, "client", f"mock-client-{i}", {
                "id": f"mock-client-{i}", "verified": i != 3,
                "spend": 4000 if i != 3 else 0, "hires": 8 if i != 3 else 0,
                "synthetic": True,
            })
    for item in json.loads((ROOT / "dev_support/fixtures/portfolio.json").read_text()):
        text = item.pop("text")
        ingest_text(tenant, text, item)
