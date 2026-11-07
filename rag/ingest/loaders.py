"""Versioned ingestion, source aliases and transactional replacement/deletion."""

import hashlib

from sqlalchemy import select

from apps.api.db import Approval, digest, get_record, put_record, transaction
from rag.index.corpus import changed, lock_tenant, records
from rag.ingest.models import ChunkSettings, DocumentSection, PortfolioDocument, SourceMetadata
from rag.ingest.parsers import parse_document


def load_bytes(content: bytes, filename: str) -> str:
    """Compatibility text view. File ingestion must use ingest_file to retain metadata."""
    return "\n".join(section.text for section in parse_document(content, filename).sections)


def chunk_settings():
    from agent.model import config

    cfg = config()["retrieval"]
    return ChunkSettings(size=cfg["chunk_chars"], overlap=cfg["overlap_chars"])


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunks(tenant, document, version):
    result = []
    for section_number, section in enumerate(document.sections, 1):
        text = section.text.replace("\r\n", "\n").replace("\r", "\n")
        offset = 0
        while offset < len(text):
            end = min(offset + version.size, len(text))
            raw = text[offset:end]
            passage = raw.strip()
            start = offset + len(raw) - len(raw.lstrip())
            stop = end - (len(raw) - len(raw.rstrip()))
            if passage:
                metadata = section.metadata.model_dump()
                identity = digest(
                    {
                        "tenant": tenant,
                        "content": _hash(passage),
                        "metadata": section.metadata.model_dump(exclude={"source"}),
                        "section": section_number,
                        "start": start,
                        "location": section.location,
                        "loader": document.loader,
                        "chunker": version.version,
                    }
                )[:24]
                result.append(
                    {
                        "id": identity,
                        "tenant": tenant,
                        **metadata,
                        "text": passage,
                        "content_hash": _hash(passage),
                        "location": f"{section.location}; chars {start}:{stop}",
                    }
                )
            if end == len(text):
                break
            offset += version.size - version.overlap
    return result


def _invalidate(db, tenant, ids):
    for approval in db.scalars(
        select(Approval).where(Approval.tenant == tenant, Approval.consumed.is_(False))
    ):
        cited = set(approval.payload.get("payload", {}).get("evidence_hashes", {}))
        if cited.intersection(ids):
            approval.decision = "invalidated"


def _remove(db, tenant, source, keep=frozenset()):
    prior = get_record(db, tenant, "source", source)
    # Read legacy sources which did not yet have explicit evidence_ids.
    ids = set(prior.value.get("evidence_ids", [])) if prior else set()
    evidence = records(db, tenant, "evidence")
    ids.update(r.key for r in evidence if r.value["source"] == source)
    others = [r for r in records(db, tenant, "source") if r.key != source]
    _invalidate(db, tenant, ids - keep)
    for item in evidence:
        if item.key not in ids or item.key in keep:
            continue
        aliases = [r for r in others if item.key in r.value.get("evidence_ids", [])]
        if aliases:
            if item.value["source"] == source:
                item.value = {**item.value, "source": aliases[0].key}
        else:
            db.delete(item)
            for cached in records(db, tenant, "embedding"):
                if cached.value.get("evidence_id") in (None, item.key):
                    db.delete(cached)
    if prior:
        db.delete(prior)
    original = get_record(db, tenant, "source_document", source)
    if original:
        db.delete(original)
    db.flush()


def ingest_document(tenant: str, document: PortfolioDocument) -> list[dict]:
    source = document.sections[0].metadata.source
    if any(s.metadata.source != source for s in document.sections):
        raise ValueError("A document must have one uploaded source identity")
    from apps.api.config import settings

    if sum(len(s.text.encode("utf-8")) for s in document.sections) > settings().max_upload_bytes:
        raise ValueError("Portfolio text exceeds the configured byte limit")
    if not any(s.text.strip() for s in document.sections):
        raise ValueError("Portfolio text cannot be empty")
    version = chunk_settings()
    normalized = [
        {
            "text": s.text.replace("\r\n", "\n").replace("\r", "\n"),
            "metadata": s.metadata.model_dump(exclude={"source"}),
            "location": s.location,
        }
        for s in document.sections
    ]
    document_hash = digest(
        {"sections": normalized, "loader": document.loader, "chunker": version.version}
    )
    incoming = _chunks(tenant, document, version)
    if not incoming:
        raise ValueError("No usable portfolio passages")
    with transaction() as db:
        lock_tenant(db, tenant)
        prior = get_record(db, tenant, "source", source)
        if prior and prior.value.get("document_hash") == document_hash:
            prior.value = {**prior.value, "hash": document.raw_hash, "raw_hash": document.raw_hash}
            current = {r.key: r.value for r in records(db, tenant, "evidence")}
            if all(item["id"] in current for item in incoming):
                put_record(db, tenant, "source_document", source, document.model_dump())
                return [current[item["id"]] for item in incoming]
        _remove(db, tenant, source, keep={item["id"] for item in incoming})
        for item in incoming:
            # Identical document+metadata under another filename is a provenance alias.
            # Preserve a single inspectable canonical passage rather than duplicate hits.
            if not get_record(db, tenant, "evidence", item["id"]):
                put_record(db, tenant, "evidence", item["id"], item)
        put_record(
            db,
            tenant,
            "source",
            source,
            {
                "hash": document.raw_hash,
                "raw_hash": document.raw_hash,
                "document_hash": document_hash,
                "metadata": document.sections[0].metadata.model_dump(),
                "loader_version": document.loader,
                "chunk_version": version.version,
                "evidence_ids": [item["id"] for item in incoming],
                "provenance": "original-synthetic"
                if any(s.metadata.synthetic for s in document.sections)
                else "user-upload",
            },
        )
        put_record(db, tenant, "source_document", source, document.model_dump())
        db.flush()
        changed(db, tenant)
        current = {r.key: r.value for r in records(db, tenant, "evidence")}
        result = [current[item["id"]] for item in incoming]
    from rag.index.dense import cleanup

    cleanup(tenant)
    return result


def ingest_text(tenant: str, text: str, metadata: dict) -> list[dict]:
    meta = SourceMetadata.model_validate(metadata)
    document = PortfolioDocument(
        sections=[DocumentSection(text=text, location="text", metadata=meta)],
        raw_hash=_hash(text),
        loader="direct-text-v2",
    )
    return ingest_document(tenant, document)


def ingest_file(tenant: str, content: bytes, filename: str, metadata: dict | None = None):
    return ingest_document(tenant, parse_document(content, filename, metadata))


def delete_source(tenant: str, source: str):
    with transaction() as db:
        lock_tenant(db, tenant)
        _remove(db, tenant, source)
        changed(db, tenant)
    from rag.index.dense import cleanup

    cleanup(tenant)


def rechunk(tenant: str):
    with transaction() as db:
        documents = [
            PortfolioDocument.model_validate(r.value)
            for r in records(db, tenant, "source_document")
        ]
    for document in documents:
        ingest_document(tenant, document)
    return len(documents)
