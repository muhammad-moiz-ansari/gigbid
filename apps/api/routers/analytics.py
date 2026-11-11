import math
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select

from agent.categories import category
from apps.api.auth.service import current_user
from apps.api.config import settings
from apps.api.db import Approval, Record, Run, User, get_record, transaction
from apps.api.schemas.api import Analytics

router = APIRouter(tags=["analytics"])
REPLIED = ("replied", "interview", "hired")


def records(db, tenant, kind):
    return [r.value for r in db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == kind))]


def spread(values):
    """Nearest-rank median and 95th percentile; empty until something was measured."""
    values = sorted(values)

    def pick(q):
        return values[max(0, math.ceil(q * len(values)) - 1)] if values else None
    return {"p50": pick(0.5), "p95": pick(0.95)}


def rate(part, whole):
    return part / whole if whole else None


@router.get("/analytics", response_model=Analytics)
def analytics(user: User = Depends(current_user)):
    with transaction() as db:
        runs = list(db.scalars(select(Run).where(Run.tenant == user.id)))
        bids = {r.subject: r for r in runs if r.kind == "bid"}
        groups, seen = {}, {}
        for item in records(db, user.id, "outcome_observation"):
            seen.setdefault(item["job_id"], set()).add(item["status"])
        for item in records(db, user.id, "pipeline"):
            if item["status"] == "drafted":
                continue
            job = bids[item["subject"]].state.get("job", {}) if item["subject"] in bids else {}
            stats = groups.setdefault(category(job.get("skills", [])),
                                      {"submitted": 0, "replied": 0, "hired": 0, "connects_spent": 0})
            stats["submitted"] += 1
            stats["replied"] += bool(seen.get(item["subject"], set()) & set(REPLIED))
            stats["hired"] += "hired" in seen.get(item["subject"], set())
            stats["connects_spent"] += job.get("connects", 0)
        budgets = [r.state.get("budget", {}) for r in bids.values() if r.state.get("draft", {}).get("text")]
        reasons = Counter(a.reason for a in db.scalars(select(Approval).where(
            Approval.tenant == user.id, Approval.decision == "rejected")) if a.reason)
        reasons.update(f"Skipped: {skip['reason']}" for skip in records(db, user.id, "job_skip"))
        account = get_record(db, user.id, "account", "connects")
        submitted = sum(g["submitted"] for g in groups.values())
        replied = sum(g["replied"] for g in groups.values())
        hired = sum(g["hired"] for g in groups.values())
        return Analytics(
            mode=settings().marketplace_mode, synthetic=settings().marketplace_mode == "mock",
            submitted=submitted, replied=replied, hired=hired,
            reply_rate=rate(replied, submitted), hire_rate=rate(hired, submitted),
            connects=account.value if account else {},
            by_category=[{"category": name, **g, "reply_rate": rate(g["replied"], g["submitted"]),
                          "hire_rate": rate(g["hired"], g["submitted"])} for name, g in sorted(groups.items())],
            proposal_tokens=spread([b["tokens"] for b in budgets if "tokens" in b]),
            proposal_active_seconds=spread([b["active_seconds"] for b in budgets if "active_seconds" in b]),
            proposal_api_usd=spread([b["api_usd"] for b in budgets if "api_usd" in b]),
            rejection_reasons=[{"reason": r, "count": c} for r, c in reasons.most_common(5)],
            runs=len(runs), usage=[u for r in runs for u in r.state.get("usage", [])],
            official_outcomes="pending instructor simulator")
