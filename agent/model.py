import asyncio
import json
import time
from functools import lru_cache

import httpx
import yaml

from apps.api.config import ROOT, settings


@lru_cache
def config():
    return yaml.safe_load((ROOT / "agent/config.yaml").read_text(encoding="utf-8"))


def prompt(node):
    return (ROOT / "agent/prompts" / f"{node}.v1.md").read_text(encoding="utf-8")


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
        for attempt in range(cfg["retries"]["model_attempts"]):
            selected = model if attempt == 0 else profile.get("fallback", model)
            try:
                async with httpx.AsyncClient(timeout=settings().model_timeout_seconds) as client:
                    response = await client.post(f"{settings().ollama_url}/api/chat", json={
                        "model": selected, "stream": False, "format": schema.model_json_schema(),
                        "messages": [{"role": "system", "content": prompt(node)},
                                     {"role": "user", "content": json.dumps({"untrusted_data": data})}],
                        "options": {"temperature": 0, "num_predict": 1800},
                    })
                    response.raise_for_status()
                    result = response.json()
                    output = schema.model_validate_json(result["message"]["content"])
                    usage = {"node": node, "model": selected, "provider": "ollama", "test_double": False,
                             "tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                             "latency_seconds": time.monotonic() - started, "api_usd": None,
                             "generated_tokens": result.get("eval_count", 0),
                             "generation_seconds": result.get("eval_duration", 0) / 1e9}
                    return output.model_dump(), usage
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                error = exc
                if attempt + 1 < cfg["retries"]["model_attempts"]:
                    await asyncio.sleep(0.25 * 2**attempt)
        raise RuntimeError(f"Open-model generation unavailable or invalid ({type(error).__name__}); initialize Ollama")
