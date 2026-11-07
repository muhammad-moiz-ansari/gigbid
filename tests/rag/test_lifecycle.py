from concurrent.futures import ThreadPoolExecutor

import pytest

from agent.handoffs import Action, WriteRequest
from apps.api.approvals import stage_approval
from apps.api.db import Approval, Run, get_record, transaction, uid
from rag.index.corpus import status
from rag.ingest.loaders import delete_source, ingest_text, rechunk
from rag.retriever import retrieve


def test_unchanged_upload_and_filename_alias_have_one_evidence_item(tenant):
    original = ingest_text(
        tenant, "Python API implementation", {"source": "first.md", "skills": ["Python"]}
    )
    before = status(tenant)["corpus"]["revision"]
    assert (
        ingest_text(
            tenant, "Python API implementation", {"source": "first.md", "skills": ["Python"]}
        )
        == original
    )
    alias = ingest_text(
        tenant, "Python API implementation", {"source": "copy.md", "skills": ["Python"]}
    )
    assert alias[0]["id"] == original[0]["id"]
    assert status(tenant)["corpus"]["revision"] == before
    assert len(retrieve(tenant, "Python", variant="BM25")) == 1
    delete_source(tenant, "first.md")
    remaining = retrieve(tenant, "Python", variant="BM25")
    assert remaining[0]["source"] == "copy.md" and remaining[0]["id"] == original[0]["id"]
    delete_source(tenant, "copy.md")
    assert retrieve(tenant, "Python", variant="BM25") == []
    # Normalized no-op uploads retain the latest raw-byte provenance, including
    # when a later explicit re-chunk uses the saved extracted document.
    import hashlib

    ingest_text(tenant, "Python\nAPI", {"source": "crlf.md"})
    latest = "Python\r\nAPI"
    ingest_text(tenant, latest, {"source": "crlf.md"})
    rechunk(tenant)
    assert status(tenant)["sources"][0]["raw_hash"] == hashlib.sha256(latest.encode()).hexdigest()


def test_replacement_and_deletion_remove_old_terms_and_original_text(tenant):
    old = ingest_text(tenant, "Rust compiler tooling", {"source": "project.md"})
    new = ingest_text(tenant, "SQL reporting models", {"source": "project.md"})
    assert new[0]["id"] != old[0]["id"]
    assert retrieve(tenant, "Rust", variant="BM25") == []
    assert len(retrieve(tenant, "SQL", variant="BM25")) == 1
    with pytest.raises(ValueError):
        ingest_text(tenant, "  ", {"source": "project.md"})
    assert len(retrieve(tenant, "SQL", variant="BM25")) == 1
    delete_source(tenant, "project.md")
    with transaction() as db:
        assert get_record(db, tenant, "source_document", "project.md") is None


def test_concurrent_duplicate_uploads_are_idempotent(tenant):
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(
            pool.map(
                lambda _: ingest_text(tenant, "Python API design", {"source": "same.md"}), range(6)
            )
        )
    assert all(items == outcomes[0] for items in outcomes)
    assert status(tenant)["corpus"]["chunks"] == 1
    assert len(retrieve(tenant, "Python", variant="BM25")) == 1


def test_deletion_invalidates_only_approvals_citing_affected_evidence(tenant):
    first = ingest_text(tenant, "Python API", {"source": "api.md"})[0]
    second = ingest_text(tenant, "SQL reports", {"source": "sql.md"})[0]
    ids = []
    with transaction() as db:
        for item in (first, second):
            run = Run(id=uid(), tenant=tenant, subject=uid(), status="awaiting_approval")
            db.add(run)
            db.flush()
            action = Action(
                kind="proposal",
                destination="mock-api",
                text="test",
                evidence_hashes={item["id"]: item["content_hash"]},
            )
            req = WriteRequest(action=action, run_id=run.id, idempotency_key=uid())
            preview = {
                "mode": "mock",
                "dry_run": True,
                "payload": req.action.model_dump(),
                "connects_cost": 8,
                "status": "preview",
            }
            approval = stage_approval(db, tenant, run.id, preview)
            ids.append(approval.id)
    delete_source(tenant, "api.md")
    with transaction() as db:
        assert db.get(Approval, ids[0]).decision == "invalidated"
        assert db.get(Approval, ids[1]).decision == "pending"


def test_configured_chunking_rechunk_and_token_cache_repair(tenant, monkeypatch):
    from agent.model import config
    from rag.index.corpus import records

    cfg = config()["retrieval"]
    monkeypatch.setitem(cfg, "chunk_chars", 60)
    monkeypatch.setitem(cfg, "overlap_chars", 10)
    items = ingest_text(tenant, "Python " * 30, {"source": "long.md"})
    assert len(items) > 1 and all(len(i["text"]) <= 60 for i in items)
    assert status(tenant)["sources"][0]["chunk_version"] == "fixed-chars-v2:60:10"
    revision = status(tenant)["corpus"]["revision"]
    with transaction() as db:
        for row in records(db, tenant, "lexical_chunk"):
            db.delete(row)
    assert retrieve(tenant, "Python", variant="BM25")
    assert status(tenant)["corpus"]["revision"] == revision
    monkeypatch.setitem(cfg, "chunk_chars", 100)
    assert rechunk(tenant) == 1
    assert status(tenant)["sources"][0]["chunk_version"] == "fixed-chars-v2:100:10"


def test_metadata_filters_and_tenant_boundaries(tenant):
    ingest_text(
        tenant, "Python API", {"source": "api.md", "persona": "full-stack", "industry": "retail"}
    )
    assert retrieve(tenant, "Python", filters={"persona": "ai-ml"}, variant="BM25") == []
    assert retrieve(tenant, "Python", filters={"industry": "retail"}, variant="BM25")
    assert retrieve("other-tenant", "Python", variant="BM25") == []
    with pytest.raises(ValueError, match="filter"):
        retrieve(tenant, "Python", filters={"tenant": "other"}, variant="BM25")
