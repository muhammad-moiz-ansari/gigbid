from agent.marketplace_port import Unavailable
from apps.api.config import settings
from rag.index import lexical
from rag.index.corpus import snapshot
from rag.variants import v0_naive, v1_decomposition, v2_hybrid, v3_rerank, v4_outcome, v8_corrective

FILTERS = {"persona", "type", "project", "industry", "outcome"}


def retrieve(tenant, requirement, k=5, filters=None, variant=None):
    from agent.model import config

    if not isinstance(requirement, str) or not requirement.strip() or len(requirement) > 4000:
        raise ValueError("Retrieval query must contain 1 to 4000 characters")
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 20:
        raise ValueError("Retrieval k must be from 1 to 20")
    filters = dict(filters or {})
    if set(filters) - FILTERS:
        raise ValueError("Unsupported evidence filter")
    cfg = config()["retrieval"]
    chosen = variant or settings().retrieval_variant or cfg["variant"]
    if chosen not in {"BM25", "V0", "V1", "V2", "V3", "V4", "V8"}:
        raise ValueError("Unknown retrieval variant")
    # A final canonical snapshot check prevents stale cache or vector payloads
    # from returning removed evidence during concurrent source replacement.
    for _ in range(2):
        corpus, fingerprint = snapshot(tenant)
        items = [
            item for item in corpus if all(item.get(key) == value for key, value in filters.items())
        ]
        if not items:
            return []

        def dense(q):
            return v0_naive.rank(q, items, tenant, cfg["embedding_model"])

        def bm25(q):
            return lexical.rank(q, items, tenant)

        def hybrid(q):
            return v2_hybrid.fuse(bm25(q), dense(q))

        if chosen == "BM25":
            ranking = bm25(requirement)
        elif chosen == "V0":
            ranking = dense(requirement)
        elif chosen == "V1":
            ranking = v1_decomposition.rank(requirement, dense)
        elif chosen == "V2":
            ranking = hybrid(requirement)
        elif chosen == "V3":
            ranking = v3_rerank.rank(requirement, hybrid(requirement)[:20], cfg["reranker"])
        elif chosen == "V4":
            ranking = v4_outcome.rank(hybrid(requirement))
        else:
            ranking = v8_corrective.retrieve(requirement, bm25)
        _, current = snapshot(tenant)
        if current == fingerprint:
            return [
                {**item, "retrieval_score": score, "retrieval_variant": chosen}
                for item, score in ranking[:k]
            ]
    raise Unavailable("Portfolio changed during retrieval; retry against current evidence")
