# Phase 1 local startup

The user requires one explicitly requested phase at a time. Phase 3 is the
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

Do not run the worker or further-phase evaluation/deployment commands until the user
explicitly requests that phase. No commits, pushes, branches, PRs or publications.

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
