from agent.marketplace_port import AdapterReadiness
from mcp_servers.marketplace.adapters.unavailable import UnavailableMarketplace


class UpworkAdapter(UnavailableMarketplace):
    """Fail closed. No guessed tool names, OAuth registration or live side effects."""

    readiness = AdapterReadiness(
        mode="upwork",
        implemented=False,
        contract_verified=False,
        externally_verified=False,
        synthetic=False,
        detail="Upwork OAuth and capability mappings await verified contract and authorization",
    )
