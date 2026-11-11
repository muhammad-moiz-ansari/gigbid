"""Shared evaluation plumbing: an isolated workspace, one seeded tenant per persona and traceable results files.

Call isolate() before importing application modules, so nothing touches the development database.
"""
import hashlib
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"
STAMP = time.strftime("%Y%m%d-%H%M%S")
ORIGIN = "http://localhost:3000"


def isolate(study):
    work = ROOT / ".cache" / "eval" / f"{study}-{STAMP}"
    work.mkdir(parents=True, exist_ok=True)
    os.environ.update({"DATABASE_URL": "sqlite:///" + (work / "domain.db").as_posix(),
                       "CHECKPOINT_URL": str(work / "checkpoints.db"), "QDRANT_PATH": str(work / "qdrant"),
                       "QDRANT_MODE": "local", "MARKETPLACE_MODE": "mock", "QUEUE_MODE": "database",
                       "MCP_TRANSPORT": "stdio"})
    return work


def tenant(persona):
    """A signed-up account holding one persona's portfolio and its jobs on the mock marketplace."""
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from apps.api.db import Base, User, engine, put_record, transaction
    from apps.api.main import app
    from dev_support.mock_marketplace.config import SimulatorConfig
    from dev_support.mock_marketplace.service import _lock
    from evals.dataset import job_spec, metadata
    from rag.ingest.loaders import ingest_text

    Base.metadata.create_all(engine)
    client = TestClient(app)
    email = f"{persona['persona']}-{secrets.token_hex(4)}@eval.test"
    me = client.post("/auth/register", json={"email": email, "password": secrets.token_urlsafe(18)},
                     headers={"origin": ORIGIN}).json()
    client.headers.update({"origin": ORIGIN, "x-csrf-token": me["csrf"]})
    client.put("/auth/profile", json={"name": persona["name"], "persona": persona["persona"],
                                 "floor_fixed": persona["floor_fixed"], "weekly_connects": 1000}).raise_for_status()
    with transaction() as db:
        user = db.scalar(select(User.id).where(User.email == email))
        _lock(db, user)
        for job in persona["jobs"]:
            put_record(db, user, "job", job["id"], job_spec(job))
            put_record(db, user, "client", f"client-{job['id']}",
                       {"id": f"client-{job['id']}", **job["client"], "synthetic": True})
        put_record(db, user, "account", "connects", {"balance": 1000, "spent": 0})
        put_record(db, user, "mock_control", "config", SimulatorConfig().model_dump())
    for item in persona["evidence"]:
        ingest_text(user, item["text"], metadata(persona["persona"], item))
    return client, user


def revision():
    """Code identity, including uncommitted work, without creating a commit."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"commit": git("rev-parse", "--short", "HEAD"), "uncommitted_changes": bool(git("status", "--porcelain"))}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(study, report):
    """One results file per run, carrying what is needed to trace every number back to its inputs."""
    from evals.dataset import fingerprint

    meta = {"study": study, "timestamp": STAMP, "code": revision(),
            "dataset": {"name": "synthetic", "sha256": fingerprint(), "use": "harness validation only"},
            "config_sha256": sha256(ROOT / "agent/config.yaml"),
            "hypotheses_sha256": sha256(ROOT / "evals/hypotheses.md")}
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{study}-{STAMP}.json"
    path.write_text(json.dumps({**meta, **report}, indent=2) + "\n")
    return path
