"""Labelled evaluation data: the synthetic set now, the official dev set when the starter kit arrives."""
import hashlib
import sys
from collections import Counter
from pathlib import Path

import yaml

from agent.handoffs import JobSpec
from rag.ingest.models import SourceMetadata

ROOT = Path(__file__).resolve().parent / "datasets"
JOB_TYPES = {"multi_requirement": 3, "exact_tool": 3, "implied_skill": 2, "vague": 2, "out_of_scope": 2,
             "low_budget": 1, "scam": 2, "injection": 2}
SPEC = ("id", "title", "description", "skills", "budget", "connects", "deliverables", "screening_questions", "timeline")


def files(name="synthetic"):
    return sorted((ROOT / name).glob("*.yaml"))


def fingerprint(name="synthetic"):
    digest = hashlib.sha256()
    for path in files(name):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def job_spec(job):
    return JobSpec.model_validate({**{k: job[k] for k in SPEC if k in job}, "client_id": f"client-{job['id']}"}).model_dump()


def metadata(persona, item):
    fields = ("source", "type", "project", "skills", "date", "industry", "outcome")
    return SourceMetadata.model_validate({**{k: item[k] for k in fields if k in item},
                                          "persona": persona, "synthetic": True}).model_dump()


def check(persona):
    """Problems in one persona file; an empty list means it is usable."""
    problems, evidence, jobs = [], persona.get("evidence", []), persona.get("jobs", [])
    sources = [item.get("source") for item in evidence]
    if len(set(sources)) != len(sources):
        problems.append("duplicate evidence sources")
    for item in evidence:
        try:
            metadata(persona["persona"], item)
        except Exception as exc:
            problems.append(f"{item.get('source')}: {exc}")
        if (item.get("type") == "proposal") != (item.get("outcome") in {"won", "replied", "ignored"}):
            problems.append(f"{item.get('source')}: proposals, and only proposals, carry an outcome")
        if not 0 < len(item.get("text", "")) <= 1000:
            problems.append(f"{item.get('source')}: text must have 1 to 1000 characters")
    ids = [job.get("id") for job in jobs]
    if len(set(ids)) != len(ids):
        problems.append("duplicate job ids")
    if Counter(job.get("job_type") for job in jobs) != Counter(JOB_TYPES):
        problems.append(f"job types differ from {JOB_TYPES}")
    for job in jobs:
        gold, name, kind = job.get("gold", {}), job.get("id"), job.get("job_type")
        try:
            job_spec(job)
            assert {"verified", "spend", "hires"} <= set(job["client"])
        except Exception as exc:
            problems.append(f"{name}: invalid job or client ({type(exc).__name__} {exc})")
        relevant = gold.get("evidence") or {}
        if set(relevant) - set(sources) or set(relevant.values()) - {1, 2}:
            problems.append(f"{name}: gold evidence must name this persona's sources with relevance 1 or 2")
        band = gold.get("price_band")
        if gold.get("bid") and not (band and 0 < band[0] <= band[1] <= job.get("budget", 0)):
            problems.append(f"{name}: a bid job needs a price band within its budget")
        if kind == "scam" and (gold.get("bid") or not gold.get("scam")):
            problems.append(f"{name}: scam jobs are skipped and marked scam")
        if kind == "out_of_scope" and relevant:
            problems.append(f"{name}: out-of-scope jobs have no relevant evidence")
        if kind == "injection" and not (job.get("canary") and job["canary"] in job.get("description", "")):
            problems.append(f"{name}: injection jobs plant their canary in the description")
    return problems


def load(name="synthetic"):
    personas = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in files(name)]
    problems = [f"{p.get('persona')}: {issue}" for p in personas for issue in check(p)]
    if problems:
        raise ValueError("Dataset problems:\n" + "\n".join(problems))
    return personas


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "synthetic"
    for path in files(name):
        persona = yaml.safe_load(path.read_text(encoding="utf-8"))
        issues = check(persona)
        print(f"{path.name}: {len(persona.get('evidence', []))} evidence, {len(persona.get('jobs', []))} jobs, "
              f"{len(issues)} problems")
        for issue in issues:
            print("  -", issue)
    print("fingerprint", fingerprint(name))
