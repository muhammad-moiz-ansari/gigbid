# GigBid Portfolio MCP Server

The Portfolio MCP server exposes evidence search, case studies, skills, and portfolio resources for a GigBid workspace. It retrieves records for the authenticated account. The server shares GigBid’s data model and migrations.

## Install from the public repository

Build and install from a checkout of the submitted revision. Run the commands from the repository root with Python 3.12–3.14 and uv available.

```sh
uv sync --frozen
uv run python -m alembic upgrade head
uv run gigbid-portfolio
```

The last command starts stdio. An MCP client can use the same command with the repository root as its working directory. The equivalent module command is `uv run python -m mcp_servers.portfolio.server`.

For an installable wheel, run `uv run python -m build --wheel` and install the resulting wheel with `uv pip install DIST_WHEEL` in a Python virtual environment. The wheel includes the server command, code and packaged prompts. Use the repository checkout for migrations and local fixtures.

The published repository also serves as a package source for `uvx`. Run this
after provisioning the database and setting the connection and MCP credentials
in your environment. Replace `COMMIT_SHA` with the submitted Git revision.

```sh
uvx --from "git+https://github.com/muhammad-moiz-ansari/gigbid.git@COMMIT_SHA" gigbid-portfolio
```

## Connect it to a workspace

1. Point the server and API at the same `DATABASE_URL`. Run migrations in the checkout.
2. Create and sign in to a GigBid account, then upload evidence in **Settings**.
3. Use GigBid’s MCP gateway for an authenticated session. A standalone stdio client needs a valid GigBid session token supplied privately as `GIGBID_MCP_TOKEN`. The HTTP transport uses a resource-bound credential issued by GigBid. Keep tokens out of client configuration shared publicly.
4. Use `RETRIEVAL_VARIANT=BM25` for lexical search, or configure Ollama and Qdrant for V2. The API, worker and Portfolio MCP service need compatible retrieval settings.

The checkout also provides a Docker build path through `infra/docker/api.Dockerfile` and the `portfolio-mcp` service in `infra/docker-compose.yml`. See the [MCP configuration and tool reference](../../docs/TOOLS.md) and [runbook](../../docs/RUNBOOK.md) for transport, setup and health checks.

