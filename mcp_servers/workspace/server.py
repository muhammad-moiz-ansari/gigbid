from mcp.server.fastmcp import Context

from agent.handoffs import WriteResult
from mcp_servers.common import READ, WRITE, execute_tool, make_server, serve
from mcp_servers.schemas import CalendarSlot, EmailRequest, HoldRequest
from mcp_servers.workspace import service


def create_server():
    server = make_server("GigBid Workspace (local mock)", 8003)

    @server.tool(annotations=READ)
    async def free_slots(ctx: Context) -> list[CalendarSlot]:
        """Read synthetic 30-minute UTC slots. These are not connected calendar availability."""
        return await execute_tool("free_slots", {}, service.free_slots, context=ctx)

    @server.tool(annotations=WRITE)
    async def create_interview_hold(request: HoldRequest, ctx: Context) -> WriteResult:
        """Preview or create an approved tentative local calendar hold. Revalidates slot; never sends an invitation."""
        return await execute_tool(
            "create_interview_hold",
            request.model_dump(),
            lambda tenant: service.write(tenant, request),
            context=ctx,
            mutating=not request.dry_run,
        )

    @server.tool(annotations=WRITE)
    async def create_email_draft(request: EmailRequest, ctx: Context) -> WriteResult:
        """Preview or save an approved, repeat-safe local email draft. Never sends email."""
        return await execute_tool(
            "create_email_draft",
            request.model_dump(),
            lambda tenant: service.write(tenant, request),
            context=ctx,
            mutating=not request.dry_run,
        )

    return server


mcp = create_server()


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
