import json
from io import BytesIO

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from agent.marketplace_port import Unavailable
from apps.api.config import ROOT, settings
from rag.ingest.github import ingest_repository
from rag.ingest.loaders import ingest_file, ingest_text
from rag.ingest.parsers import parse_document


def test_pdf_cv_preserves_page_provenance(tenant):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(40, 700, "Synthetic CV: Python FastAPI APIs")
    pdf.showPage()
    pdf.drawString(40, 700, "Synthetic CV: SQL reporting")
    pdf.save()
    items = ingest_file(tenant, buffer.getvalue(), "sample-cv.pdf", {"skills": ["Python", "SQL"]})
    assert len(items) == 2 and all(i["type"] == "cv" for i in items)
    assert "page 1" in items[0]["location"] and "page 2" in items[1]["location"]
    assert items[0]["source"] == "sample-cv.pdf" and items[0]["skills"] == ["Python", "SQL"]


def test_markdown_frontmatter_and_outcome_json_preserve_metadata(tenant):
    markdown = (ROOT / "dev_support/fixtures/case_study.md").read_bytes()
    items = ingest_file(tenant, markdown, "case.md")
    assert items[0]["project"] == "Cedar Tasks" and items[0]["synthetic"]
    assert items[0]["persona"] == "full-stack" and "FastAPI" in items[0]["skills"]
    assert "line 10" in items[0]["location"]
    windows = ingest_file(tenant, markdown.replace(b"\n", b"\r\n"), "windows-case.md")
    assert windows[0]["project"] == "Cedar Tasks" and windows[0]["skills"] == items[0]["skills"]
    proposals = ingest_file(
        tenant, (ROOT / "dev_support/fixtures/past_proposals.json").read_bytes(), "proposals.json"
    )
    assert {p["outcome"] for p in proposals} == {"replied", "ignored"}
    assert all(
        p["type"] == "proposal" and p["text"].startswith("Proposed approach:") for p in proposals
    )
    reviews = ingest_file(
        tenant, (ROOT / "dev_support/fixtures/reviews.json").read_bytes(), "reviews.json"
    )
    assert reviews[0]["type"] == "review"
    assert "entry 1" in reviews[0]["location"]


@pytest.mark.parametrize(
    "content,name",
    [
        (b'{"text": 5}', "bad.json"),
        (b"[]", "empty.json"),
        (b'{"text":"test","tenant":"someone-else"}', "foreign.json"),
        (b"\xff", "bad.md"),
        (b"---\nproject: broken\n", "bad.md"),
        (b"not-a-pdf", "bad.pdf"),
        (b"text", "bad.exe"),
        (b"  \n", "empty.txt"),
    ],
)
def test_invalid_uploads_are_rejected(content, name):
    with pytest.raises(ValueError):
        parse_document(content, name)


def test_blank_and_encrypted_pdf_fail_without_inventing_ocr():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    with pytest.raises(ValueError, match="No selectable"):
        parse_document(buf.getvalue(), "scan.pdf")
    writer.encrypt("not-a-real-secret")
    encrypted = BytesIO()
    writer.write(encrypted)
    with pytest.raises(ValueError, match="Encrypted"):
        parse_document(encrypted.getvalue(), "locked.pdf")


def test_byte_limits_metadata_constraints_and_repository_boundary(tenant, monkeypatch):
    monkeypatch.setattr(settings(), "max_upload_bytes", 20)
    with pytest.raises(ValueError, match="byte limit"):
        ingest_text(tenant, "é" * 15, {"source": "unicode.txt"})
    with pytest.raises(ValueError, match="byte limit"):
        parse_document(b"x" * 21, "big.md")


async def test_repository_import_needs_a_name_and_a_github_token(tenant):
    with pytest.raises(ValueError, match="owner/repository"):
        await ingest_repository(tenant, "not-a-repository")
    with pytest.raises(Unavailable, match="GITHUB_TOKEN"):
        await ingest_repository(tenant, "octo/demo")


def test_repository_import_prefers_source_folders_and_skips_generated_files():
    from agent.model import config
    from rag.ingest.github import pick
    tree = {"tree": [{"path": p, "type": "blob", "size": s} for p, s in (
        ("next-env.d.ts", 5), ("scripts/probe.ts", 900), ("src/lib/booking.ts", 800), ("src/app/page.tsx", 300),
        ("README.md", 50), ("docs/notes.md", 40))]}
    assert pick(tree, config()["github"]) == ["README.md", "src/lib/booking.ts", "src/app/page.tsx", "scripts/probe.ts"]


async def test_repository_import_reads_readme_and_code_through_github_mcp(tenant, monkeypatch):
    from contextlib import asynccontextmanager

    from mcp.types import CallToolResult, EmbeddedResource, TextContent, TextResourceContents

    import rag.ingest.github as github
    files = {"README.md": "# Demo\nA FastAPI service.", "app/main.py": "from fastapi import FastAPI\napp = FastAPI()",
             "node_modules/x.js": "vendored", "big.py": "x"}
    tree = [{"path": p, "type": "blob", "size": 99999 if p == "big.py" else 10} for p in files] + [{"path": "app", "type": "tree"}]
    seen = {}

    class Session:
        async def call_tool(self, name, args):
            if name == "get_repository_tree":
                return CallToolResult(content=[TextContent(type="text", text=json.dumps({"tree": tree}))])
            resource = TextResourceContents(uri=f"repo://demo/{args['path']}", text=files[args["path"]])
            return CallToolResult(content=[TextContent(type="text", text="downloaded"),
                                           EmbeddedResource(type="resource", resource=resource)])

    class Client:
        def __init__(self, connections):
            seen.update(connections["github"])

        @asynccontextmanager
        async def session(self, name):
            yield Session()
    monkeypatch.setattr(settings(), "github_token", "test-token")
    monkeypatch.setattr(github, "MultiServerMCPClient", Client)
    items = await ingest_repository(tenant, "octo/demo")
    assert {item["source"] for item in items} == {"github:octo/demo/README.md", "github:octo/demo/app/main.py"}
    assert all(i["type"] == "repository" and i["project"] == "demo" and i["skills"] == ["Python"] for i in items)
    assert seen["url"].endswith("/mcp/readonly")
    assert seen["headers"] == {"Authorization": "Bearer test-token", "X-MCP-Tools": "get_repository_tree,get_file_contents"}


def test_json_does_not_become_raw_portfolio_prose_and_manual_code_is_not_github(tenant):
    payload = json.dumps(
        [{"text": "Reviewed the API tests.", "type": "review", "outcome": "replied"}]
    ).encode()
    item = ingest_file(tenant, payload, "review.json")[0]
    assert item["text"] == "Reviewed the API tests." and item["outcome"] == "replied"
    repo = ingest_file(tenant, b"def example(): return 'synthetic'", "example.py")[0]
    assert repo["type"] == "repository"


def test_unquoted_yaml_date_is_normalized_to_iso_string(tenant):
    result = ingest_file(
        tenant, b"---\ndate: 2026-05-01\nskills: [Python]\n---\nPython API", "dated.md"
    )
    assert result[0]["date"] == "2026-05-01"
