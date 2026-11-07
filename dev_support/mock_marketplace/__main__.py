"""Local simulator controls only. Does not run MCP, workers or a live adapter."""

import argparse
import json
from dataclasses import asdict

from apps.api.config import settings
from dev_support.mock_marketplace.config import FaultScenario, SimulatorConfig
from dev_support.mock_marketplace.seed import seed_marketplace
from dev_support.mock_marketplace.service import MockMarketplace
from mcp_servers.marketplace.adapters import marketplace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "seed", "fault", "configure", "advance"])
    parser.add_argument("--tenant")
    parser.add_argument("--json", default="{}", help="Validated JSON config or fault scenario")
    parser.add_argument("--tick-key", help="Stable key for one idempotent outcome tick")
    args = parser.parse_args()
    if args.command == "status":
        adapter = marketplace()
        print(
            json.dumps(
                {
                    "readiness": asdict(adapter.readiness),
                    "capabilities": asdict(adapter.capabilities),
                },
                indent=2,
            )
        )
        return
    if settings().marketplace_mode != "mock":
        parser.error("Development controls are only available with MARKETPLACE_MODE=mock")
    if not args.tenant:
        parser.error("--tenant is required; register an account first")
    mock = MockMarketplace()
    if args.command == "seed":
        seed_marketplace(args.tenant)
        result = {"synthetic": True, "seeded": True}
    elif args.command == "fault":
        mock.set_fault(args.tenant, FaultScenario.model_validate_json(args.json))
        result = {"synthetic": True, "fault": json.loads(args.json)}
    elif args.command == "configure":
        config = SimulatorConfig.model_validate_json(args.json)
        mock.configure(args.tenant, config)
        result = {"synthetic": True, "configuration": config.model_dump()}
    else:
        if not args.tick_key:
            parser.error("--tick-key is required for repeat-safe outcome advancement")
        result = {"synthetic": True, "outcomes": mock.advance(args.tenant, args.tick_key)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
