BOOSTS = {"won": 1.15, "replied": 1.07, "ignored": 0.95}


def boosted(item, score):
    """A boost moves an item up whatever the score's sign; BM25 scores turn negative on small corpora."""
    factor = BOOSTS.get(item["outcome"], 1.0)
    return score * factor if score >= 0 else score / factor


def rank(candidates):
    return sorted([(item, boosted(item, score)) for item, score in candidates], key=lambda pair: pair[1], reverse=True)
