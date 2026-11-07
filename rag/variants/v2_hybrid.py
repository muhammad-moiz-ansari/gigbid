import re

from rank_bm25 import BM25Okapi


def tokens(text):
    return re.findall(r"[\w.+#-]+", text.lower())


def lexical(query, items):
    if not items:
        return []
    # BM25Plus-like positive IDF is unnecessary for sorting, but zero-match items
    # must not count as evidence for a requirement.
    corpus = [tokens(item["text"] + " " + " ".join(item["skills"])) for item in items]
    scores = BM25Okapi(corpus).get_scores(tokens(query))
    matched = set(tokens(query))
    return sorted([(item, float(score)) for item, score, words in zip(items, scores, corpus, strict=True)
                   if matched.intersection(words)], key=lambda p: p[1], reverse=True)


def fuse(*rankings, constant=60):
    values = {}
    for ranking in rankings:
        for position, (item, _) in enumerate(ranking, 1):
            prior = values.get(item["id"], (item, 0))
            values[item["id"]] = (item, prior[1] + 1 / (constant + position))
    return sorted(values.values(), key=lambda p: p[1], reverse=True)
