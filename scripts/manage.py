import argparse
import asyncio
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="GigBid local commands (no Git or publishing operations)")
    parser.add_argument("command", choices=["migrate", "seed", "dev", "worker", "test", "lint", "eval", "demo", "client", "graphs"])
    parser.add_argument("--tenant")
    args = parser.parse_args()
    if args.command == "migrate":
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    elif args.command == "seed":
        if not args.tenant:
            parser.error("--tenant is required; sign up first or use the UI's Load synthetic examples")
        from dev_support.seed import seed
        seed(args.tenant)
    elif args.command == "dev":
        subprocess.run([sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000"], check=True)
    elif args.command == "worker":
        from worker.__main__ import main as worker_main
        asyncio.run(worker_main())
    elif args.command == "test":
        subprocess.run([sys.executable, "-m", "pytest", "-q"], check=True)
    elif args.command == "lint":
        subprocess.run([sys.executable, "-m", "ruff", "check", "."], check=True)
    elif args.command == "eval":
        from evals.runners.smoke import main as evaluate
        evaluate()
    elif args.command == "demo":
        print("Start API, worker and web; sign up; load labelled synthetic data. See docs/DEMO_SCRIPT.md.")
    elif args.command == "client":
        from scripts.openapi import main as generate
        generate()
    elif args.command == "graphs":
        from scripts.graphs import main as diagrams
        diagrams()


if __name__ == "__main__":
    main()
