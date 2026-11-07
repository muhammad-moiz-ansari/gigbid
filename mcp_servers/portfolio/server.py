from pydantic import Field
from sqlalchemy import select

from apps.api.db import Record, get_record, transaction
from mcp_servers.common import READ, audited, make_server, serve, tenant_id
from rag.retriever import retrieve

mcp = make_server("GigBid Portfolio", 8001)


@mcp.tool(annotations=READ)
def search_evidence(requirement: str, k: int = Field(default=5, ge=1, le=20),
                    filters: dict[str, str] | None = None) -> list[dict]:
    """Retrieve tenant-scoped passages with stable IDs, provenance and inspectable text."""
    with audited("search_evidence", {"requirement": requirement, "k": k, "filters": filters}) as tenant:
        return retrieve(tenant, requirement, k, filters)


@mcp.tool(annotations=READ)
def get_case_study(id: str) -> dict:
    """Read the current evidence passage by ID; deleted evidence is unavailable."""
    with audited("get_case_study", {"id": id}) as tenant:
        with transaction() as db:
            record = get_record(db, tenant, "evidence", id)
            if not record:
                raise ValueError("Evidence not found")
            return record.value


@mcp.tool(annotations=READ)
def list_skills() -> list[str]:
    """List skills found in the current tenant's portfolio metadata."""
    with audited("list_skills", {}) as tenant:
        with transaction() as db:
            items = db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == "evidence"))
            return sorted({skill for item in items for skill in item.value["skills"]})


@mcp.resource("portfolio://case/{id}")
def case_resource(id: str) -> str:
    return str(get_case_study(id))


@mcp.resource("portfolio://proposal/{id}")
def proposal_resource(id: str) -> str:
    item = get_case_study(id)
    if item["type"] != "proposal":
        raise ValueError("Not an outcome-labelled portfolio proposal")
    return str(item)


@mcp.prompt()
def answer_screening_question(question: str) -> str:
    from agent.model import prompt
    tenant_id()
    return prompt("screening") + "\n<untrusted_question>\n" + question + "\n</untrusted_question>"


@mcp.prompt()
def portfolio_summary(skill: str) -> str:
    from agent.model import prompt
    tenant_id()
    return prompt("portfolio_summary") + "\n<untrusted_skill>" + skill + "</untrusted_skill>"


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
