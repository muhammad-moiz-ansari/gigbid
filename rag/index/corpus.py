"""Canonical SQL evidence and versioned index manifests. Every lookup is tenant scoped."""

import re

from sqlalchemy import select, text

from apps.api.db import Record, User, digest, get_record, put_record, transaction

TOKENIZER = "casefold-word-symbols-v1"


def tokens(value):
    return re.findall(r"[\w.+#-]+", value.casefold())


def lock_tenant(db, tenant):
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
        user = db.get(User, tenant)
    else:
        user = db.scalar(select(User).where(User.id == tenant).with_for_update())
    if not user:
        raise PermissionError("Unknown portfolio tenant")


def records(db, tenant, kind):
    return list(
        db.scalars(
            select(Record).where(Record.tenant == tenant, Record.kind == kind).order_by(Record.key)
        )
    )


def snapshot_in(db, tenant):
    items = [r.value for r in records(db, tenant, "evidence")]
    return items, digest(items)


def snapshot(tenant):
    with transaction() as db:
        return snapshot_in(db, tenant)


def changed(db, tenant, force=False):
    items, fingerprint = snapshot_in(db, tenant)
    old = get_record(db, tenant, "corpus", "portfolio")
    same = old and old.value["fingerprint"] == fingerprint
    if same and not force:
        return
    revision = old.value["revision"] if same else old.value["revision"] + 1 if old else 1
    put_record(
        db,
        tenant,
        "corpus",
        "portfolio",
        {
            "fingerprint": fingerprint,
            "revision": revision,
            "chunks": len(items),
            "format": "evidence-v1",
        },
    )
    active = {item["id"] for item in items}
    prior = {r.key: r for r in records(db, tenant, "lexical_chunk")}
    for item in items:
        identity = digest(
            {"content_hash": item["content_hash"], "skills": item["skills"], "tokenizer": TOKENIZER}
        )
        if item["id"] not in prior or prior[item["id"]].value["fingerprint"] != identity:
            put_record(
                db,
                tenant,
                "lexical_chunk",
                item["id"],
                {
                    "fingerprint": identity,
                    "tokens": tokens(item["text"] + " " + " ".join(item["skills"])),
                },
            )
    for key in set(prior) - active:
        db.delete(prior[key])
    put_record(
        db,
        tenant,
        "index_manifest",
        "bm25",
        {
            "fingerprint": fingerprint,
            "corpus_revision": revision,
            "tokenizer": TOKENIZER,
            "algorithm": "BM25Okapi",
            "package_version": "rank-bm25==0.2.2",
            "status": "ready",
        },
    )
    for state in records(db, tenant, "dense_index"):
        value = state.value
        if value.get("fingerprint") and value["fingerprint"] != fingerprint:
            key = digest({"collection": value["collection"], "fingerprint": value["fingerprint"]})
            put_record(
                db,
                tenant,
                "vector_cleanup",
                key,
                {
                    "collection": value["collection"],
                    "fingerprint": value["fingerprint"],
                    "status": "pending",
                },
            )
            state.value = {**value, "status": "pending"}


def status(tenant):
    with transaction() as db:
        items, fingerprint = snapshot_in(db, tenant)
        corpus = get_record(db, tenant, "corpus", "portfolio")
        lexical = get_record(db, tenant, "index_manifest", "bm25")
        return {
            "corpus": corpus.value
            if corpus
            else {"fingerprint": fingerprint, "revision": 0, "chunks": len(items)},
            "sources": [{"source": r.key, **r.value} for r in records(db, tenant, "source")],
            "bm25": lexical.value if lexical else {"status": "not_indexed"},
            "dense": [r.value for r in records(db, tenant, "dense_index")]
            or [{"status": "pending"}],
            "vector_cleanup_pending": len(records(db, tenant, "vector_cleanup")),
        }
