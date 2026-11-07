from contextlib import contextmanager

import pytest
from qdrant_client import models

from agent.marketplace_port import Unavailable
from apps.api.db import User, transaction, uid
from rag.index import dense
from rag.index.corpus import status
from rag.ingest.loaders import delete_source, ingest_text
from rag.retriever import retrieve


def test_v0_uses_real_qdrant_engine_and_versioned_model_cache(tenant, vector_index, embeddings):
    python = ingest_text(
        tenant, "Python API engineering", {"source": "python.md", "skills": ["Python"]}
    )[0]
    ingest_text(tenant, "Rust compiler tooling", {"source": "rust.md", "skills": ["Rust"]})
    first = retrieve(tenant, "Python API", variant="V0", k=1)
    assert first[0]["id"] == python["id"] and first[0]["retrieval_variant"] == "V0"
    calls = len(embeddings.calls)
    retrieve(tenant, "Python API", variant="V0")
    assert len(embeddings.calls) == calls + 1  # Only query embedding; document vectors reused.
    manifest = status(tenant)["dense"][0]
    assert manifest["status"] == "ready" and manifest["points"] == 2
    assert manifest["embedding"]["test_double"] is True
    assert manifest["distance"] == "Cosine" and manifest["dimension"] == 3
    embeddings.revision = "test-fixture-v2"
    retrieve(tenant, "Python API", variant="V0")
    assert len(status(tenant)["dense"]) == 2
    assert len(vector_index.client.get_collections().collections) == 2


def test_new_source_only_embeds_new_document_and_deletion_removes_points(
    tenant, vector_index, embeddings
):
    first = ingest_text(tenant, "Python API", {"source": "one.md"})[0]
    retrieve(tenant, "Python", variant="V0")
    collection = status(tenant)["dense"][0]["collection"]
    ingest_text(tenant, "SQL reporting", {"source": "two.md"})
    embeddings.calls.clear()
    retrieve(tenant, "SQL", variant="V0")
    assert embeddings.calls == [["SQL reporting"], ["SQL"]]
    delete_source(tenant, "one.md")
    assert status(tenant)["vector_cleanup_pending"] == 0
    hits = retrieve(tenant, "Python", variant="V0")
    assert all(h["id"] != first["id"] for h in hits)
    assert vector_index.client.count(collection, exact=True).count == 1
    delete_source(tenant, "two.md")
    assert retrieve(tenant, "SQL", variant="V0") == []
    assert vector_index.client.count(collection, exact=True).count == 0


def test_vector_and_lexical_filters_never_cross_tenants(tenant, vector_index, embeddings):
    own = ingest_text(tenant, "Python API", {"source": "own.md", "persona": "full-stack"})[0]
    with transaction() as db:
        other = uid()
        db.add(
            User(
                id=other,
                email="dense-other@example.test",
                password_hash="unused-test-hash",
                profile={},
            )
        )
    secret = ingest_text(other, "Rust secret project", {"source": "other.md", "persona": "ai-ml"})[
        0
    ]
    retrieve(other, "Rust", variant="V0")
    hits = retrieve(tenant, "Rust", variant="V0")
    assert {h["id"] for h in hits} == {own["id"]}
    assert secret["text"] not in str(hits)
    assert retrieve(tenant, "Rust", variant="BM25") == []
    assert retrieve(tenant, "Python", filters={"persona": "ai-ml"}, variant="V0") == []
    # A foreign vector carrying an otherwise allowed ID still cannot pass the
    # mandatory tenant predicate in Qdrant.
    manifest = status(tenant)["dense"][0]
    vector_index.client.upsert(
        manifest["collection"],
        points=[
            models.PointStruct(
                id=uid(),
                vector=[0, 1, 0],
                payload={
                    "tenant": other,
                    "corpus_fingerprint": manifest["fingerprint"],
                    "evidence_id": own["id"],
                    "content_hash": own["content_hash"],
                },
            )
        ],
    )
    assert len(retrieve(tenant, "Rust", variant="V0")) == 1


def test_deletion_during_embedding_cannot_recreate_evidence_or_cache(
    tenant, vector_index, embeddings, monkeypatch
):
    ingest_text(tenant, "Python API", {"source": "race.md"})
    original = embeddings.embed
    triggered = False

    def racing(texts):
        nonlocal triggered
        if not triggered:
            triggered = True
            delete_source(tenant, "race.md")
        return original(texts)

    monkeypatch.setattr(embeddings, "embed", racing)
    with pytest.raises(Unavailable, match="changed while indexing"):
        retrieve(tenant, "Python", variant="V0")
    assert retrieve(tenant, "Python", variant="V0") == []
    from rag.index.corpus import records

    with transaction() as db:
        assert not records(db, tenant, "embedding")
    assert all(
        vector_index.client.count(c.name, exact=True).count == 0
        for c in vector_index.client.get_collections().collections
    )


def test_unavailable_physical_cleanup_is_durable_but_deleted_evidence_stays_hidden(
    tenant, vector_index, embeddings, monkeypatch
):
    ingest_text(tenant, "Python API", {"source": "remove.md"})
    retrieve(tenant, "Python", variant="V0")
    factory = dense.open_store

    @contextmanager
    def outage():
        raise Unavailable("Synthetic vector store outage")
        yield  # pragma: no cover

    monkeypatch.setattr(dense, "open_store", outage)
    delete_source(tenant, "remove.md")
    assert status(tenant)["vector_cleanup_pending"] == 1
    assert retrieve(tenant, "Python", variant="V0") == []
    assert retrieve(tenant, "Python", variant="BM25") == []
    monkeypatch.setattr(dense, "open_store", factory)
    dense.cleanup(tenant)
    assert status(tenant)["vector_cleanup_pending"] == 0


def test_unchanged_chunks_keep_identity_and_embeddings_after_append(
    tenant, vector_index, embeddings, monkeypatch
):
    from agent.model import config

    monkeypatch.setitem(config()["retrieval"], "chunk_chars", 60)
    monkeypatch.setitem(config()["retrieval"], "overlap_chars", 10)
    text = "Python " + "x" * 53
    before = ingest_text(tenant, text, {"source": "append.md"})
    retrieve(tenant, "Python", variant="V0")
    after = ingest_text(tenant, text + " SQL reporting", {"source": "append.md"})
    assert before[0]["id"] == after[0]["id"]
    embeddings.calls.clear()
    retrieve(tenant, "Python", variant="V0")
    assert text not in [t for batch in embeddings.calls for t in batch]


@pytest.mark.parametrize(
    "vectors,count",
    [
        ([], 1),
        ([[0, 0]], 1),
        ([[float("nan"), 1]], 1),
        ([[1, 0], [1, 0, 0]], 2),
        ([[float("inf"), 0]], 1),
    ],
)
def test_invalid_embedding_responses_are_never_published(vectors, count):
    with pytest.raises(Unavailable):
        dense.checked_vectors(vectors, count)
