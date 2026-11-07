from rag.index.dense import rank as dense_rank


def rank(query, items, tenant, model):
    return dense_rank(query, items, tenant, model)
