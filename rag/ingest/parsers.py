import hashlib
import json
from datetime import date
from io import BytesIO
from pathlib import PurePosixPath

import yaml
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from apps.api.config import settings
from rag.ingest.models import DocumentSection, PortfolioDocument, SourceMetadata


def parse_document(
    content: bytes, filename: str, metadata: dict | None = None
) -> PortfolioDocument:
    if len(content) > settings().max_upload_bytes:
        raise ValueError("Portfolio file exceeds the configured byte limit")
    filename = PurePosixPath(filename.replace("\\", "/")).name
    base = {"source": filename, **(metadata or {})}
    suffix = PurePosixPath(filename).suffix.casefold()
    sections = []
    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are unsupported; upload an unlocked copy")
            if len(reader.pages) > 100:
                raise ValueError("PDF page limit exceeded")
            meta = SourceMetadata.model_validate({"type": "cv", **base})
            for number, page in enumerate(reader.pages, 1):
                stream = page.get_contents()
                if stream and len(stream.get_data()) > 5_000_000:
                    raise ValueError("PDF page content exceeds extraction limit")
                text = page.extract_text() or ""
                if text.strip():
                    sections.append(
                        DocumentSection(text=text, location=f"page {number}", metadata=meta)
                    )
        except (PdfReadError, OSError, KeyError) as exc:
            raise ValueError("Cannot parse PDF document") from exc
        loader = "pypdf-page-text-v1"
    elif suffix == ".json":
        try:
            data = json.loads(content.decode("utf-8-sig"))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("Invalid UTF-8 JSON portfolio document") from exc
        items = data if isinstance(data, list) else [data]
        if not 1 <= len(items) <= 500:
            raise ValueError("JSON portfolio requires 1 to 500 entries")
        for number, item in enumerate(items, 1):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise ValueError(
                    "Each JSON portfolio entry requires a text string and metadata fields"
                )
            fields = {k: v for k, v in item.items() if k != "text"}
            # File identity belongs to the upload, never an arbitrary entry's path.
            if "source" in fields:
                raise ValueError("JSON entries cannot override the uploaded source identity")
            meta = SourceMetadata.model_validate({**base, **fields})
            sections.append(
                DocumentSection(text=item["text"], location=f"entry {number}", metadata=meta)
            )
        loader = "json-portfolio-entries-v1"
    elif suffix in (".md", ".txt", ".py", ".ts"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeError as exc:
            raise ValueError("Portfolio text must use UTF-8") from exc
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        line = 1
        if suffix == ".md" and text.startswith("---\n"):
            lines = text.splitlines(keepends=True)
            end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
            if end is None:
                raise ValueError("Unclosed Markdown metadata block")
            try:
                fields = yaml.safe_load("".join(lines[1:end])) or {}
            except yaml.YAMLError as exc:
                raise ValueError("Invalid Markdown metadata block") from exc
            if not isinstance(fields, dict) or "source" in fields:
                raise ValueError("Markdown metadata must be a mapping without source overrides")
            if isinstance(fields.get("date"), date):
                fields["date"] = fields["date"].isoformat()
            base = {**fields, **base}
            text, line = "".join(lines[end + 1 :]), end + 2
        if suffix in (".py", ".ts"):
            base = {"type": "repository", **base}
        sections.append(
            DocumentSection(
                text=text, location=f"line {line}", metadata=SourceMetadata.model_validate(base)
            )
        )
        loader = "utf8-markdown-frontmatter-v1" if suffix == ".md" else "utf8-text-v1"
    else:
        raise ValueError(
            "Upload PDF, Markdown, UTF-8 text/code, or structured JSON reviews/proposals"
        )
    if not sections or not any(s.text.strip() for s in sections):
        raise ValueError("No selectable portfolio text found; scanned PDFs need OCR before upload")
    if sum(len(s.text.encode("utf-8")) for s in sections) > settings().max_upload_bytes:
        raise ValueError("Extracted text exceeds the configured byte limit")
    return PortfolioDocument(
        sections=sections, raw_hash=hashlib.sha256(content).hexdigest(), loader=loader
    )
