# Phase 1 local startup

The user requires one explicitly requested phase at a time. Phase 6 is the
current stopping point. Code written for later phases before that instruction is
preserved, unfinished and not a claim of acceptance.

Prerequisites: Python 3.12-3.14, uv, Node.js 24 and npm. GNU Make is optional on
Windows; equivalent PowerShell commands follow. No secrets are embedded in the repo.

From the project root:

```powershell
uv sync --frozen
uv run python -m alembic upgrade head
uv run python -m scripts.manage dev
```

In a second terminal:

```powershell
cd apps/web
npm ci
npm run dev
```

Open http://localhost:3000 (use this origin for the configured CSRF check). Register
an account with a password of at least 12 characters. The mock mode is labelled in
the UI. In Settings select **Load synthetic examples**, or sign in and invoke the
CSRF-protected `/dev/seed` endpoint. The seed command also accepts an existing user
ID: `uv run python -m scripts.manage seed --tenant USER_ID`.

Phase 1 checks:

```powershell
uv run python -m pytest tests/unit/test_auth.py tests/unit/test_foundation.py -q
uv run python -m ruff check .
uv run python -m scripts.openapi
cd apps/web
npm run generate
npm run typecheck
npm run build
```

The TypeScript schema is generated from FastAPI OpenAPI; never hand-edit
`src/lib/api/schema.d.ts`. The small client wrapper uses openapi-fetch with these
generated paths and adds the in-memory CSRF token.

Optional foundation Compose (not executed here; Docker is unavailable):

```powershell
$env:POSTGRES_PASSWORD = 'choose-a-local-password'
docker compose -f infra/docker-compose.yml up --build
```

Use a URL-safe password for the connection string. This Phase 1 Compose starts
Postgres, Redis, migrations, API and web only. Worker, models, MCP HTTP services and
vector/tracing infrastructure belong to later phases and are not operationally
verified. Postgres acceptance remains pending a Docker-enabled environment.

Auth uses Argon2 password hashes, random opaque session tokens stored as SHA-256
hashes, expiry/revocation, HttpOnly SameSite cookies, exact-origin CSRF checks and
restricted CORS. `COOKIE_SECURE=false` is for local HTTP only; use true behind HTTPS.
Logs omit request bodies and sensitive paths. Health is `/health`; database readiness
is `/ready`. Readiness does not claim external integrations or models are ready.

On this workstation the sandbox blocked Windows asyncio's local socketpair setup.
API/protocol tests required execution with local loopback permission. This is an
environment constraint, not a test failure in the application.

Phase 6 UI and worker verification are authorized locally. Further-phase evaluations,
deployment and feature implementation still require a new explicit request.
No commits, pushes, branches, PRs or publications.

Phase 2 simulator-only commands and checks are documented in
`dev_support/mock_marketplace/README.md`. They do not start the Phase 3 MCP layer or
later graph/worker workflows. The foundation Compose file remains unchanged.

Phase 3 MCP startup, credentials, tool schemas, roles, recovery and checks are in
`docs/TOOLS.md`. Standalone HTTP processes bind to loopback by default and need the
configured database. The gateway delegates resource-bound bearer credentials from
the existing app session; do not expose or print them. New MCP deadline/bind/host
variables are documented in `.env.example`.

`/status` now includes timestamped tenant-scoped MCP observations. Once discovery or
a call observes a stopped marketplace server, the existing degraded banner reports
it. Queue records remain; restore the service and retry. Status is last observed
state, not a continuous independent probe. Phase 3 does not change the foundation
Compose file or start Phase 4. Inspector screenshots remain pending.

## Phase 4 portfolio ingestion and indexes

Text uploads retain the existing `/evidence` API. `/evidence/file` now parses PDF,
Markdown, UTF-8 text/code and structured JSON reviews/proposals, with an optional
multipart `metadata` JSON object. It preserves typed metadata and page/entry/text
locations instead of treating every file as a CV. `/evidence/index` reports the
authenticated user's source/corpus/index manifests and pending physical cleanup.
The generated frontend schema was refreshed; no new screen or graph was added.

Default retrieval is V0, the fixed-chunk dense baseline, pending future evaluation.
It requires the configured open Ollama embedding model. This workstation's real
Ollama probe timed out; test vectors do not substitute for a real-model smoke check.
Initialize the service/model in your own environment before requesting V0 retrieval:

