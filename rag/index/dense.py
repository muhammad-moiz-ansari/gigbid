"""Real open-model embeddings and tenant-scoped Qdrant baseline indexing."""

import hashlib
import math
from uuid import NAMESPACE_URL, uuid5

import httpx

from agent.marketplace_port import Unavailable
from apps.api.config import settings
from apps.api.db import digest, get_record, put_record, transaction
from rag.index.corpus import changed, lock_tenant, records, snapshot, snapshot_in


def open_store():
    # Keep BM25-only MCP subprocesses independent of Qdrant/grpc imports. The
    # vector dependency is loaded only when a real vector operation is requested.
    from rag.index.vector_store import open_store as factory

    return factory()


def checked_vectors(values, count, dimension=None):
    if not isinstance(values, list) or len(values) != count:
        raise Unavailable("Embedding service returned the wrong number of vectors")
    result = []
    for vector in values:
        if not isinstance(vector, list) or not vector:
            raise Unavailable("Embedding service returned an empty vector")
        try:
            parsed = [float(x) for x in vector]
        except (TypeError, ValueError) as exc:
            raise Unavailable("Embedding service returned invalid coordinates") from exc
        if any(not math.isfinite(x) for x in parsed) or not sum(x * x for x in parsed):
            raise Unavailable("Embedding service returned non-finite or zero-norm vectors")
        dimension = dimension or len(parsed)
        if len(parsed) != dimension:
            raise Unavailable("Embedding dimensions changed; rebuild with a verified model")
        result.append(parsed)
    return result


class OllamaEmbeddings:
    def __init__(self, model):
        self.model = model

    def identity(self):
        try:
            with httpx.Client(timeout=5) as client:
                result = client.get(f"{settings().ollama_url}/api/tags")
                result.raise_for_status()
                requested = self.model if ":" in self.model else self.model + ":latest"
                match = next(
                    (
                        m
                        for m in result.json()["models"]
                        if m.get("name", m.get("model")) == requested
                    ),
                    None,
                )
                if not match or not match.get("digest"):
                    raise Unavailable(
                        "Configured open embedding model is not installed or has no verified digest"
                    )
                return {
                    "provider": "ollama",
                    "model": requested,
                    "revision": match["digest"],
                    "endpoint_hash": digest(settings().ollama_url),
                    "format": "ollama-embed-v1",
                    "test_double": False,
                }
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise Unavailable(
                "Open embedding service unavailable; initialize Ollama and the configured model"
            ) from exc

    def embed(self, texts):
        try:
            with httpx.Client(timeout=settings().model_timeout_seconds) as client:
                response = client.post(
                    f"{settings().ollama_url}/api/embed",
                    json={"model": self.model, "input": texts, "truncate": False},
                )
                response.raise_for_status()
                return checked_vectors(response.json()["embeddings"], len(texts))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise Unavailable(
                "Open embedding generation failed; no synthetic embeddings were substituted"
            ) from exc


def cosine(a, b):
    norm = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


def _cache_key(item, identity):
    return digest(
        {"evidence_id": item["id"], "content_hash": item["content_hash"], "embedding": identity}
    )


