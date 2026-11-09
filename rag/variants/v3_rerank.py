import os
import sys
from functools import lru_cache
from pathlib import Path

SCORES = {}  # (model, query, content hash) -> score, so pipelines sharing a query skip repeated scoring


@lru_cache(maxsize=2)
def scorer(model):
    """Optional CPU open cross-encoder, loaded once per process."""
    os.environ.setdefault("HF_HOME", str(Path(sys.prefix) / "huggingface"))  # weights stay in the virtual env
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError("Install the rerank extra and download configured open weights") from exc
    return CrossEncoder(model, device="cpu", trust_remote_code=False)


def rank(query, candidates, model):
    """No fake scores if the weights are absent."""
    missing = [item for item, _ in candidates if (model, query, item["content_hash"]) not in SCORES]
    if missing:
        if len(SCORES) > 50_000:
            SCORES.clear()
        values = scorer(model).predict([(query, item["text"]) for item in missing])
        SCORES.update({(model, query, item["content_hash"]): float(v) for item, v in zip(missing, values, strict=True)})
    return sorted([(item, SCORES[(model, query, item["content_hash"])]) for item, _ in candidates],
                  key=lambda pair: pair[1], reverse=True)
