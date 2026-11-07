from agent.memory.promotion_rules import outcome_candidate, style_candidates
from agent.memory.store import delete_memory, list_memory, load_store, promote
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
    edits = [{"run_id": str(i), "before": "passionate about APIs", "after": "APIs"} for i in range(5)]
    assert not style_candidates(edits[:4])
    candidate = style_candidates(edits)[0]
    assert candidate["word"] == "passionate"
    promote(account["id"], candidate)
    memory = list_memory(account["id"])
    assert len(memory) == 1
    delete_memory(account["id"], memory[0]["id"])
    promote(account["id"], candidate)
    assert load_store(account["id"]).search((account["id"], "style")) == []
    assert not outcome_candidate([{"event_id": "one", "category": "api", "status": "hired"}] * 3)
