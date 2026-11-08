import asyncio
import json
import time
from contextvars import ContextVar
from functools import lru_cache

import httpx
import yaml

from apps.api.config import ROOT, settings

usage_sink = ContextVar("model_usage_sink", default=None)


class RateLimited(Exception):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__(f"Model provider rate limit; retry after {retry_after:g} s")


@lru_cache
def _config(content):
    return yaml.safe_load(content)


def config():
    # Content-keyed cache notices policy/budget edits in an already running worker.
    return _config((ROOT / "agent/config.yaml").read_text(encoding="utf-8"))


def prompt(node):
    version = config().get("prompts", {}).get(node, "v1")
    return (ROOT / "agent/prompts" / f"{node}.{version}.md").read_text(encoding="utf-8")


def profile():
    selected = config()["profiles"][settings().model_profile]
    if not selected.get("provider"):
        raise RuntimeError(f"Model profile '{settings().model_profile}' is not configured")
    return selected


async def ollama(client, selected, model, messages, schema, cap):
    response = await client.post(f"{settings().ollama_url}/api/chat", json={
        "model": model, "stream": False, "format": schema.model_json_schema(), "think": selected.get("think", False),
        "keep_alive": selected.get("keep_alive", "5m"), "messages": messages,
        "options": {"temperature": 0, "num_predict": cap}})
    response.raise_for_status()
    result = response.json()
    return (result["message"]["content"], result.get("prompt_eval_count"), result.get("eval_count"),
            result.get("eval_duration", 0) / 1e9)


async def groq(client, selected, model, messages, schema, cap):
    """OpenAI-compatible JSON mode: every completed call reports usage, even when its JSON is invalid."""
    if not settings().groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured for the hosted open profile")
    system = f"{messages[0]['content']}\n{prompt('json_mode').strip()} {json.dumps(schema.model_json_schema())}"
    response = await client.post(f"{selected['base_url']}/chat/completions",
                                 headers={"Authorization": f"Bearer {settings().groq_api_key}"}, json={
        "model": model, "temperature": 0, "max_completion_tokens": cap,
        "reasoning_effort": selected.get("reasoning_effort", "low"), "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, *messages[1:]]})
    if response.status_code == 429:
        raise RateLimited(float(response.headers.get("retry-after", 1)))
    response.raise_for_status()
    body = response.json()
    usage = body.get("usage", {})
    return (body["choices"][0]["message"]["content"], usage.get("prompt_tokens"), usage.get("completion_tokens"),
            usage.get("completion_time", 0))


PROVIDERS = {"ollama": ollama, "groq": groq}


def cost(selected, model, prompt_tokens, completion_tokens):
    price = selected.get("usd_per_million_tokens", {}).get(model)
    return (prompt_tokens * price[0] + completion_tokens * price[1]) / 1e6 if price else None


def total(usages):
    """Totals across attempts; API cost stays unknown (None) when no attempt reported one."""
    costs = [u["api_usd"] for u in usages if u.get("api_usd") is not None]
    return {"tokens": sum(u["tokens"] for u in usages), "api_usd": sum(costs) if costs else None,
            "generated_tokens": sum(u["generated_tokens"] for u in usages),
            "generation_seconds": sum(u["generation_seconds"] for u in usages),
            "usage_complete": all(u["usage_complete"] for u in usages)}


class OpenModel:
    """Open-weight models from the configured profile (hosted Groq or local Ollama). No fake-model switch."""
    async def complete(self, node, data, schema):
        cfg, selected = config(), profile()
        primary = selected["nodes"][node]
        caps = selected.get("max_tokens", {})
        messages = [{"role": "system", "content": prompt(node)},
                    {"role": "user", "content": json.dumps({"untrusted_data": data})}]
        started, error, usages = time.monotonic(), None, []
        for attempt in range(cfg["retries"]["model_attempts"]):
            model = primary if attempt == 0 else selected.get("fallbacks", {}).get(primary, primary)
            recorded = False
            attempt_started = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=settings().model_timeout_seconds) as client:
                    content, prompt_tokens, completion_tokens, seconds = await PROVIDERS[selected["provider"]](
                        client, selected, model, messages, schema, caps.get(node, caps.get("default", 1000)))
                usage = {"node": node, "model": model, "provider": selected["provider"], "test_double": False,
                         "tokens": (prompt_tokens or 0) + (completion_tokens or 0),
                         "latency_seconds": time.monotonic() - attempt_started,
                         "api_usd": cost(selected, model, prompt_tokens or 0, completion_tokens or 0),
                         "generated_tokens": completion_tokens or 0, "generation_seconds": seconds or 0,
                         "usage_complete": prompt_tokens is not None and completion_tokens is not None,
                         "prompt_version": cfg.get("prompts", {}).get(node, "v1")}
                usages.append(usage)
                recorded = True
                if usage_sink.get() is not None:
                    usage_sink.get().append(usage)
                output = schema.model_validate_json(content)
                return output.model_dump(), {**usage, **total(usages), "attempts": attempt + 1,
                                             "latency_seconds": time.monotonic() - started}
            except RateLimited as exc:
                # A rate-limited request generated nothing, so its usage is known to be zero.
                rejected = {"node": node, "model": model, "provider": selected["provider"], "tokens": 0,
                            "usage_complete": True}
                usages.append({**rejected, "generated_tokens": 0, "generation_seconds": 0})
                if usage_sink.get() is not None:
                    usage_sink.get().append(rejected)
                error = exc
                await asyncio.sleep(min(exc.retry_after, cfg["retries"].get("max_rate_limit_wait_seconds", 10)))
            except (asyncio.CancelledError, httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                # A request the provider rejected (4xx) produced no answer; timeouts and 5xx leave usage unknown.
                rejected = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500
                if not recorded:
                    unknown = {"node": node, "model": model, "tokens": 0, "usage_complete": rejected}
                    usages.append({**unknown, "generated_tokens": 0, "generation_seconds": 0})
                    if usage_sink.get() is not None:
                        usage_sink.get().append(unknown)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                error = exc
                if attempt + 1 < cfg["retries"]["model_attempts"]:
                    await asyncio.sleep(0.25 * 2**attempt)
        raise RuntimeError(f"Open-model generation unavailable or invalid ({type(error).__name__}); "
                           f"check the {selected['provider']} model profile")
