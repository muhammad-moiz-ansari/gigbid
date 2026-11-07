def rank(candidates):
    boosts = {"won": 1.15, "replied": 1.07, "ignored": 0.95, "unknown": 1.0}
    return sorted([(item, score * boosts.get(item["outcome"], 1.0)) for item, score in candidates],
                  key=lambda pair: pair[1], reverse=True)
