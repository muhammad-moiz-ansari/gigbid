"""Validate and optionally import instructor-provided historical jobs into mock mode."""

import argparse
import csv
import re
from hashlib import sha256
from pathlib import Path

from agent.handoffs import JobSpec
from apps.api.config import ROOT, settings
from apps.api.db import User, transaction
from dev_support.mock_marketplace.seed import seed_marketplace

DEFAULT_SOURCE = ROOT / "data/instructor/archive/Final_Upwork_Dataset.csv"
SKILL_COLUMNS = tuple(f"Category_{i}" for i in range(1, 10))
REQUIRED_COLUMNS = {
    "Job Title", "Job_URL", "Description", "Payment_type", "Job_Cost",
    "New_Connects_Num", *SKILL_COLUMNS,
}


def load_jobs(source: Path, limit: int) -> list[JobSpec]:
    if limit < 1:
        raise ValueError("Limit must be positive")
    jobs = {}
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if missing := REQUIRED_COLUMNS.difference(reader.fieldnames or []):
            raise ValueError(f"Missing archive columns: {', '.join(sorted(missing))}")
        for row in reader:
            if row["Payment_type"] != "Fixed-price":
                continue
            title = (row["Job Title"] or "").strip()
            description = (row["Description"] or "").strip()
            url = (row["Job_URL"] or "").strip()
            amount = (row["Job_Cost"] or "").strip().replace(",", "")
            connects = (row["New_Connects_Num"] or "").strip()
            if not title or not description or not url or not re.fullmatch(r"\$\d+(?:\.\d{1,2})?", amount):
                continue
            if not re.fullmatch(r"[0-9]+", connects) or float(amount[1:]) <= 0:
                continue
            key = "historical-upwork-" + sha256(url.encode()).hexdigest()[:24]
            if key in jobs:
                continue
            skills = list(dict.fromkeys(
                skill for column in SKILL_COLUMNS if (skill := (row[column] or "").strip())
            ))
            jobs[key] = JobSpec(
                id=key, title=title, description=description, skills=skills,
                budget=float(amount[1:]), connects=int(connects), client_id=f"{key}-mock-client",
                timeline=(row.get("Time_Limitation") or "").strip() or "Unspecified",
            )
            if len(jobs) == limit:
                break
    return list(jobs.values())


def import_jobs(tenant: str, jobs: list[JobSpec]) -> None:
    if settings().marketplace_mode != "mock":
        raise ValueError("Historical job import requires mock marketplace mode")
    with transaction() as db:
        if db.get(User, tenant) is None:
            raise ValueError("Tenant does not exist")
    clients = [
        {"id": job.client_id, "verified": False, "spend": 0, "hires": 0, "synthetic": True}
        for job in jobs
    ]
    seed_marketplace(tenant, jobs=[job.model_dump() for job in jobs], clients=clients)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--tenant", help="Existing mock tenant to import into. Omit to validate only.")
    args = parser.parse_args()
    try:
        jobs = load_jobs(args.source, args.limit)
        if not jobs:
            raise ValueError("No usable fixed-price jobs found")
        if args.tenant:
            import_jobs(args.tenant, jobs)
    except (ValueError, OSError, csv.Error) as exc:
        parser.error(str(exc))
    action = "Seeded or already present" if args.tenant else "Validated"
    print(f"{action}: {len(jobs)} historical jobs")


if __name__ == "__main__":
    main()
