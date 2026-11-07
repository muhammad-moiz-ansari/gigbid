import asyncio
import json
import time
from contextvars import ContextVar
from functools import lru_cache

import httpx
import yaml

from apps.api.config import ROOT, settings

usage_sink = ContextVar("model_usage_sink", default=None)


@lru_cache
def _config(content):
    return yaml.safe_load(content)


def config():
    # Content-keyed cache notices policy/budget edits in an already running worker.
    return _config((ROOT / "agent/config.yaml").read_text(encoding="utf-8"))


def prompt(node):
    version = config().get("prompts", {}).get(node, "v1")
    return (ROOT / "agent/prompts" / f"{node}.{version}.md").read_text(encoding="utf-8")


class OpenModel:
    """Real Ollama structured generation. There is no production fake-model switch."""
    async def complete(self, node, data, schema):
        cfg = config()
        profile = cfg["profiles"][settings().model_profile]
        if settings().model_profile != "open":
            raise RuntimeError("Optional paid profile is not configured")
        model = profile["nodes"][node]
        started = time.monotonic()
        error = None
        usages = []
        for attempt in range(cfg["retries"]["model_attempts"]):
            selected = model if attempt == 0 else profile.get("fallback", model)
            recorded = False
            attempt_started = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=settings().model_timeout_seconds) as client:
                    response = await client.post(f"{settings().ollama_url}/api/chat", json={
                        "model": selected, "stream": False, "format": schema.model_json_schema(),
                        "messages": [{"role": "system", "content": prompt(node)},
                                     {"role": "user", "content": json.dumps({"untrusted_data": data})}],
                        "options": {"temperature": 0, "num_predict": cfg.get("generation", {}).get("max_tokens", 1800)},
                    })
                    response.raise_for_status()
                    result = response.json()
                    usage = {"node": node, "model": selected, "provider": "ollama", "test_double": False,
                             "tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                             "latency_seconds": time.monotonic() - attempt_started, "api_usd": None,
                             "generated_tokens": result.get("eval_count", 0),
                             "generation_seconds": result.get("eval_duration", 0) / 1e9,
                             "usage_complete": all(k in result for k in ("prompt_eval_count", "eval_count")),
                             "prompt_version": cfg.get("prompts", {}).get(node, "v1")}
                    usages.append(usage)
                    recorded = True
                    if usage_sink.get() is not None:
                        usage_sink.get().append(usage)
                    output = schema.model_validate_json(result["message"]["content"])
                    return output.model_dump(), {**usage, "tokens": sum(u["tokens"] for u in usages),
                        "generated_tokens": sum(u["generated_tokens"] for u in usages),
                        "generation_seconds": sum(u["generation_seconds"] for u in usages),
                        "latency_seconds": time.monotonic() - started, "attempts": attempt + 1,
                        "usage_complete": all(u["usage_complete"] for u in usages)}
            except (asyncio.CancelledError, httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                if not recorded:
                    unknown = {"node": node, "model": selected, "tokens": 0, "usage_complete": False}
                    usages.append({**unknown, "generated_tokens": 0, "generation_seconds": 0})
                    if usage_sink.get() is not None:
                        usage_sink.get().append(unknown)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                error = exc
                if attempt + 1 < cfg["retries"]["model_attempts"]:
                    await asyncio.sleep(0.25 * 2**attempt)
        raise RuntimeError(f"Open-model generation unavailable or invalid ({type(error).__name__}); initialize Ollama")
