from agent.marketplace_port import AdapterReadiness
from mcp_servers.marketplace.adapters.unavailable import UnavailableMarketplace


class GigSimAdapter(UnavailableMarketplace):
    readiness = AdapterReadiness(
        mode="gigsim",
        implemented=False,
        contract_verified=False,
        externally_verified=False,
        synthetic=False,
        detail="Official GigSim contract is missing; adapter mapping is not implemented",
    )
