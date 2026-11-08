# GigBid

An evidence-grounded freelancer copilot with human approval before outgoing actions.

**Current handoff: Phase 6 local implementation; stopped before Phase 7.** The user
requires explicit instructions before each subsequent phase. Later-phase code
started under the original authorization is preserved but unfinished.

Phase 2 adds typed marketplace contracts, explicit adapter readiness, a durable
synthetic marketplace, deterministic client outcomes, fault controls and tested
idempotent Connects accounting. See the [simulator guide](dev_support/mock_marketplace/README.md).
Official adapter implementations remain unavailable pending verified contracts.
The final checks passed all 54 simulator/foundation/approval compatibility tests and
Ruff. Recorded counts and source/fixture hashes are in [Phase 2 check evidence](docs/checks/phase2.json).

Phase 3 implements three MCP servers with typed tools, portfolio resources/prompts,
authenticated tenant access, approval/idempotency checks, deadlines, rate limits,
redacted audits and role allowlists. All 91 regression tests pass, including real
stdio/HTTP calls and server recovery. See [MCP tool guide](docs/TOOLS.md) and
[Phase 3 evidence](docs/checks/phase3.json). Inspector screenshots and official
integration verification remain pending.

Phase 4 adds structured PDF/Markdown/review/proposal ingestion, source metadata and
hashes, deduplication, incremental replacement/deletion, tenant-scoped BM25/Qdrant
indexes and a versioned V0 dense baseline. See [portfolio data card](docs/DATA_CARD.md)
and [index commands](docs/RUNBOOK.md). Local Qdrant and test-vector lifecycle checks
pass; real Ollama embedding execution and GitHub MCP ingestion remain pending.
The full regression run passed 128 tests; the final Phase 4 subset passed 37
overlapping tests after edge-case fixes. [Phase 4 evidence](docs/checks/phase4.json)
records commands, provenance and limitations.

Phase 5 hardens the durable bid graph, typed parallel handoffs, bounded revisions,
claim verification, persistent human approvals and crash recovery. Approval resumes
require saved human decision receipts; material context changes block execution.
Durable budgets include failed attempts and survive retries. Local crash tests use
the original mock, real checkpoints and explicitly labelled model doubles. Postgres
and real open-model runtime verification remain pending. See the
[graph and approval guide](docs/BID_WORKFLOW.md) and
[Phase 5 evidence](docs/checks/phase5.json). Full regression: 154 passed, one
Postgres skip. Final focused checks: 27 passed, with the same skip; counts overlap.

Phase 6 completes onboarding metadata, saved inbox filters, structured job details,
the evidence-backed studio, paragraph regeneration and persisted live activity.
SSE history/reconnect and inactive approval states use actual backend records.
See the [web workflow guide](docs/WEB_WORKFLOW.md) and
[Phase 6 check evidence](docs/checks/phase6.json) for actual results and limits.

The foundation includes FastAPI, Next.js/TypeScript, multi-user sign-in, tenant-scoped
storage, migrations, generated API types, and visibly labelled synthetic examples.
Local development uses SQLite. Postgres/Redis Compose configuration is provided;
Docker startup has not been verified on this workstation.

Phase 1 checks passed: five foundation tests, Ruff, generated API types, TypeScript
and the production web build. Postgres/Compose execution remains an environment
blocker. See the phase log for exact commands and unfinished later-phase work.

See [local startup and checks](docs/RUNBOOK.md), [phase status](docs/PHASE_STATUS.md),
[requirements](docs/REQUIREMENTS.md), and [missing dependencies](docs/DEPENDENCIES.md).

Official GigSim, persona data, policy update, live accounts, real-model evaluations,
human ratings and public deployment are pending. No official outcomes are claimed.
No commits or external publication actions have been performed.
