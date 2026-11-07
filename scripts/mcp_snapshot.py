import asyncio
import json

from mcp.shared.memory import create_connected_server_and_client_session

from apps.api.config import ROOT
from mcp_servers.marketplace.server import mcp as marketplace
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace


async def main():
    snapshot = {}
    extras = {}
    for server in (marketplace, portfolio, workspace):
        async with create_connected_server_and_client_session(server) as session:
            tools = await session.list_tools()
            snapshot[server.name] = [
                tool.model_dump(mode="json", exclude_none=True) for tool in tools.tools
            ]
            templates = await session.list_resource_templates()
            prompts = await session.list_prompts()
            extras[server.name] = {
                "resource_templates": [
                    t.model_dump(mode="json", exclude_none=True)
                    for t in templates.resourceTemplates
                ],
                "prompts": [p.model_dump(mode="json", exclude_none=True) for p in prompts.prompts],
            }
    path = ROOT / "tests/contract/mcp_schema.json"
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    (path.parent / "mcp_resources_prompts.json").write_text(
        json.dumps(extras, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
