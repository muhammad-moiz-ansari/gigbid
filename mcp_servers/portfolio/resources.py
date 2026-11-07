from agent.marketplace_port import NotFound
from mcp_servers.portfolio.tools import case


def case_resource(tenant, identity, *, proposal=False):
    item = case(tenant, identity)
    if proposal and item.type != "proposal":
        raise NotFound("Not an outcome-labelled portfolio proposal")
    return item.model_dump_json()
