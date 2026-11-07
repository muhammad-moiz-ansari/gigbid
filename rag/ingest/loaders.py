import hashlib
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import delete, select

from agent.handoffs import Evidence
from apps.api.db import Approval, Record, get_record, put_record, transaction


def load_bytes(content: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    if not filename.lower().endswith((".md", ".txt", ".json", ".py", ".ts")):
        raise ValueError("Upload PDF, Markdown, plain text, JSON reviews/proposals or source text")
    return content.decode("utf-8")


def ingest_text(tenant: str, text: str, metadata: dict) -> list[dict]:
    source = metadata["source"]
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    with transaction() as db:
        prior = get_record(db, tenant, "source", source)
        if prior and prior.value["hash"] == content_hash and prior.value.get("metadata") == metadata:
            return [r.value for r in db.scalars(select(Record).where(Record.tenant == tenant,
                    Record.kind == "evidence")) if r.value["source"] == source]
        _delete_source(db, tenant, source)
        result = []
        # Fixed chunks establish V0; no generated summaries or synthetic embeddings.
        for offset in range(0, len(text), 1050):
            passage = text[offset:offset + 1200].strip()
            if not passage:
                continue
            identity = hashlib.sha256(f"{tenant}:{source}:{offset}:{content_hash}".encode()).hexdigest()[:24]
            evidence = Evidence(id=identity, tenant=tenant, source=source,
                location=f"chars {offset}:{offset + len(passage)}", text=passage,
                content_hash=hashlib.sha256(passage.encode()).hexdigest(),
                type=metadata.get("type", "case_study"), persona=metadata.get("persona", "own"),
                project=metadata.get("project", source), skills=metadata.get("skills", []),
                date=metadata.get("date", "unspecified"), industry=metadata.get("industry", "unspecified"),
                outcome=metadata.get("outcome", "unknown"), synthetic=metadata.get("synthetic", False))
            put_record(db, tenant, "evidence", identity, evidence.model_dump())
            result.append(evidence.model_dump())
        put_record(db, tenant, "source", source, {"hash": content_hash, "metadata": metadata,
                                                  "chunk_version": "fixed-1200-150-v1"})
        return result


def _delete_source(db, tenant, source):
    for record in db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == "evidence")):
        if record.value["source"] == source:
            db.delete(record)
    db.execute(delete(Record).where(Record.tenant == tenant, Record.kind == "embedding"))
    for approval in db.scalars(select(Approval).where(Approval.tenant == tenant,
                                                      Approval.consumed.is_(False))):
        approval.decision = "invalidated"


def delete_source(tenant: str, source: str):
    with transaction() as db:
        _delete_source(db, tenant, source)
        record = get_record(db, tenant, "source", source)
        if record:
            db.delete(record)
