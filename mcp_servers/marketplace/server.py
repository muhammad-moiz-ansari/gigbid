from pydantic import Field

from agent.handoffs import JobSpec, WriteRequest, WriteResult
from mcp_servers.common import READ, WRITE, audited, make_server, serve
from mcp_servers.marketplace.adapters import marketplace

mcp = make_server("GigBid Marketplace", 8002)


@mcp.tool(annotations=READ)
def search_jobs(query: str = "") -> list[JobSpec]:
    """Read tenant-visible jobs matching a saved-search query; never submits a bid."""
    with audited("search_jobs", {"query": query}) as tenant:
        return marketplace().search(tenant, query)


@mcp.tool(annotations=READ)
def get_job(job_id: str) -> JobSpec:
    """Read one job including its current Connects cost."""
    with audited("get_job", {"job_id": job_id}) as tenant:
        return marketplace().job(tenant, job_id)


@mcp.tool(annotations=READ)
def get_client_history(client_id: str) -> dict:
    """Read client verification, recorded spend and hiring history."""
    with audited("get_client_history", {"client_id": client_id}) as tenant:
        return marketplace().client_history(tenant, client_id)


@mcp.tool(annotations=READ)
def get_connects_balance() -> dict:
    """Read current Connects balance and recorded spend."""
    with audited("get_connects_balance", {}) as tenant:
        return marketplace().balance(tenant)


@mcp.tool(annotations=READ)
def list_messages(conversation: str) -> list[dict]:
    """Read messages in a tenant-owned conversation."""
    with audited("list_messages", {"conversation": conversation}) as tenant:
        return marketplace().messages(tenant, conversation)


@mcp.tool(annotations=READ)
def list_events(after: int = Field(default=0, ge=0)) -> list[dict]:
    """Read marketplace event history after a monotonic cursor."""
    with audited("list_events", {"after": after}) as tenant:
        return marketplace().events(tenant, after)


def _write(tool, request, kind):
    if request.action.kind != kind:
        raise ValueError(f"{tool} requires action.kind={kind}")
    with audited(tool, request.model_dump()) as tenant:
        return marketplace().write(tenant, request)


@mcp.tool(annotations=WRITE)
def create_proposal_draft(request: WriteRequest) -> WriteResult:
    """Preview a draft without effects; execution requires an exact human approval."""
    return _write("create_proposal_draft", request, "draft")


@mcp.tool(annotations=WRITE)
def submit_proposal(request: WriteRequest) -> WriteResult:
    """Preview exact payload and Connects cost, or execute an approved idempotent mock bid."""
    return _write("submit_proposal", request, "proposal")


@mcp.tool(annotations=WRITE)
def send_message(request: WriteRequest) -> WriteResult:
    """Preview a reply or send only the exact approved message using a stable key."""
    return _write("send_message", request, "message")


@mcp.tool(annotations=READ)
def reconcile_write(idempotency_key: str) -> WriteResult | None:
    """Read the recorded result after an ambiguous write; does not repeat the effect."""
    with audited("reconcile_write", {"idempotency_key": idempotency_key}) as tenant:
        return marketplace().reconcile(tenant, idempotency_key)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
