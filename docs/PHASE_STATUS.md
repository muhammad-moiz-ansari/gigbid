# Phase log

## Phase 0

Read both assignment sources and the implementation plan; inspected the clean, nearly
empty repository and applicable instruction locations. Defined contracts, provisional
budgets, requirements and missing-dependency register. No Git state was changed.

Checks: source files read; `git status --short` initially empty. Python 3.14.3,
Node 24.19.0 and uv 0.10.5 available. Docker and Poppler CLI unavailable.

Suggested commit: `docs: define assignment requirements and implementation constraints`

Subsequent phases must record actual check outcomes and distinguish implemented code
from executed acceptance checks. Partial phases are not marked complete.

## Phase 1 - local foundation finished; stopped at user instruction

The user superseded the original continue-through-phases instruction on 2026-11-07.
Finish Phase 1, then stop. Every later phase now requires an explicit user request.
See WORKING_AGREEMENT.md.

Implemented foundation:

- FastAPI and Next.js/TypeScript applications, validated environment configuration,
  pinned Python dependencies with uv.lock and frontend package-lock.json.
- SQLAlchemy tenant-scoped users, sessions, domain documents, runs, events and
  approvals; initial Alembic migration. Domain documents currently hold profiles,
  jobs, proposals/messages and memory as tenant-scoped JSON records.
- Argon2 password hashing, hashed opaque expiring sessions, logout revocation,
  HttpOnly/SameSite cookies, origin and CSRF checks, CORS and rate-limited sign-in.
- Health and database readiness, JSON request log messages with redaction, trace IDs.
- OpenAPI export and generated TypeScript schema used by an openapi-fetch client.
- Original synthetic seeding with tenant separation and visible UI labelling.
- Foundation Dockerfiles/Compose for Postgres, Redis, migrations, API and web.
- Startup commands, Windows equivalents and limits in RUNBOOK.md; root Makefile.

Executed checks on the final Phase 1 handoff:

| Command/check | Actual outcome |
|---|---|
| `python -m pytest tests/unit/test_auth.py tests/unit/test_foundation.py -q` | 5 passed; 13 third-party Python 3.14 deprecation warnings; 6.88 seconds |
| Clean SQLite Alembic upgrade followed by repeated upgrade | Passed within foundation tests |
| Auth/CSRF, two-user isolation, logout, health/readiness, cookie flags, repeatable seed, saved profile | Passed within foundation tests |
| `python -m scripts.openapi` and `npm run generate` | Passed; client schema generated from actual API |
| `npm run typecheck` | Passed |
| `npm run build` | Passed; Windows uses normal Next output, Linux Docker uses standalone |
| `python -m ruff check .` | Passed |
| Foundation Compose YAML parse / service inventory | Passed; five services, not a runtime check |
| `git diff --check` | Passed; Git noted its existing LF/CRLF behavior for README |

Postgres migrations and full Compose startup are **not verified**: Docker is not
installed. SQLite is a documented local deviation, not proof of Postgres behavior.
No real-model inference, public deployment or official integration was verified.

Before the user's stop instruction, the earlier authorization had already led to
partial code for marketplace/MCP, retrieval, graphs, worker, memory and workflow UI.
Those files are preserved and **not accepted as completed phases**. The most recent
broader pre-stop run had 14 passing tests and one failing full-MCP graph test. That
failure is outside Phase 1; it was deliberately not investigated or fixed after the
scope change. No browser journeys were run. A previously started Chromium download
was interrupted when finishing this narrowed scope.

Suggested commit (text only): `feat: add application foundation and tenant authentication`

Stopped. No next phase is authorized until the user explicitly names it. No commits,
pushes, PRs, branches, Git configuration changes, deployment or publication occurred.

## Phase 2 - complete locally; stopped before Phase 3

The user explicitly requested Phase 2 only. Implemented and verified the shared
marketplace interface and original development simulator without starting the next
phase. Previously written MCP, graph and UI implementation files were not extended.
Existing approval tests were run only as compatibility checks for the changed port.

Implemented:

- Typed shared operations for jobs/search, client histories, Connects balances,
  proposal inspection, messages/conversations, events, writes and reconciliation.
  Explicit capability flags and readiness separate mock support from unavailable
  official integrations. Removed dynamic catch-all adapter methods.
- Original mock proposals, approved drafts/messages, Connects accounting, owned
  conversations and append-only proposal/message events with increasing cursors.
  No simulator implementation or fixtures were put under `gigsim/`.
- A duplicate-posting fixture alongside scams, planted injection and unmatched jobs;
  original client/config fixtures; re-seeding preserves existing account/state.
- Configurable hash-based reply/interview/hire outcomes, captured configuration per
  proposal, synthetic inbound messages, terminal lost handling and idempotent ticks.
- Durable operation-scoped faults: outage, 429/retry-after, 503, immediate synthetic
  timeout and ambiguous postcommit write response, with bounded or persistent plans.
- Transactional write deduplication, conflicting-key rejection, safe retry after job
  deletion/cost changes, same-job duplicate submission prevention, weekly budget
  rollover, rollback recovery, and no approval/dry-run spending bypass.
- Local CLI controls and simulator guide. Official GigSim/Upwork calls remain
  explicitly unavailable; no guessed HTTP mappings or account access were added.

Final checks:

| Check | Actual outcome |
|---|---|
| Phase 2 tests + existing foundation/auth/approval compatibility command in `docs/checks/phase2.json` | 54 passed, zero failed/skipped, 31.47 seconds |
| Phase 2 simulator tests within that run | 44 passed, separated under `tests/mock_marketplace/` |
| Existing foundation/auth/approval compatibility | 10 passed; no later-phase implementation added |
| CLI status for mock/GigSim/Upwork, official-mode mutation refusal | Passed within simulator tests |
| Concurrent identical writes/ticks, new-process reconciliation, rollback and ambiguous writes | Passed within simulator tests |
| `python -m ruff check .` | Passed |
| `git diff --check` | Passed after normalizing the service file's trailing newline |

The run emitted 13 upstream LangSmith/Python 3.14 deprecation warnings. Test counts,
fixture hashes, tested-source hashes, Git base revision and the uncommitted-work flag
are recorded in `docs/checks/phase2.json`. All outcomes are original synthetic
development outcomes, never official GigSim metrics or real-model results.

Limits: Postgres locking has code support but was not runtime-tested because Docker
is unavailable. Official GigSim schemas/services and live Upwork authorization remain
missing. The previously documented full-MCP graph failure remains outside this phase.
MCP service work, advanced UI controls and automatic scouting/outcome polling await
their explicitly requested phases.

Suggested commit (text only): `feat: add marketplace interface and deterministic development simulator`

Stopped at Phase 2. Phase 3 was not started. No commits, pushes, PRs, branches,
Git configuration changes, deployments or publication actions were performed.
