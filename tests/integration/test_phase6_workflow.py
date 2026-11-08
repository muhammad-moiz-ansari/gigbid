import pytest
from sqlalchemy import select

from apps.api.db import Event, transaction
from tests.support import TestModels, TestTools
from worker.runtime import process_run


def test_onboarding_rates_filters_and_marketplace_validation(client, account):
    values = {"name": "Phase six", "persona": "data-analyst", "floor_fixed": 80, "hourly_rate": 65,
              "min_budget": 200, "max_connects": 9, "required_skills": ["Python"],
              "marketplace_mode": "mock", "weekly_connects": 24}
    result = client.put("/auth/profile", json=values)
    assert result.status_code == 200
    assert all(client.get("/auth/me").json()["profile"][key] == value for key, value in values.items())
    assert client.put("/auth/profile", json={**values, "marketplace_mode": "upwork"}).status_code == 409
    assert client.put("/auth/profile", json={**values, "max_connects": -1}).status_code == 422


@pytest.mark.asyncio
async def test_multiline_paragraph_regeneration_rechecks_and_preserves_other_text(client, account):
    tenant = account["id"]
    class Models(TestModels):
        async def complete(self, node, data, schema):
            result, usage = await super().complete(node, data, schema)
            if node == "writer" and "regenerate_paragraph" in data:
                result["text"] = "Proposed approach: I would test authorization."
            return result, usage
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    await process_run(run_id, TestTools(tenant), Models())
    before = client.get(f"/runs/{run_id}").json()
    approval_id = before["state"]["approval_id"]
    assert len(before["draft_paragraphs"]) == 2
    assert client.post(f"/approvals/{approval_id}/decision",
                       json={"decision": "regenerate", "paragraph": 99}).status_code == 422
    assert client.post(f"/approvals/{approval_id}/decision",
                       json={"decision": "regenerate", "paragraph": 1}).status_code == 200
    await process_run(run_id, TestTools(tenant), Models())
    after = client.get(f"/runs/{run_id}").json()
    assert after["status"] == "awaiting_approval" and after["state"]["draft"]["version"] == 2
    assert after["draft_paragraphs"][0] == before["draft_paragraphs"][0]
    assert after["draft_paragraphs"][1] == "Proposed approach: I would test authorization."
    assert after["state"]["approval_id"] != approval_id
    assert after["approval_status"] == "pending"
    with transaction() as db:
        events = list(db.scalars(select(Event).where(Event.run_id == run_id)))
        for name in ("verifier", "critic", "compliance"):
            assert sum(event.name == f"node:{name}" for event in events) == 2
        assert any(event.name == "node:started" and event.payload["node"] == "regenerate" for event in events)
    source = after["state"]["fit"]["evidence"][0]["source"]
    assert client.delete(f"/evidence/source/{source}").status_code == 200
    assert client.get(f"/runs/{run_id}").json()["approval_status"] == "invalidated"
