def rank(query, candidates, model):
    """Optional CPU open cross-encoder; no fake scores if its weights are absent."""
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError("Install the rerank extra and download configured open weights") from exc
    scorer = CrossEncoder(model, device="cpu", trust_remote_code=False)
    scores = scorer.predict([(query, item["text"]) for item, _ in candidates])
    return sorted([(item, float(score)) for (item, _), score in zip(candidates, scores, strict=True)],
                  key=lambda pair: pair[1], reverse=True)
