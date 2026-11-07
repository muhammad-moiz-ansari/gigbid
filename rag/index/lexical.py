from rank_bm25 import BM25Okapi

from apps.api.db import transaction
from rag.index.corpus import changed, lock_tenant, records, tokens


def rank(query, items, tenant):
    if not items or not tokens(query):
        return []
    with transaction() as db:
        lock_tenant(db, tenant)
        changed(
            db, tenant, force=True
        )  # Repairs missing token caches without changing corpus revision.
        indexed = {r.key: r.value["tokens"] for r in records(db, tenant, "lexical_chunk")}
    corpus = [indexed[item["id"]] for item in items if item["id"] in indexed]
    current = [item for item in items if item["id"] in indexed]
    if not current or not any(corpus):
        return []
    scores = BM25Okapi(corpus).get_scores(tokens(query))
    words = set(tokens(query))
    return sorted(
        [
            (item, float(score))
            for item, score, terms in zip(current, scores, corpus, strict=True)
            if words.intersection(terms)
        ],
        key=lambda row: (-row[1], row[0]["id"]),
    )
