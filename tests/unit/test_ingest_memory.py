from agent.memory.promotion_rules import outcome_candidate, style_candidates
from agent.memory.store import delete_memory, list_memory, promote
from rag.ingest.loaders import delete_source, ingest_text
from rag.retriever import retrieve


def test_incremental_deletion_and_tenant_filter(account):
    tenant = account["id"]
    meta = {"source": "own.md", "skills": ["Rust"]}
    a = ingest_text(tenant, "Rust systems programming", meta)
    b = ingest_text(tenant, "Rust systems programming", meta)
    assert a == b
    assert retrieve("other-tenant", "Rust", variant="BM25") == []
    assert len(retrieve(tenant, "Rust", variant="BM25")) == 1
    ingest_text(tenant, "Rust systems with testing", meta)
    assert len(retrieve(tenant, "Rust", variant="BM25")) == 1
    delete_source(tenant, "own.md")
    assert retrieve(tenant, "Rust", variant="BM25") == []


def test_memory_rules_and_tombstone(account):
    tenant = account["id"]
    edits = [{"run_id": str(i), "before": "passionate about APIs", "after": "APIs"} for i in range(5)]
    assert not style_candidates(edits[:4])
    assert not style_candidates([{"run_id": str(i), "paragraph": 1} for i in range(5)])
    candidate = style_candidates(edits)[0]
    assert candidate["word"] == "passionate"
    assert promote(tenant, "style", "style:passionate", candidate)
    assert [m["id"] for m in list_memory(tenant)] == ["style:passionate"]
    delete_memory(tenant, "style:passionate")
    assert not promote(tenant, "style", "style:passionate", candidate)
    assert list_memory(tenant) == []
    assert not outcome_candidate([{"event_id": "one", "category": "api", "status": "hired"}] * 3)
