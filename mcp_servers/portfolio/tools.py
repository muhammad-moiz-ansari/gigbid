from sqlalchemy import select

from agent.handoffs import Evidence
from agent.marketplace_port import NotFound
from apps.api.db import Record, get_record, transaction
from mcp_servers.schemas import EvidenceHit
from rag.retriever import retrieve


def search(tenant, requirement, k, filters):
    return [EvidenceHit.model_validate(item) for item in retrieve(tenant, requirement, k, filters)]


def case(tenant, identity) -> Evidence:
    with transaction() as db:
        record = get_record(db, tenant, "evidence", identity)
        if not record:
            raise NotFound("Evidence not found")
        return Evidence.model_validate(record.value)


def skills(tenant):
    with transaction() as db:
        items = db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == "evidence"))
        return sorted({skill for item in items for skill in item.value["skills"]})
