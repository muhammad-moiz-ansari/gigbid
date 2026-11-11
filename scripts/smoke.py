"""Real-model smoke check: approved proposals and client replies on a throwaway database.

Runs the real API code, worker, MCP servers and the configured model profile, then writes a
results file to evals/results. The development database is never touched.
"""
import argparse
import asyncio
import json
import os
import secrets
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = time.strftime("%Y%m%d-%H%M%S")
WORK = ROOT / ".cache" / "smoke" / STAMP
WORK.mkdir(parents=True, exist_ok=True)
os.environ.update({"DATABASE_URL": "sqlite:///" + (WORK / "domain.db").as_posix(),
                   "CHECKPOINT_URL": str(WORK / "checkpoints.db"), "QDRANT_PATH": str(WORK / "qdrant"),
                   "MARKETPLACE_MODE": "mock", "QUEUE_MODE": "database"})

from fastapi.testclient import TestClient  # noqa: E402

from agent.model import profile  # noqa: E402
from agent.nodes.workflow import slot_list  # noqa: E402
from apps.api.config import settings  # noqa: E402
from apps.api.db import Base, engine  # noqa: E402
from apps.api.main import app  # noqa: E402
from apps.api.routers.analytics import spread  # noqa: E402
from rag.verify import CITATION  # noqa: E402
from worker.runtime import process_run  # noqa: E402

ORIGIN = "http://localhost:3000"
REPLY = "Thanks for the proposal. Could we schedule an interview to discuss the API?"


def account():
    client = TestClient(app)
    credentials = {"email": f"smoke-{secrets.token_hex(4)}@example.test", "password": secrets.token_urlsafe(18)}
    me = client.post("/auth/register", json=credentials, headers={"origin": ORIGIN}).json()
    client.headers.update({"origin": ORIGIN, "x-csrf-token": me["csrf"]})
    client.post("/dev/seed").raise_for_status()
    return client


def warnings(run, draft):
    """Quality problems that a pass count misses."""
    found = []
    if run["kind"] == "bid" and draft.get("text") and not CITATION.search(draft["text"]):
        found.append("cover letter cites no evidence")
    if run["answers_missing"]:
        found.append("unanswered screening question")
    if run["slots_sent"] is False:
        found.append("offered interview times missing from the reply")
    return found


def summary(run, approved=None):
    state, budget = run["state"], run["state"].get("budget", {})
    usage = state.get("usage", [])
    writer = next((u for u in usage if u["node"] == "writer"), None)
    labels = [c["label"] for c in (state.get("verification") or {}).get("claims", [])]
    draft, price = state.get("draft") or {}, state.get("price") or {}
    answers = draft.get("screening_answers") or {}
    questions = (state.get("job_spec") or {}).get("screening_questions", []) if draft.get("text") else []
    sent = ((state.get("outcome") or {}).get("payload") or (state.get("preview") or {}).get("payload") or {}).get("text", "")
    result = {"kind": run["kind"], "subject": run["subject"], "status": run["status"], "after_approval": approved,
              "steps": budget.get("steps"), "tokens": budget.get("tokens"), "api_usd": budget.get("api_usd"),
              "active_seconds": round(budget.get("active_seconds", 0), 1),
              "models": sorted({u["model"] for u in usage}), "intent": state.get("intent"),
              "writer_prompt_tokens": writer["tokens"] - writer["generated_tokens"] if writer else None,
              "claims_removed": labels.count("unsupported") + labels.count("partly_supported"),
              "cited_sentences": labels.count("supported"), "flags": (state.get("risk") or {}).get("flags"),
              "bid_share": round(price["amount"] / state["job"]["budget"], 2) if price else None,
              "answers_missing": [q for q in questions if not answers.get(q, "").strip()],
              "slots_sent": slot_list(state["slots"]) in sent if state.get("slots") else None,
              "error": state.get("error")}
    return {**result, "warnings": warnings(result, draft)}


async def exercise(client, run_id, approve):
    await process_run(run_id)
    run = client.get(f"/runs/{run_id}").json()
    if not (approve and run["status"] == "awaiting_approval"):
        return summary(run)
    client.post(f"/approvals/{run['state']['approval_id']}/decision", json={"decision": "approve"})
    await process_run(run_id)
    return summary(run, client.get(f"/runs/{run_id}").json()["status"])


async def main(runs):
    Base.metadata.create_all(engine)
    results = []
    for index in range(runs):
        client = account()
        results.append(await exercise(client, client.post("/jobs/mock-api/analyse").json()["id"], approve=True))
        client.post("/dev/client-message", json={"conversation": "mock-api", "text": REPLY})
        results.append(await exercise(client, client.post("/messages/mock-api/draft").json()["id"], approve=True))
        if index == 0:
            for job in ("mock-scam", "mock-injection"):
                results.append(await exercise(client, client.post(f"/jobs/{job}/analyse").json()["id"], approve=False))
    proposals = [r for r in results if r["subject"] == "mock-api" and r["kind"] == "bid"]
    report = {"profile": settings().model_profile, "provider": profile()["provider"], "nodes": profile()["nodes"],
              "runs": results, "proposals_submitted": sum(r["after_approval"] == "submitted" for r in proposals),
              "replies_sent": sum(r["after_approval"] == "sent" for r in results if r["kind"] == "conversation"),
              "proposal_tokens": spread([r["tokens"] for r in proposals if r["tokens"]]),
              "proposal_active_seconds": spread([r["active_seconds"] for r in proposals]),
              "proposal_api_usd": spread([r["api_usd"] for r in proposals if r["api_usd"] is not None]),
              "quality_warnings": sum(len(r["warnings"]) for r in results)}
    out = ROOT / "evals/results" / f"smoke-{STAMP}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    for r in results:
        print(f"{r['kind']:<12} {r['subject']:<15} {r['status']:<18} {str(r['after_approval']):<10} "
              f"tokens {r['tokens']}  {r['active_seconds']} s  cited {r['cited_sentences']}  "
              f"removed {r['claims_removed']}  bid share {r['bid_share']}  {'; '.join(r['warnings'])}  {r['error'] or ''}")
    print(f"Submitted {report['proposals_submitted']}/{len(proposals)} proposals, sent {report['replies_sent']} replies, "
          f"{report['quality_warnings']} quality warnings. Results: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=1, help="Proposal and reply pairs, each on a fresh account")
    asyncio.run(main(parser.parse_args().runs))
