from agent.marketplace_port import MarketplacePort
from apps.api.config import settings
from dev_support.mock_marketplace.service import MockMarketplace
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.marketplace.adapters.upwork_live import UpworkAdapter


def marketplace(mode: str | None = None) -> MarketplacePort:
    selected = mode or settings().marketplace_mode
    adapters = {"mock": MockMarketplace, "gigsim": GigSimAdapter, "upwork": UpworkAdapter}
    if selected not in adapters:
        raise ValueError(f"Unknown marketplace mode: {selected}")
    return adapters[selected]()
