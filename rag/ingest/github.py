"""Portfolio import from a GitHub repository through GitHub's official MCP server (read-only repo tools)."""
import json
from pathlib import PurePosixPath

from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.marketplace_port import Unavailable
from agent.model import config
from apps.api.config import settings
from rag.ingest.loaders import ingest_text

TOOLS = "get_repository_tree,get_file_contents"


def text_of(result):
    """A tool result's text: files arrive as embedded text resources, other results as text blocks."""
    if result.isError:
        raise Unavailable("GitHub MCP error: " + " ".join(getattr(b, "text", "") for b in result.content)[:200])
    files = [b.resource.text for b in result.content if b.type == "resource" and hasattr(b.resource, "text")]
    return "\n".join(files or [b.text for b in result.content if b.type == "text"])


def pick(tree, rules):
    """README first, then source files in configured languages: source folders first, larger files first."""
    entries = tree.get("tree", []) if isinstance(tree, dict) else tree
    files = {e["path"]: e.get("size", 0) for e in entries if e.get("type") in ("blob", "file")
             and e.get("size", 0) <= rules["max_file_bytes"] and not e["path"].endswith(tuple(rules["skip_suffixes"]))
             and not set(PurePosixPath(e["path"]).parts) & set(rules["skip_dirs"])}
    readme = [p for p in files if "/" not in p and p.lower().startswith("readme")]
    code = sorted((p for p in files if PurePosixPath(p).suffix in rules["languages"]),
                  key=lambda p: (PurePosixPath(p).parts[0] not in rules["source_dirs"], -files[p], p))
    return (readme[:1] + code)[: rules["max_files"]]


async def ingest_repository(tenant, repository, persona="own"):
    """Import a repository's README and main source files as portfolio evidence."""
    owner, _, name = repository.strip().partition("/")
    if not owner or not name or "/" in name:
        raise ValueError("Use the form owner/repository")
    if not settings().github_token:
        raise Unavailable("GITHUB_TOKEN is not configured for GitHub MCP repository import")
    rules, items = config()["github"], []
    client = MultiServerMCPClient({"github": {"transport": "streamable_http", "url": rules["mcp_url"], "headers": {
        "Authorization": f"Bearer {settings().github_token}", "X-MCP-Tools": TOOLS}}})
    try:
        async with client.session("github") as session:
            tree = await session.call_tool("get_repository_tree", {"owner": owner, "repo": name, "recursive": True})
            paths = pick(json.loads(text_of(tree)), rules)
            for path in paths:
                text = text_of(await session.call_tool("get_file_contents", {"owner": owner, "repo": name, "path": path}))
                language = rules["languages"].get(PurePosixPath(path).suffix)
                skills = [language] if language else sorted({rules["languages"][PurePosixPath(p).suffix] for p in paths[1:]})
                if text.strip():
                    items += ingest_text(tenant, text, {"source": f"github:{owner}/{name}/{path}"[:200], "type": "repository",
                                                        "project": name, "skills": skills, "persona": persona})
    except ExceptionGroup as group:
        # The MCP transport runs in a task group, which wraps errors; surface the first one.
        raise group.exceptions[0] from None
    return items
