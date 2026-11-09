"""R&D A: does tool granularity change agent behaviour? One model call per labelled task and tool set; no tool runs.

Sets: fine (the 16 MCP tools as published), coarse (one tool per server with an action argument) and rewritten
(the same 16 tools and schemas with rewritten descriptions). Calls are appended to a JSONL file, so a run stopped
by the daily quota resumes where it stopped.
Usage: python -m evals.runners.tools [--model openai/gpt-oss-20b]
"""
import argparse
import json
import time
from statistics import mean

import httpx
import yaml

from agent.model import config
from evals.runners.common import RESULTS, ROOT, sha256, write

SCHEMA, TASKS = ROOT / "tests/contract/mcp_schema.json", ROOT / "evals/datasets/tool_tasks.yaml"
SYSTEM = "You are GigBid's assistant for one freelancer. Serve the request with exactly one tool call."
URL = "https://api.groq.com/openai/v1/chat/completions"


def published():
    """Server name -> its MCP tools exactly as the schema snapshot records them."""
    return {server.split()[1].lower(): tools for server, tools in json.loads(SCHEMA.read_text()).items()}


def function(name, description, parameters):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


def outline(schema):
    """Argument names, with nested request objects spelled out, for the coarse tools' descriptions."""
    defs = schema.get("$defs", {})

    def names(properties):
        refs = {name: spec.get("$ref", "").split("/")[-1] for name, spec in properties.items()}
        return ", ".join(f"{name}: {{{names(defs[ref]['properties'])}}}" if ref in defs else name
                         for name, ref in refs.items())
    return names(schema.get("properties", {}))


def tool_sets(rewritten):
    servers = published()
    every = [tool for tools in servers.values() for tool in tools]
    coarse = [function(server, f"All {server} operations: set action and pass that action's arguments. Actions: " + "; ".join(
        f"{t['name']}({outline(t['inputSchema'])}): {t['description']}" for t in tools), {
        "type": "object", "required": ["action", "arguments"],
        "properties": {"action": {"type": "string", "enum": [t["name"] for t in tools]},
                       "arguments": {"type": "object", "description": "The chosen action's arguments"}}})
        for server, tools in servers.items()]
    return {"fine": [function(t["name"], t["description"], t["inputSchema"]) for t in every], "coarse": coarse,
            "rewritten": [function(t["name"], rewritten[t["name"]], t["inputSchema"]) for t in every]}


def matches(expected, actual):
    if isinstance(expected, dict) and "contains" in expected:
        return all(word.casefold() in str(actual).casefold() for word in expected["contains"])
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(matches(value, actual.get(key)) for key, value in expected.items())
    return str(expected).casefold() == str(actual).casefold()


def ask(model, tools, task, effort="low", cap=1000):
    """One completion; returns the body, a provider-rejected call, or None when the daily quota is spent."""
    from apps.api.config import settings

    body = {"model": model, "temperature": 0, "reasoning_effort": effort, "tools": tools, "tool_choice": "auto",
            "max_completion_tokens": cap, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]}
    for _ in range(8):
        response = httpx.post(URL, headers={"Authorization": f"Bearer {settings().groq_api_key}"}, json=body, timeout=90)
        wait = float(response.headers.get("retry-after", 5))
        if response.status_code == 429 and wait > 120:
            return None
        if response.status_code == 429:
            time.sleep(wait)
            continue
        if response.status_code == 400 and "tool_use_failed" in response.text:
            return {"rejected": True}
        response.raise_for_status()
        return response.json()
    return None


def judge(task, kind, body, servers):
    """Tool-selection and argument accuracy of the first tool call."""
    calls = ((body.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []
    name = calls[0]["function"]["name"] if calls else None
    try:
        arguments = json.loads(calls[0]["function"]["arguments"] or "{}") if calls else {}
    except json.JSONDecodeError:
        arguments = None
    if kind == "coarse" and isinstance(arguments, dict):
        name = arguments.get("action") if name == servers[task["tool"]] else None
        arguments = arguments.get("arguments")
        arguments = json.loads(arguments) if isinstance(arguments, str) and arguments.strip().startswith("{") else arguments
    usage = body.get("usage") or {}
    selected = name == task["tool"]
    return {"selected": name, "tool_correct": selected,
            "arguments_correct": selected and isinstance(arguments, dict) and matches(task["arguments"], arguments),
            "rejected_by_provider": bool(body.get("rejected")), "prompt_tokens": usage.get("prompt_tokens"),
            "tokens": usage.get("total_tokens"),
            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)}


def summary(rows):
    priced = [r["tokens"] for r in rows if r["tokens"]]
    return {"tasks": len(rows), "tool_selection_accuracy": round(mean(r["tool_correct"] for r in rows), 3),
            "argument_accuracy": round(mean(r["arguments_correct"] for r in rows), 3),
            "tokens_per_task": round(mean(priced)) if priced else None,
            "rejected_by_provider": sum(r["rejected_by_provider"] for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=config()["evaluation"]["tool_study"]["model"])
    parser.add_argument("--pause", type=float, default=4, help="Seconds between calls, under per-minute token limits")
    args = parser.parse_args()
    data, study = yaml.safe_load(TASKS.read_text()), config()["evaluation"]["tool_study"]
    sets, servers = tool_sets(data["rewritten"]), {t["name"]: s for s, tools in published().items() for t in tools}
    path = RESULTS / f"tools-{args.model.split('/')[-1]}-{sha256(TASKS)[:8]}.jsonl"
    done = {(r["task"], r["set"]) for r in map(json.loads, path.read_text().splitlines())} if path.exists() else set()
    stopped = False
    for number, task in enumerate(data["tasks"]):
        for kind, tools in sets.items():
            if (number, kind) in done or stopped:
                continue
            body = ask(args.model, tools, task["task"], study["reasoning_effort"], study["max_tokens"])
            if body is None:
                print("Daily quota reached; run again later to resume.")
                stopped = True
                continue
            row = {"task": number, "set": kind, "expected": task["tool"], **judge(task, kind, body, servers)}
            with path.open("a") as handle:
                handle.write(json.dumps(row) + "\n")
            print(f"{number:>2} {kind:<9} {str(row['selected']):<22} tool {row['tool_correct']!s:<5} "
                  f"args {row['arguments_correct']!s:<5} tokens {row['tokens']}", flush=True)
            time.sleep(args.pause)
    rows = list(map(json.loads, path.read_text().splitlines())) if path.exists() else []
    report = {"model": args.model, "rows_file": path.name, "tasks_sha256": sha256(TASKS),
              "schema_sha256": sha256(SCHEMA), "tasks": len(data["tasks"]),
              "sets": {kind: summary([r for r in rows if r["set"] == kind]) for kind in sets
                       if any(r["set"] == kind for r in rows)}}
    print(json.dumps(report["sets"], indent=1), f"\nResults: {write('tools', report).name}")


if __name__ == "__main__":
    main()