def sync(tenant, model, *, backend=None):
    from qdrant_client import models

    backend = backend or OllamaEmbeddings(model)
    with transaction() as db:
        lock_tenant(db, tenant)
        changed(db, tenant)
        items, fingerprint = snapshot_in(db, tenant)
    if not items:
        return None
    identity = backend.identity()
    profile = digest(identity)
    collection = "gigbid_portfolio_" + profile[:20]
    cached, missing = {}, []
    with transaction() as db:
        for item in items:
            if hashlib.sha256(item["text"].encode()).hexdigest() != item["content_hash"]:
                raise Unavailable("Evidence content hash mismatch; re-upload the source")
            entry = get_record(db, tenant, "embedding", _cache_key(item, identity))
            if entry:
                cached[item["id"]] = entry.value["vector"]
            else:
                missing.append(item)
    for offset in range(0, len(missing), 32):
        batch = missing[offset : offset + 32]
        vectors = checked_vectors(backend.embed([i["text"] for i in batch]), len(batch))
        cached.update({i["id"]: vector for i, vector in zip(batch, vectors, strict=True)})
    vectors = checked_vectors([cached[i["id"]] for i in items], len(items))
    if backend.identity() != identity:
        raise Unavailable(
            "Embedding model revision changed during indexing; retry with a stable model"
        )
    points = [
        models.PointStruct(
            id=str(uuid5(NAMESPACE_URL, f"{tenant}:{profile}:{fingerprint}:{item['id']}")),
            vector=vector,
            payload={
                "tenant": tenant,
                "corpus_fingerprint": fingerprint,
                "evidence_id": item["id"],
                "content_hash": item["content_hash"],
                **{
                    key: item[key]
                    for key in (
                        "persona",
                        "type",
                        "project",
                        "industry",
                        "outcome",
                        "date",
                        "skills",
                    )
                },
            },
        )
        for item, vector in zip(items, vectors, strict=True)
    ]
    with open_store() as store:
        if not store.ready(collection, tenant, fingerprint, len(points)):
            store.publish(collection, len(vectors[0]), points)
    with transaction() as db:
        lock_tenant(db, tenant)
        _, current = snapshot_in(db, tenant)
        if current != fingerprint:
            put_record(
                db,
                tenant,
                "vector_cleanup",
                digest([collection, fingerprint]),
                {"collection": collection, "fingerprint": fingerprint, "status": "pending"},
            )
            stale = True
        else:
            stale = False
            for item, vector in zip(items, vectors, strict=True):
                put_record(
                    db,
                    tenant,
                    "embedding",
                    _cache_key(item, identity),
                    {
                        "evidence_id": item["id"],
                        "content_hash": item["content_hash"],
                        "vector": vector,
                        "embedding": identity,
                    },
                )
            old = get_record(db, tenant, "dense_index", profile)
            if old and old.value["fingerprint"] != fingerprint:
                value = old.value
                put_record(
                    db,
                    tenant,
                    "vector_cleanup",
                    digest([value["collection"], value["fingerprint"]]),
                    {
                        "collection": value["collection"],
                        "fingerprint": value["fingerprint"],
                        "status": "pending",
                    },
                )
            put_record(
                db,
                tenant,
                "dense_index",
                profile,
                {
                    "status": "ready",
                    "collection": collection,
                    "fingerprint": fingerprint,
                    "embedding": identity,
                    "dimension": len(vectors[0]),
                    "distance": "Cosine",
                    "algorithm": "V0-fixed-chunk-dense",
                    "qdrant_client_version": "1.20.0",
                    "points": len(points),
                    "corpus_revision": get_record(db, tenant, "corpus", "portfolio").value[
                        "revision"
                    ],
                    "chunk_versions": sorted(
                        {
                            r.value.get("chunk_version", "legacy-unspecified")
                            for r in records(db, tenant, "source")
                        }
                    ),
                },
            )
    cleanup(tenant)
    if stale:
        raise Unavailable("Portfolio changed while indexing; retry against the current corpus")
    return {
        "fingerprint": fingerprint,
        "identity": identity,
        "collection": collection,
        "dimension": len(vectors[0]),
        "items": items,
        "backend": backend,
    }


def rank(query, items, tenant, model, *, backend=None, limit=20):
    if not items:
        return []
    indexed = sync(tenant, model, backend=backend)
    if indexed is None:
        return []
    vector = checked_vectors(indexed["backend"].embed([query]), 1, indexed["dimension"])[0]
    if indexed["backend"].identity() != indexed["identity"]:
        raise Unavailable("Embedding model revision changed during retrieval; retry")
    with open_store() as store:
        hits = store.search(
            indexed["collection"],
            tenant,
            indexed["fingerprint"],
            vector,
            [i["id"] for i in items],
            min(limit, len(items)),
        )
    current, fingerprint = snapshot(tenant)
    if fingerprint != indexed["fingerprint"]:
        raise Unavailable("Portfolio changed during retrieval; retry against the current corpus")
    by_id = {item["id"]: item for item in current}
    return [
        (by_id[hit.payload["evidence_id"]], float(hit.score))
        for hit in hits
        if hit.payload["tenant"] == tenant
        and hit.payload["evidence_id"] in by_id
        and hit.payload["content_hash"] == by_id[hit.payload["evidence_id"]]["content_hash"]
    ]


def cleanup(tenant):
    with transaction() as db:
        tasks = [(r.key, r.value) for r in records(db, tenant, "vector_cleanup")]
    if not tasks:
        return
    for key, task in tasks:
        try:
            with transaction() as db:
                lock_tenant(db, tenant)
                _, fingerprint = snapshot_in(db, tenant)
                if fingerprint != task["fingerprint"]:
                    with open_store() as store:
                        store.purge(task["collection"], tenant, task["fingerprint"])
                row = get_record(db, tenant, "vector_cleanup", key)
                if row:
                    db.delete(row)
        except Unavailable:
            # Canonical SQL evidence and generation filters already prevent stale
            # retrieval. Physical cleanup remains durable and explicitly pending.
            return
