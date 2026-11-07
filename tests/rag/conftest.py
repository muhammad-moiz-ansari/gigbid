from contextlib import contextmanager

import pytest
from qdrant_client import QdrantClient

from apps.api.db import User, transaction, uid
from rag.index import dense
from rag.index.vector_store import VectorIndex


class TestEmbeddings:
    """Fixed test vectors, never offered as real semantic embeddings."""

    __test__ = False

    def __init__(self):
        self.revision = "test-fixture-v1"
        self.calls = []

    def identity(self):
        return {
            "provider": "test-only",
            "model": "fixed-three-axis-vectors",
            "revision": self.revision,
            "test_double": True,
        }

    def embed(self, texts):
        self.calls.append(list(texts))
        return [
            [0.0, 1.0, 0.0]
            if "rust" in text.lower()
            else [0.0, 0.0, 1.0]
            if "sql" in text.lower()
            else [1.0, 0.0, 0.0]
            for text in texts
        ]


@pytest.fixture
def tenant():
    with transaction() as db:
        identity = uid()
        db.add(
            User(
                id=identity,
                email=f"{identity}@example.test",
                password_hash="unused-test-hash",
                profile={},
            )
        )
    return identity


@pytest.fixture
def vector_index(monkeypatch):
    client = QdrantClient(":memory:")
    store = VectorIndex(client)

    @contextmanager
    def factory():
        yield store

    monkeypatch.setattr(dense, "open_store", factory)
    yield store
    client.close()


@pytest.fixture
def embeddings(monkeypatch):
    backend = TestEmbeddings()
    monkeypatch.setattr(dense, "OllamaEmbeddings", lambda model: backend)
    return backend
