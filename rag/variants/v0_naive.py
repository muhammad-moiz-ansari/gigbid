from rag.index.dense import cosine, embed, vectors


def rank(query, items, tenant, model):
    if not items:
        return []
    q = embed([query], model)[0]
    indexed = vectors(tenant, items, model)
    return sorted([(item, cosine(q, vector)) for item, vector in zip(items, indexed, strict=True)],
                  key=lambda pair: pair[1], reverse=True)
