import argparse
import asyncio
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="GigBid local commands (no Git or publishing operations)")
    parser.add_argument("command", choices=["migrate", "seed", "dev", "worker", "test", "lint", "eval", "demo", "client",
                                            "graphs", "replay"])
    parser.add_argument("--tenant")
    parser.add_argument("--starter-kit", action="store_true", help="Seed the v0.1 sample data")
    parser.add_argument("--run", help="Run ID for replay")
    parser.add_argument("--node", help="Replay from the latest checkpoint that runs this node next")
    args = parser.parse_args()
    if args.starter_kit and args.command != "seed":
        parser.error("--starter-kit requires seed")
    if args.command == "migrate":
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    elif args.command == "seed":
        if not args.tenant:
            parser.error("--tenant is required; sign up first or use the UI's Load synthetic examples")
        if args.starter_kit:
            from dev_support.starter_kit import seed
        else:
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
        subprocess.run([sys.executable, "-m", "evals.runners.retrieval"], check=True)
        subprocess.run([sys.executable, "-m", "evals.tables"], check=True)
    elif args.command == "demo":
        print("Start API, worker and web; sign up; load labelled synthetic data. See docs/DEMO_SCRIPT.md.")
    elif args.command == "client":
        from scripts.openapi import main as generate
        generate()
    elif args.command == "replay":
        if not args.run:
            parser.error("--run is required; omit --node to list the run's checkpoints")
        from worker.replay import cli
        asyncio.run(cli(args.run, args.node))
    elif args.command == "graphs":
        from scripts.graphs import main as diagrams
        diagrams()


if __name__ == "__main__":
    main()
