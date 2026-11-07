import math

import httpx

from apps.api.config import settings
from apps.api.db import digest, get_record, put_record, transaction


def embed(texts: list[str], model: str) -> list[list[float]]:
    with httpx.Client(timeout=settings().model_timeout_seconds) as client:
        response = client.post(f"{settings().ollama_url}/api/embed",
                               json={"model": model, "input": texts, "truncate": False})
        response.raise_for_status()
        return response.json()["embeddings"]


def vectors(tenant, evidence, model):
    result = []
    for item in evidence:
        key = digest({"id": item["id"], "hash": item["content_hash"], "model": model})
        with transaction() as db:
            cached = get_record(db, tenant, "embedding", key)
        if cached:
            result.append(cached.value["vector"])
        else:
            vector = embed([item["text"]], model)[0]
            with transaction() as db:
                put_record(db, tenant, "embedding", key, {"vector": vector, "model": model})
            result.append(vector)
    return result


def cosine(a, b):
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0