```powershell
ollama pull nomic-embed-text
```

For explicit lexical development, set `RETRIEVAL_VARIANT=BM25`. This is diagnostic
lexical retrieval, not a claim that mandatory dense V0 ran. Qdrant defaults to local
persistence under `data/processed/qdrant`; operations are file-locked across stdio
processes. Set `QDRANT_MODE=server` and `QDRANT_URL` to use an actual server. The
foundation Compose stack has not been expanded or verified for that service.

From the root, after registration/upload, replace USER_ID with the authenticated
user ID. These commands do not run an agent, worker or marketplace action:

```powershell
uv run python -m rag.index status --tenant USER_ID
uv run python -m rag.index rebuild --tenant USER_ID --lexical-only
uv run python -m rag.index rebuild --tenant USER_ID
uv run python -m rag.index cleanup --tenant USER_ID
# Explicitly re-chunk saved extracted sections after changing chunk configuration:
uv run python -m rag.index rebuild --tenant USER_ID --rechunk --lexical-only
```

Uploads immediately update canonical SQL evidence/BM25 and mark changed vector
generations pending. The next dense search or rebuild synchronizes new/changed
vectors. Deletion hides evidence immediately, removes retained extracted source
text and invalidates affected approvals; interrupted physical vector cleanup stays
pending and can be retried. Source aliases preserve evidence until its final owner
is deleted. Older pre-Phase-4 sources without retained sections need re-upload before
re-chunking; original text is never reconstructed by guessing.

The expanded synthetic seed includes original Markdown, review and proposal fixtures.
See DATA_CARD.md for supported formats/provenance and the Phase 4 check report for
actual verification. GitHub MCP repository ingestion remains explicitly unavailable.

```powershell
uv run python -m pytest tests/rag -q
uv run python -m pytest -q
uv run python -m ruff check .
```

## Phase 7 worker, schedules and replay

Real generation needs Ollama with the configured models. `agent/config.yaml` sets
`generation.think: false` for Qwen3, and the per-request model timeout defaults to
120 seconds (`MODEL_TIMEOUT_SECONDS`).

```bash
ollama pull qwen3:4b
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

Both worker modes use the same idempotent run processing:

- `QUEUE_MODE=database` (default): `uv run python -m scripts.manage worker` drains queued
  runs and also runs the saved-search scout, marketplace event sync and, in mock mode,
  simulated client outcomes, each on its own schedule.
- `QUEUE_MODE=celery` with Redis at `REDIS_URL`: the API dispatches runs to Celery and the
  beat scheduler runs recovery every 30 s plus scouting, event sync and mock outcomes on
  60 s ticks, each gated by its own per-user interval. Compose starts `worker` and `beat`.

```bash
redis-server --port 6379 --save "" --appendonly no
QUEUE_MODE=celery uv run celery -A worker.tasks worker --loglevel=info
QUEUE_MODE=celery uv run celery -A worker.tasks beat --loglevel=info
```

The local macOS check used `--pool=solo`; Compose uses Celery's default pool.

Schedules live in `agent/config.yaml` under `scheduling`. A saved search runs no more often
than its profile interval, and never more often than every 5 minutes in mock mode or every
4 hours in live mode. Four hours keeps live reads far from anything resembling scraping
(Upwork forbids scraping and unapproved bots) while still catching new postings the same
day. Event sync runs every 60 s and mock outcomes advance every 120 s. A worker killed
mid-run leaves the run leased for 300 s; the recovery task then resumes it from its last
checkpoint, so finished nodes do not run again and stable action keys prevent a second
submission. The scout skips postings it has seen and marks duplicate postings (same title,
description and client under another ID) without analysing them.

Replay a run from a saved checkpoint as a new branch (an operator and debugging tool):

```bash
uv run python -m scripts.manage replay --run RUN_ID
uv run python -m scripts.manage replay --run RUN_ID --node writer
```

The first command lists checkpoints; the second queues a replay from the latest checkpoint
that runs `writer` next. The run viewer at `/runs/RUN_ID` lists the same checkpoints with
Replay buttons. A replay gets a fresh budget and must be approved again before any send.
