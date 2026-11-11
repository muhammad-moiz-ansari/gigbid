.PHONY: dev migrate test seed demo lint client smoke eval eval-all tables
dev:
	uv run python -m scripts.manage dev
migrate:
	uv run python -m scripts.manage migrate
test:
	uv run python -m pytest -q
seed:
	uv run python -m scripts.manage seed --tenant $(TENANT)
demo:
	uv run python -m scripts.manage demo
lint:
	uv run python -m ruff check .
client:
	uv run python -m scripts.openapi
	cd apps/web && npm run generate
smoke:
	uv run python -m scripts.smoke --runs $(or $(RUNS),1)
# One study per call (retrieval needs no tokens), then every results table: make eval STUDY=decisions ARGS="--subset proposals"
eval:
	uv run --extra rerank --extra eval python -m evals.runners.$(or $(STUDY),retrieval) $(ARGS)
	uv run python -m evals.tables
tables:
	uv run python -m evals.tables
# Final run of every token-using study; each step resumes where a quota stop left it, so rerun it after a reset.
eval-all:
	uv run python -m evals.runners.decisions
	uv run --extra eval python -m evals.runners.architecture --design react
	uv run --extra eval python -m evals.runners.architecture --design supervisor
	uv run python -m evals.runners.tools
	uv run python -m evals.runners.judge --sheet
	uv run python -m evals.tables
