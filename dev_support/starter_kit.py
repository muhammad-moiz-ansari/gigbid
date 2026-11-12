"""Import the instructor's illustrative v0.1 samples into the local mock."""

import json

from apps.api.config import ROOT, settings
from dev_support.mock_marketplace.seed import seed_marketplace
from rag.ingest.loaders import ingest_text


def _read(name: str) -> list[dict]:
    return json.loads((ROOT / "data" / "sample" / name).read_text(encoding="utf-8"))


def seed(tenant: str):
    if settings().marketplace_mode != "mock":
        raise ValueError("Starter kit seeding requires mock marketplace mode")
    jobs = []
    clients = []
    for item in _read("jobs.json"):
        if item["budget"]["currency"] != "USD":
            raise ValueError("Starter kit sample budgets must be in USD")
        # The v0.1 jobs have no client IDs. Do not attribute the sample history to them.
        client_id = f'{item["job_id"]}-unknown-client'
        clients.append({
            "id": client_id, "verified": False, "spend": 0, "hires": 0, "synthetic": True,
        })
        jobs.append({
            "id": item["job_id"],
            "title": item["title"],
            "description": item["description"],
            "skills": item["required_skills"],
            "budget": item["budget"]["max"],
            "connects": item["connects_cost"],
            "client_id": client_id,
            "screening_questions": item["screening_questions"],
            "timeline": f'{item["duration_days"]} days',
        })
    seed_marketplace(tenant, jobs=jobs, clients=clients)
    for item in _read("portfolio_items.json"):
        ingest_text(tenant, item["summary"], {
            "source": f'starter-kit-v0.1:{item["evidence_id"]}',
            "persona": item["freelancer_id"],
            "project": item["title"],
            "type": item["type"],
            "skills": item["skills"],
            "synthetic": True,
        })
