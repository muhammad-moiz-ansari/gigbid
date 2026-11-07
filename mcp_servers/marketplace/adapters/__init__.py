from apps.api.config import settings
from dev_support.mock_marketplace.service import MockMarketplace
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.marketplace.adapters.upwork_live import UpworkAdapter


def marketplace():
    return {"mock": MockMarketplace, "gigsim": GigSimAdapter,
            "upwork": UpworkAdapter}[settings().marketplace_mode]()
