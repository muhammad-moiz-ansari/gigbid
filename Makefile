.PHONY: dev migrate test seed demo lint client smoke
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
