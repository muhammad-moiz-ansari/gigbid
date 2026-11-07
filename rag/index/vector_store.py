from contextlib import contextmanager
from pathlib import Path
from threading import RLock

import portalocker
from qdrant_client import QdrantClient, models

from agent.marketplace_port import Unavailable
from apps.api.config import ROOT, settings


def scope(tenant, fingerprint, ids=None):
    conditions = [
        models.FieldCondition(key="tenant", match=models.MatchValue(value=tenant)),
        models.FieldCondition(key="corpus_fingerprint", match=models.MatchValue(value=fingerprint)),
    ]
    if ids is not None:
        conditions.append(
            models.FieldCondition(key="evidence_id", match=models.MatchAny(any=list(ids)))
        )
    return models.Filter(must=conditions)


class VectorIndex:
    def __init__(self, client):
        self.client, self.lock = client, RLock()

    def publish(self, collection, dimension, points):
        with self.lock:
            if not self.client.collection_exists(collection):
                try:
                    self.client.create_collection(
                        collection,
                        vectors_config=models.VectorParams(
                            size=dimension, distance=models.Distance.COSINE
                        ),
                    )
                except Exception:
                    if not self.client.collection_exists(collection):
                        raise
            for start in range(0, len(points), 256):
                self.client.upsert(collection, points=points[start : start + 256], wait=True)

    def ready(self, collection, tenant, fingerprint, count):
        with self.lock:
            return (
                self.client.collection_exists(collection)
                and self.client.count(
                    collection, count_filter=scope(tenant, fingerprint), exact=True
                ).count
                == count
            )

    def search(self, collection, tenant, fingerprint, vector, ids, limit):
        if not ids:
            return []
        with self.lock:
            return self.client.query_points(
                collection,
                query=vector,
                query_filter=scope(tenant, fingerprint, ids),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            ).points

    def purge(self, collection, tenant, fingerprint):
        with self.lock:
            if self.client.collection_exists(collection):
                self.client.delete(
                    collection,
                    points_selector=models.FilterSelector(filter=scope(tenant, fingerprint)),
                    wait=True,
                )


@contextmanager
def open_store():
    cfg = settings()
    client = None
    try:
        if cfg.qdrant_mode == "server":
            client = QdrantClient(url=cfg.qdrant_url, timeout=5)
            yield VectorIndex(client)
        else:
            path = Path(cfg.qdrant_path)
            if not path.is_absolute():
                path = ROOT / path
            path.mkdir(parents=True, exist_ok=True)
            # Local Qdrant holds a file lock while open. Serialize separate stdio
            # processes around short operations and close it after each operation.
            with portalocker.Lock(str(path / "portfolio-operation.lock"), timeout=10):
                client = QdrantClient(path=str(path), force_disable_check_same_thread=True)
                try:
                    yield VectorIndex(client)
                finally:
                    client.close()
                    client = None
    except Unavailable:
        raise
    except Exception as exc:
        raise Unavailable(
            "Vector store unavailable; portfolio text is retained and BM25 remains available"
        ) from exc
    finally:
        if client is not None:
            client.close()
