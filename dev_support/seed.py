import json

from apps.api.config import ROOT
from dev_support.mock_marketplace.seed import seed_marketplace
from rag.ingest.loaders import ingest_file, ingest_text


def seed(tenant: str):
    seed_marketplace(tenant)
    for item in json.loads((ROOT / "dev_support/fixtures/portfolio.json").read_text()):
        text = item.pop("text")
        ingest_text(tenant, text, item)
    for filename in ("case_study.md", "reviews.json", "past_proposals.json"):
        ingest_file(tenant, (ROOT / "dev_support/fixtures" / filename).read_bytes(), filename)
