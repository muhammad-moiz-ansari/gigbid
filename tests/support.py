"""Deterministic doubles for tests only; never imported by production code."""
import asyncio

from agent.marketplace_port import NotFound
from agent.mcp_client import ALLOWLISTS, ToolFailure
from apps.api.db import get_record, transaction
from dev_support.mock_marketplace.service import MockMarketplace
from rag.retriever import retrieve


class TestModels:
    __test__ = False

    async def complete(self, node, data, schema):
        await asyncio.sleep(0.005)
        if node == "analyst":
            value = data
        elif node == "risk":
            value = {"score": 0.1, "flags": [], "reasons": ["Synthetic test double"]}
        elif node == "pricing":
            value = {"amount": 500, "connects": data["job"]["connects"], "rationale": "Test fixture price"}
        elif node in ("writer", "liaison"):
            evidence = data["evidence"]
            claim = f'{" ".join(evidence[0]["text"].split())} [{evidence[0]["id"]}]' if evidence else ""
            questions = (data.get("job") or {}).get("screening_questions", [])
            value = {"text": claim + "\n\nProposed approach: I would begin with a small scope and test each requirement.",
                     "version": data.get("version", 1), "evidence_ids": [e["id"] for e in evidence],
                     "screening_answers": {q: "I would test each requirement." for q in questions}}
        elif node == "answer":
            value = {"answer": "I would test each requirement."}
        elif node == "intent":
            text = data["message"].lower()
            intent = "interview" if any(w in text for w in ("interview", "schedule", "available")) else \
                "negotiation" if any(w in text for w in ("price", "budget", "rate")) else "question"
            value = {"intent": intent, "reasons": ["Synthetic keyword test double"]}
        elif node == "critic":
            value = {"passed": True, "comments": []}
        else:
            value = {"passed": True, "reasons": []}
        return schema.model_validate(value).model_dump(), {
            "node": node, "tokens": 10, "api_usd": None, "test_double": True,
            "model": "deterministic-test-only", "latency_seconds": 0.005}


class TestTools:
    __test__ = False

    def __init__(self, tenant):
        self.tenant = tenant
        self.calls = []

    async def call(self, role, name, args):
        assert name in ALLOWLISTS[role]
        self.calls.append((role, name, args))
        mock = MockMarketplace()
        if name == "get_job":
            try:
                return mock.job(self.tenant, args["job_id"]).model_dump()
            except NotFound:
                raise ToolFailure("not_found", message="Job not found") from None
        if name == "get_client_history":
            return mock.client_history(self.tenant, args["client_id"])
        if name == "get_connects_balance":
            return mock.balance(self.tenant)
        if name == "search_evidence":
            return retrieve(self.tenant, args["requirement"], args.get("k", 5), variant="BM25")
        if name == "get_case_study":
            with transaction() as db:
                record = get_record(db, self.tenant, "evidence", args["id"])
                if not record:
                    raise ValueError("Evidence not found")
                return record.value
        if name in ("submit_proposal", "send_message"):
            from agent.handoffs import WriteRequest
            return mock.write(self.tenant, WriteRequest.model_validate(args["request"])).model_dump()
        if name == "reconcile_write":
            result = mock.reconcile(self.tenant, args["idempotency_key"])
            return result.model_dump() if result else None
        if name == "list_events":
            return mock.events(self.tenant, args["after"])
        if name == "list_messages":
            return mock.messages(self.tenant, args["conversation"])
        if name == "free_slots":
            return [{"start": "2026-11-10T10:00:00Z", "minutes": 30, "synthetic": True}]
        raise AssertionError(name)
