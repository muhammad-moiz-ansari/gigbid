from sqlalchemy import select

from apps.api.db import Record, transaction
from rag.variants import v0_naive, v1_decomposition, v2_hybrid, v3_rerank, v4_outcome, v8_corrective


def retrieve(tenant, requirement, k=5, filters=None, variant=None):
    from agent.model import config
    cfg = config()["retrieval"]
    filters = dict(filters or {})
    if set(filters) - {"persona", "type", "project", "industry", "outcome"}:
        raise ValueError("Unsupported evidence filter")
    with transaction() as db:
        items = [r.value for r in db.scalars(select(Record).where(Record.tenant == tenant,
                                                                 Record.kind == "evidence"))
                 if all(r.value.get(key) == value for key, value in filters.items())]
    from apps.api.config import settings
    chosen = variant or settings().retrieval_variant or cfg["variant"]
    def dense(q):
        return v0_naive.rank(q, items, tenant, cfg["embedding_model"])

    def hybrid(q):
        return v2_hybrid.fuse(v2_hybrid.lexical(q, items), dense(q))
    if chosen == "BM25":  # Explicit lexical diagnostic, not the mandatory V0 baseline.
        ranking = v2_hybrid.lexical(requirement, items)
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
    elif chosen == "V8":
        ranking = v8_corrective.retrieve(requirement, lambda q: v2_hybrid.lexical(q, items))
    else:
        raise ValueError("Unknown retrieval variant")
    return [{**item, "retrieval_score": score, "retrieval_variant": chosen} for item, score in ranking[:k]]
