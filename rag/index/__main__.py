import argparse
import json

from agent.model import config
from apps.api.db import transaction
from rag.index.corpus import changed, lock_tenant, status
from rag.index.dense import cleanup, sync
from rag.ingest.loaders import rechunk


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild/inspect tenant-owned portfolio indexes; no agent or marketplace work"
    )
    parser.add_argument("command", choices=["status", "rebuild", "cleanup"])
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument("--rechunk", action="store_true")
    args = parser.parse_args()
    if args.command == "rebuild":
        if args.rechunk:
            rechunk(args.tenant)
        with transaction() as db:
            lock_tenant(db, args.tenant)
            changed(db, args.tenant, force=True)
        if not args.lexical_only:
            sync(args.tenant, config()["retrieval"]["embedding_model"])
    elif args.command == "cleanup":
        cleanup(args.tenant)
    print(json.dumps(status(args.tenant), indent=2))


if __name__ == "__main__":
    main()
