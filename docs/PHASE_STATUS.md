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

## Phase 3 - implemented and verified locally; stopped before Phase 4

Scope: the user requested Phase 3 only. Completed the own MCP servers and controlled
tool access, preserving the later-phase stopping rule. No retrieval algorithm,
ingestion feature or graph design was added. Existing workflows were executed only
as compatibility checks.

Implemented:

- Portfolio: typed evidence search/get/skills, stable metadata/passages, JSON case
  and past-proposal resource templates, and two useful versioned prompt templates.
- Marketplace: constrained read/write schemas with output schemas and explicit
  annotations, fixed per-tool action kinds, exact dry-run payload/cost, stable keys,
  approval revalidation and structured error/reconciliation semantics.
- Workspace: real local mock slots, tentative holds and email drafts, exact approval
  and destination validation, tenant transaction locks and idempotent/concurrent
  write protection. No invitation or email send capability was introduced.
- Shared authentication: bearer-protected Streamable HTTP with audience-bound,
  hashed, expiring delegated credentials tied to revocable app sessions; authenticated
  stdio via environment; Host/Origin protection and no HTTP fallback to inherited
  environment credentials. This is not general OAuth or an Upwork integration.
- Shared per-user rate limits and bounded execution; timed-out writes are ambiguous
  and late results are audited. Append-only application audit entries include actor,
  arguments/result hashes, redacted summaries, timestamps and propagated trace IDs.
- MCP client: name allowlists and runtime permission checks, structured artifacts
  preserved, bounded read retries/backoff, Retry-After handling, no automatic write
  retries, independent discovery and fresh sessions after server recovery. Persisted
  observed MCP availability feeds the existing API status/degraded banner.
- Tool/resource/prompt schema snapshots and docs/TOOLS.md, including ownership,
  schemas, annotations, auth, trust rationales and pending third-party integrations.

Final verification:

| Check | Actual outcome |
|---|---|
| `python -m pytest -q --tb=short --junitxml=.cache/phase3-regression.xml` | 91 passed; zero failed/skipped; 127.42 seconds |
| New Phase 3 MCP checks in that run | 29 passed |
| Tool/resource/prompt snapshot and stdio contract checks | 2 passed |
| Other existing compatibility checks | 60 passed |
| Real local TCP HTTP service stop/restart | Passed; failure reported, queued run retained, same gateway recovered |
| Auth audience/expiry/revocation, tenant boundaries, Host/Origin, shared rate limit | Passed |
| Exact approval/changed cost/deleted evidence, concurrent holds, no automatic write retries | Passed |
| Previously failing full-MCP graph compatibility | Now passes after the MCP structured-result fix; models remain labelled test doubles |
| `python -m ruff check .` and `git diff --check` | Passed |
| FastAPI OpenAPI vs existing exported schema | Unchanged; generated frontend contract remains consistent |

The run emitted 13 upstream LangSmith/Python 3.14 deprecation warnings. Counts,
source/snapshot hashes, Git base revision and the uncommitted-work flag are recorded
in `docs/checks/phase3.json`. No real-model quality or official simulator metrics are
claimed. API references and local startup commands are in TOOLS.md.

Outstanding acceptance/evidence: MCP Inspector screenshots remain pending actual
inspection; none were fabricated. Official GigSim/Upwork/GitHub integration checks,
real model execution and Postgres runtime checks remain unverified. General OAuth,
third-party connections, automatic scheduling and later-phase product work were not
introduced. The foundation Compose configuration was not expanded in this phase.

Suggested commit (text only): `feat: implement authenticated MCP servers and controlled tool access`

Stopped at Phase 3. Phase 4 was not started. No commits, pushes, PRs, branches, Git
configuration changes, deployments, publishing or real-account connections occurred.

## Phase 4 - implemented locally; stopped before Phase 5

The user authorized Phase 4 only. Implemented portfolio ingestion and baseline
retrieval without adding graph design, approval-flow features or a subsequent phase.

Implemented:

- Typed loaders for selectable PDF CVs, Markdown/safe frontmatter, UTF-8 text/code,
  JSON reviews and outcome-labelled proposals. Source/page/entry/character metadata
  is inspectable. Blank/scanned, encrypted, malformed and oversized files fail
  before replacing an existing source. Windows line endings are supported.
- Typed tenant/persona/type/project/skills/date/industry/outcome/synthetic metadata;
  raw/document/passage hashes and loader/chunker versions. Original extracted
  sections are retained privately for explicit re-chunking, with latest raw-byte
  provenance preserved even for normalized no-op uploads.
- Content-based deduplication/source aliases, stable unchanged passages, serialized
  concurrent uploads, incremental replacement/deletion, lexical-cache repair, and
  targeted invalidation of approvals citing changed/deleted evidence.
- Persistent tenant-scoped BM25 token records/manifests and a Qdrant cosine V0
  baseline. Vector namespaces use actual model identity/revision and corpus
  fingerprint generations. Search applies tenant/generation/permitted-ID filters
  and rehydrates current SQL passages; removed/stale evidence is never restored.
- Batched real Ollama embedding adapter with digest discovery, dimensional/finite
  checks, version-aware caches and explicit service-unavailable behavior. No
  production fake-embedding fallback was added.
- Lazy vector synchronization on dense retrieval or local rebuild. Source deletion
  hides SQL evidence immediately; unsuccessful physical Qdrant cleanup remains
  durable/pending and can be retried. Local Qdrant operations close within a
  cross-process file lock; remote Qdrant configuration remains supported.
- Structured file-upload metadata and authenticated `/evidence/index`, refreshed
  OpenAPI/TypeScript contract, root test command for the complete suite, index CLI,
  original Markdown/review/proposal fixtures and DATA_CARD.md.
- Explicitly unavailable GitHub MCP ingestion boundary until the integration is
  verified/configured. Manual repository text is labelled as a user upload.

V0 is the default baseline, not an experimentally selected winner. Existing advanced
retrieval variants are preserved for later phases, not claimed as Phase 4 research.

Checks and evidence:

| Check | Actual outcome |
|---|---|
| Full regression suite | 128 passed, zero failed/skipped; about 242 seconds |
| Final Phase 4 subset after final CRLF/raw-provenance fixes | 37 passed, zero failed/skipped; about 24 seconds; overlaps the full suite |
| Real Qdrant local persistence across threads and reopened process | Passed with explicitly labelled test vectors |
| V0 upload/search/get/delete through actual Portfolio MCP protocol | Passed with real Qdrant and labelled test vectors |
| Corpus deduplication, replacement, deletion, aliases, model/cache revisions, stale-publication race and outage cleanup | Passed |
| Generated OpenAPI/client, TypeScript check and production Next build | Passed |
| Ruff, whitespace check, offline lockfile consistency | Passed |
| Real local Ollama `/api/tags` probe | ConnectTimeout; real-model verification remains pending |

The first full compatibility run exposed a regression at the existing MCP
approval-to-submit boundary. Moving unnecessary vector imports behind real vector
operations was followed by a passing focused test and full rerun; graph code and
budgets were not changed. A duplicate test-module filename was also corrected by
namespacing the new test directory. No failed run is presented as passing evidence.

The test invocations emit 13 upstream LangSmith/Python 3.14 deprecation warnings.
Actual command outcomes, timing, source/fixture hashes, Git base and uncommitted-work
status are in `docs/checks/phase4.json`. The final focused subset follows the last
small provenance/line-ending fixes; its counts must not be added to the full suite.

Limits: real open-model embeddings remain unverified because the local service
probe timed out. GitHub MCP ingestion, official persona/evaluation materials and
remote Qdrant/Postgres/Compose runtime checks remain pending. No semantic retrieval
quality, official outcomes or model-cost result is invented. Synthetic fixture
outcomes are authored development labels only.

Suggested commit (text only):

```text
feat: add versioned portfolio ingestion and baseline retrieval

- load PDF CVs, Markdown, reviews, and outcome-labelled proposals with provenance
- add source hashing, deduplication, aliases, and incremental replacement/deletion
- persist tenant-scoped BM25 and Qdrant indexes with corpus/model revisions
- invalidate stale vector caches and approvals that cite affected evidence
- expose upload metadata and index status through the typed API
- add index lifecycle and Portfolio MCP tests with labelled test embeddings
- document data provenance, local index commands, and pending integrations
```

Stopped at Phase 4. Phase 5 was not started. No commits, pushes, PRs, branches,
Git configuration changes, deployments, publishing or real-account connections
were performed. Generated TypeScript build-cache noise was restored to its original
content; generated API types remain updated.

## Phase 5 - implemented locally; stopped before Phase 6

The user explicitly authorized Phase 5 only. Hardened the existing bid graph and
its backend approval boundary; no Phase 6 screens or live streaming were added.
Shared conversation helpers received compatibility changes only. Existing later
phase memory/pipeline features were preserved without adding new capabilities.

Implemented:

- Pydantic analytical handoffs, evidence metadata and finite numeric validation;
  tenant-qualified durable graph threads with synchronous checkpoint persistence.
- Independent Send branches for analyst, risk and matcher, barrier reconciliation,
  deterministic skip/watch/bid decisions, pricing and grounded drafting.
- At most two critic-requested rewrites, each re-verified; human edits/renewal
  cannot reset that allowance. Actual generated diagrams show conditional routes.
- Conservative full-passage claim verification and versioned v2 prompts. Plans and
  questions use a closed grammar; disguised historical claims, partial quotations,
  unsupported screening answers and invented question labels are removed.
- Atomic, durable step/token/active-node-time/API-cost budgets, failed model-attempt
  usage, numeric audit metrics and explicit needs_attention on exhaustion or unknown
  usage. Incomplete reservations after process death are retained as uncertainty;
  retries never reset counters. Reconciliation can confirm an existing effect even
  when new execution is budget-blocked.
- Real persisted approval interrupts, serialized decisions and saved human decision
  receipts checked against interrupt resumes. Context binds tenant/thread, policy,
  profile and raw job in addition to action/version/destination/price/cost/evidence.
  The marketplace transaction rechecks material context before writing or spending.
- Saved tenant-owned edit diffs and complete verification/critique/compliance before
  renewed approval. Renewal versions remain stable across worker restarts.
- Local process locks and Postgres advisory locks for one writer per thread;
  checkpoint-derived stable keys, reconciliation before writes, and saved-result
  validation. Worker failures preserve partial checkpoint state. A secondary event
  feed failure cannot overwrite the completed bid/approval status.
- New adversarial, parallel-resume, revision, budget, model-contract and separate
  worker-process crash tests; workflow/operation guide and explicit check evidence.

Executed checks and exact counts are recorded in `docs/checks/phase5.json`.
The full regression passed 154 tests with one explicit Postgres skip in 311.80
seconds. The final focused checks passed 27 tests with the same Postgres skip in
51.96 seconds. They
include the last screening-label guard. Full regression results are recorded in
the same report; focused counts overlap and must never be added to full counts.
Ruff, whitespace, offline lockfile consistency and OpenAPI export checks passed;
the exported public API schema was unchanged. No frontend code was changed.

The first new handoff test run exposed missing retrieval-ranking metadata in the
typed evidence contract. The contract was corrected and the durability checks then
passed. No failed invocation is presented as passing evidence. Pytest emits 13
upstream LangSmith/Python 3.14 deprecation warnings per invocation.

Limits: real Postgres checkpoint/domain transactions, Docker, real Ollama inference,
hardware/model latency and official integrations remain unverified. The optional
real Postgres restart test is skipped until a disposable service URL is supplied.
Tests use real local graphs/checkpoints/MCP transports where stated, original mock
marketplace effects and labelled model/embedding doubles. No real-model quality,
official outcomes or external exactly-once guarantee is claimed. The deterministic
verifier intentionally restricts free-form prose. See `docs/BID_WORKFLOW.md`.

Suggested commit (text only):

```text
feat: implement durable bid graph with grounded approvals

- validate parallel analyst, risk, fit, pricing, and proposal handoffs
- enforce durable execution budgets and two verified critic revisions
- remove unsupported claims and constrain plan and screening-answer output
- bind persisted human approvals to the exact action and execution context
- save edit diffs and recheck drafts before renewed approval
- reconcile stable action keys across worker crashes without duplicate spending
- add approval security, budget, parallel recovery, and crash regression tests
- document workflow operation and pending Postgres and real-model checks
```

Stopped at Phase 5. Phase 6 was not started. No commits, pushes, branches, PRs,
Git configuration changes, deployments, publications or real-account connections
were performed.

## Phase 6 - implemented and locally verified; stopped before Phase 7

2026-11-08: the user requested completion of Phase 6 only and asked how much remains.
Implemented the core web workflow and actual persisted event streaming. Existing
later-phase pages and services were preserved without adding Phase 7 capabilities.

Implemented:

- Onboarding for persona, fixed/hourly rates, weekly Connects budget, saved search,
  skill/budget/application-cost filters and the configured marketplace. Unavailable
  official integrations are disabled and rejected by profile validation.
- Text/file portfolio uploads with source/type/project/skills/persona/date/industry/
  outcome metadata. Browser refresh retains saved profile and evidence.
- Inbox filtering and fit ranking, risk/action/price/cost information, structured
  job analysis, pricing reasoning and requirement-to-evidence matches.
- Proposal preview/editor, focus/hover evidence passages, claim/Critic/Compliance
  feedback, exact dry-run review, reasoned rejection and safe approval. Unsaved
  edits disable approval and regeneration. Stale reviews show a renewal path.
- Paragraph selection and regeneration, with whole multi-paragraph quotations kept
  intact. Other paragraphs are preserved and verification/Critic/Compliance run
  again before a new approval. Invalid paragraph indices are rejected by the API.
- Typed paginated event history and authenticated SSE with persisted IDs,
  Last-Event-ID replay, de-duplication, reconnect state and revocation/expiry checks.
  Node starts/completions come from actual execution. Public trace links are not
  invented; local trace IDs remain inspectable.
- Responsive layouts, keyboard citations, skip navigation, visible empty/error/
  loading/degraded states and a scrollable desktop sidebar. Workspace caches are
  cleared on sign-out, and old in-flight responses cannot populate a new session.
- Isolated Chrome journeys against the actual local API, Next UI and graph worker,
  plus real HTTP/SSE tests and generated OpenAPI/TypeScript types.

Checks:

| Check | Actual outcome |
|---|---|
| Full Python regression | 160 passed, 1 explicit Postgres skip; 362.51 seconds |
| Core Chrome journeys | 5 passed, no retries or skips; 90.00 seconds |
| Final stale-review/account-switching Chrome journey | 1 passed, no retries or skips; 38.35 seconds |
| TypeScript and optimized Next.js build | Passed |
| Ruff, whitespace and offline lockfile consistency | Passed |
| OpenAPI export and generated client | Regenerated from actual API |
| Desktop studio and 390px mobile inbox screenshots | Captured from exercised flows and visually inspected |

The six browser journeys are distinct; their two runs reflect the final sidebar
correction after the core five passed. Full Python regression is independent of
these browser counts. Source hashes, commands, timings and provenance are recorded
in `docs/checks/phase6.json`. Tests use original mock effects and clearly labelled
model doubles, not real inference or official data. Pytest emits 13 upstream
LangSmith/Python 3.14 deprecation warnings. Next development emitted color-setting
warnings and generated its `apps/web/AGENTS.md` guidance; it remains local.

Browser testing caught selector/assertion assumptions and a genuine sticky-sidebar
overflow that made sign-out unreachable at desktop height. Those were corrected
before the final passing checks. A test-only path initially created disposable
databases one directory above the project; verified synthetic test data were removed
and the harness now confines every test database to the project cache. No failed
invocation is represented as passing evidence. Generated build-cache noise was
restored to its initial bytes.

Limits: real Ollama/model quality, Postgres/Compose runtime, official integrations,
instructor corpora/policy/evaluations and hosted trace links remain pending. Saved
hourly rate is profile input; the current bid graph produces fixed-price proposals.
Only the configured marketplace backend can be selected. No real accounts were
connected and no external publication was performed.

Suggested commit (text only):

```text
feat: add evidence-backed proposal studio and live run viewer

- complete onboarding, metadata uploads, and saved inbox filters
- show structured job analysis, pricing, and inspectable evidence citations
- add cover-letter editing and verified paragraph regeneration
- enforce exact approval, rejection reasons, and inactive-review handling
- stream actual node activity with persisted SSE history and reconnect replay
- improve responsive layouts, keyboard access, and session cache isolation
- add real API/SSE tests and six isolated browser journeys
- regenerate API types and document Phase 6 checks and runtime limits
```

Stopped at Phase 6. Five phases remain: 7 conversations/scheduling/memory;
8 advanced retrieval/experiments; 9 official integrations; 10 reliability/CI/packaging;
11 extension/submission. Partial existing code still needs completion and acceptance.
Phase 9 and parts of the evaluation/reporting work depend on unavailable official
inputs, real model runs and human labels. No next phase was started. No commits,
pushes, branches, PRs, Git configuration changes or publishing were performed.

## Phase 7 - implemented; two real-model issues await the user's decision

2026-11-08: the user authorized Phase 7 with Claude Code. Step 0 (real-model fixes and the
writer/verifier redesign) came first; steps 0c and 1-8 then ran in one pass at the user's
request, with a single commit planned once the phase is complete.

Implemented:

- Real models: Qwen3 thinking off through config, 120 s model request timeout, sentence-level
  claim verification with `[id]` citations, advisory compliance-model warnings, and a separate
  model call for any screening question the writer leaves unanswered.
- Conversations: one durable thread per client conversation (intake, small-model intent
  classification with a rule-based scam override, draft, verifier, compliance, approval, send).
  Each new client message starts the next turn; a message arriving during review cancels that
  review. Interview requests offer free Workspace slots. Compliance blocks prices below the
  user's minimum.
- Events and pipeline: the mock records an event for each client message; the worker reads
  events from a saved cursor, moves pipeline cards forward only, marks proposals awaiting
  review as drafted and queues replies. Mock outcomes advance on a schedule and on demand.
- Scheduling: Celery tasks and beat entries for recovery, scouting, event sync and mock
  outcomes, with matching schedules in the database worker; worker and beat Compose services.
  The scout records duplicate postings instead of analysing them.
- Memory: a LangGraph SQLite/Postgres store with per-tenant style and outcome namespaces, read by
  nodes through `get_store()`. Style rules come from approved text edits only; outcome notes come
  from outcome events by job category. Forgetting is durable. The Critic flags style violations.
- Autonomy and inbox: skip decisions are archived or shown as recommendations depending on the
  setting; any job can be skipped with a reason. Sending always needs approval.
- Analytics by job category, per-proposal token, active-second and API cost percentiles, and top
  rejection reasons. Checkpoint replay through `scripts.manage replay` and the API. The previously
  empty Agent runs screen now shows activity and checkpoints with Replay buttons.
- `stage_approval` now reuses only a still-pending approval; before, an identical replayed
  preview could pick up an approval that was already consumed.

Checks:

| Check | Actual outcome |
|---|---|
| Full Python regression | 177 passed, 1 Postgres skip (54.7 s) |
| Playwright journeys in installed Chrome | 9 passed: 6 existing and 3 new (client reply with slots, forgetting memory, inbox skip) |
| Ruff, TypeScript check, production build | Passed |
| OpenAPI export and generated client; MCP schema snapshot | Regenerated; the snapshot change is the new `received` event status |

Real-model runs (Ollama 0.40.15, Apple M3 24 GB, qwen3:4b and qwen3:8b, mock marketplace, V0):

| Run | Actual outcome |
|---|---|
| Before step 0, code as committed | needs_attention after 92 s; all four model attempts timed out in thinking mode |
| Before step 0, thinking disabled in the test driver | blocked; all three drafts removed by the closed grammar |
| Step 0 with advisory compliance | proposal reached approval, approved and submitted once; Connects 100 -> 92 |
| Step 0 after the timeout change | blocked: the writer left screening answers empty in all three drafts |
| Phase 7, proposal and reply | proposal needs_attention at the 180 s active budget; reply failed because `intent.v1.md` was missing (added, with a test that every node has a prompt) |
| Phase 7, second run | proposal needs_attention at 14,498 of 12,000 tokens after two rewrites, because its screening answer was removed as partly supported each time; reply failed at the MCP preview on an empty approval id (fixed, with an MCP-level test) and its slot sentence was removed (fixed) |

Celery and Redis check (Redis 8.10.3, `--pool=solo`, real models, the dashboard job): the worker
was killed with SIGKILL 22.6 s in, after intake, analyst, risk, matcher, reconcile and pricing had
completed and the writer had started. After the 300 s lease the recovery task resumed the run at
338 s. No completed node ran again and nothing was submitted or spent. The run then stopped as
needs_attention: the killed writer's token usage is unknown, the existing budget rule blocks
further generation, and Retry cannot clear it.

Open issues awaiting the user:

1. Screening answers: qwen3:8b writes one sentence that mixes a plan with a past-work claim; the
   verifier removes it as partly supported, the Critic asks again, and two rewrites exceed the
   token budget. Proposed fix: screening answers are plans only, and evidence claims stay in the
   cover letter.
2. Interrupted model calls: a run killed mid-call can never continue. Proposed fix: Retry records
   a human acknowledgement of the unknown usage and continues within the remaining budget.

Known benign warning: LangGraph's async SQLite store can log "Task was destroyed but it is
pending" when a run's store closes. No commits, pushes, branches, PRs or publication occurred.

## Real-model fixes and hosted open models - implemented and verified

2026-11-08: after the Phase 7 commit the user supplied a Groq API key and asked for the 11
fixes from the real-model review, with hosted open-weight models from now on and everything
else local. Both open Phase 7 issues are closed (fixes 1 and 2).

Implemented:

1. Screening answers are plans only ("I would ..."), from writer v4 and answer v2; evidence
   claims stay in the cover letter.
2. Retry on a run stopped by unknown usage records the user's acknowledgement (nodes and time)
   in the budget ledger and continues within the remaining budget. The studio explains this.
3. Evidence sent to models is trimmed to id, text, project, skills, date and outcome.
4. Per-node output caps in each profile; the local profile keeps Ollama models loaded (`keep_alive`).
5. Budgets were re-measured on hosted runs; no change was needed (below).
6. Risk flags come from a fixed list. Planted instructions raise risk to at least 0.5
   (`thresholds.injection_risk`) so the reviewer sees them, without forcing a skip.
7. Each model falls back to a different real model: gpt-oss-120b and gpt-oss-20b back each
   other up; locally qwen3:8b -> qwen3:4b -> qwen3:1.7b.
8. Marketplace job and client IDs are removed from every model input.
9. Pricing receives computed facts (budget, minimum bid, Connects cost, balance and weekly
   allowance, category outcomes) and returns an amount within them with a one-sentence rationale.
10. `make smoke` (`scripts/smoke.py`) runs approved proposals and replies with the configured
    models on a throwaway database and writes `evals/results/smoke-<time>.json`.
11. `MODEL_PROFILE=open` (the default) calls Groq's OpenAI-compatible API in JSON mode:
    gpt-oss-20b for the small nodes and gpt-oss-120b for the writer, Critic and liaison, with API
    cost from published prices. `open_local` keeps Ollama. Embeddings stay local
    (`nomic-embed-text`). The key is kept only in the git-ignored `.env`.

Usage rule: a rate-limited (429) or rejected (other 4xx) request generated nothing, so it counts
as known zero usage and the fallback model runs; a rate limit waits at most 10 s first. Timeouts
and 5xx responses leave usage unknown, which stops the run until Retry.

Checks:

| Check | Actual outcome |
|---|---|
| Full Python regression | 185 passed, 1 Postgres skip (48.7 s) |
| Playwright journeys in installed Chrome | 9 passed (58.7 s) |
| Ruff, TypeScript check, production build | Passed |

Hosted runs (Groq, mock marketplace, V0 retrieval with local `nomic-embed-text`, Apple M3 24 GB):

| Run | Actual outcome |
|---|---|
| Baseline before trimming and ID removal (`make smoke`) | proposal submitted, reply sent; proposal 6,478 tokens with a 1,931-token writer prompt; the injected job reached review |
| After all fixes (`make smoke RUNS=3`) | 3/3 proposals submitted once, 3/3 replies sent; per proposal p50/p95 5,438/5,583 tokens, 14.5/14.7 active s, $0.00096/$0.00097; writer prompt about 1,180 tokens (-39%); scam and injected jobs skipped |
| Forced fallback (unknown primary model name) | 404, then gpt-oss-120b answered; usage complete, $0.00015 |
| Celery kill and Retry (Redis, `--pool=solo`, mock-web) | killed 9.0 s in, during the writer; recovered at 334 s as needs_attention; Retry recorded the acknowledgement for `writer`; only the writer ran again; approved and submitted once (Connects 100 -> 90) |

At p95 a proposal uses 47% of the 12,000-token budget, 8% of the 180 s active budget and about
1% of the $0.10 API budget, so budgets stay unchanged. Results are in
`evals/results/smoke-20261108-193512.json` and `smoke-20261108-193808.json`; commands, hashes
and details are in `docs/checks/real-model-fixes.json`.

Limits: Groq free-tier rate limits apply; the local qwen3:1.7b fallback was not pulled or run;
hosted output varies between runs, and the injected job was skipped by the model's own risk
score. Nothing was committed at check time; no push, branch, PR or publication.

## Quality review of hosted outputs - fixed and verified

2026-11-08: reading the actual drafts and sent messages, not just the pass count, showed problems
the smoke check had missed, plus four places that differed from the assignment PDF. The user
asked to fix them for the hosted models only; local-model behaviour and choosing the best models
come at the end.

Found in the hosted runs: one sent reply asked the client to pick "from the following interview
slots" with no slots (the claim checker removed the slot list); two of three bids were the $50
minimum on a $900 job; plan sentences with curly apostrophes ("I’d", "I’m") were removed as
claims; one proposal kept no evidence at all and another kept an orphaned "This work was
delivered..." sentence. PDF differences: plan-only screening answers (the PDF asks for evidence
citations), pricing without client spend or a Connects decision, a hard-coded risk-flag list, and
a Compose file that could not run the models.

Implemented:

- Interview times are added to the reply by code from the calendar tool when the action is built,
  so the approval preview and the sent message always list them; liaison v4 never writes times.
- The claim checker reads curly quotes and non-breaking hyphens as plain text, treats a plan that
  names a portfolio project or says "as demonstrated in" as a claim that needs a citation, and
  removes a "This/That/It..." sentence that follows a removed one.
- The Critic sends back a model draft whose cover letter cites no evidence, quoting up to two
  removed sentences and why; human edits and regenerated paragraphs are reviewed as written.
  Writer v5 and answer v3 reuse the evidence's own wording.
- Screening answers cite evidence for experience questions and use "I would" plans otherwise; the
  mock API job now also asks "Describe a similar API you have delivered."
- Pricing gets the client's total spend, hires and average paid per hire, and code keeps the bid
  within 60-100% of the job budget (`pricing.budget_share`, never below the floor). When fit x bid
  is below Connects x $0.15 x 20 (`pricing.connect_usd`, `pricing.min_return`) the run stops as
  "watch" with the reason. Market statistics wait for GigSim's historical jobs.
- Risk flags are validated against `policy.risk_flags` in config and passed to the risk model.
- The Groq JSON instruction moved to `agent/prompts/json_mode.v1.md`.
- Compose passes `MODEL_PROFILE`, `GROQ_API_KEY` and `OLLAMA_URL` to the API, worker and beat and
  adds an `ollama` service that pulls `nomic-embed-text`.
- `make smoke` reports cited sentences, bid share, unanswered questions and whether the interview
  times reached the reply, with a warning for each problem.

Checks:

| Check | Actual outcome |
|---|---|
| Full Python regression | 193 passed, 1 Postgres skip (50.1 s) |
| Playwright journeys in installed Chrome | 9 passed (58.8 s) |
| Ruff, TypeScript check, production build | Passed |
| `docker compose config` with dummy values | Valid; model settings reach api, worker, beat and migrate |

Hosted runs (`make smoke RUNS=3`):

| Run | Actual outcome |
|---|---|
| First run with the new rules (`smoke-20261108-214105.json`) | 2/3 proposals submitted; the second hit the token budget (12,150 of 12,000) after two rewrites, because the writer embellished its evidence sentences ("a full suite of integration tests") and the Critic's note did not say what was removed |
| After the wording and feedback fix (`smoke-20261108-214552.json`) | 3/3 submitted with no rewrites, 3/3 replies with the interview times, 0 quality warnings; but every price reason read the client's $4,000 total as "per hire" |
| After renaming the client fields (`smoke-20261108-214840.json`) | 3/3 submitted with no rewrites, 3/3 replies with the interview times, 0 quality warnings; p50/p95 6,105/6,324 tokens, 15.4/15.7 active s, $0.0011/$0.0012; bid $850 (94% of budget) with the reason "near the top of the 540-900 range ... despite the client's average paid per hire of 500" |

Deferred by the user: choosing models by measurement at the end (with the smoke quality fields as
the yardstick), local-only failures, an extra layer that strips injected sentences from model
input, and moving the rule-based safety patterns into config. Nothing was committed at check
time; no push, branch, PR or publication.

## Partly-done items: Compose on Postgres, GitHub import, layout - done and verified

2026-11-08: the starter kit is not available yet, so the user asked to finish the partly-done
items first, then Phase 8, then Phase 10.

Implemented:

- Compose runs the whole stack: Postgres, Redis, a shared `qdrant` store, `ollama` for the
  embeddings, the three MCP servers as HTTP services that check audience-bound bearer tokens,
  migrations, the API, the Celery worker and beat, and the web app. Before this, the API and
  worker would each have kept their own vector index inside their containers.
- GitHub repository import through GitHub's official MCP server (`rag/ingest/github.py`,
  `POST /evidence/github`, a Settings form): read-only repos toolset, only `get_repository_tree` and
  `get_file_contents`, the README plus up to 12 source files as `repository` evidence.
- Playwright specs moved to `apps/web/tests/e2e/`, the path the PDF lists.

Checks:

| Check | Actual outcome |
|---|---|
| Full Python regression | 196 passed, 1 skip (the Postgres test, run separately below) |
| Postgres checkpoint test against Compose Postgres | 19 durability tests passed, including the previously skipped one |
| Playwright journeys from `apps/web/tests/e2e/` | 9 passed |
| Ruff, TypeScript check, image builds (including the production web build) | Passed; 8 images built in about 12 minutes |
| `docker compose up` | 13 services: 11 running, migrations and the embedding-model pull exited 0 |
| End to end through the HTTP API | proposal reached approval in 6.2 s with 5 evidence items and an $850 bid; MCP servers healthy over HTTP; 44 checkpoints in Postgres; one shared Qdrant collection |
| C6 crash demo | API killed while the proposal awaited approval, restarted, approved: submitted exactly once (1 proposal record, Connects 100 -> 92) |
| Client reply on the stack | sent, with the interview times listed |
| Hosted smoke (`smoke-20261108-230027.json`) | 1/1 submitted, reply sent, 0 quality warnings; one Critic rewrite for a brief screening answer (9,392 tokens) |
| GitHub import, live (`muhammad-moiz-ansari/pakrail-remastered`) | the server offered only the two named tools; README plus 11 source files from `src/`, 167 passages in 25 s, all `repository` evidence with real file text |

Upwork: the user has an account. Upwork's MCP page (updated 6 Nov) says any MCP app may connect
with OAuth 2.1 and dynamic client registration, and that API keys are not accepted. It also says
callback addresses for apps on a server or website need Support approval, and that agents should not
rank, score or pick jobs by their own criteria.

Upwork sign-in (`apps/api/auth/upwork.py`, Settings -> Connect Upwork): OAuth 2.1 with PKCE (S256)
and dynamic client registration; Upwork accepted the localhost callback, the user signed in on
Upwork's page, and the tokens are stored encrypted per user (`apps/api/auth/tokens.py`). Check
connection opened an MCP session with the user's token and listed 33 tools, including `find_jobs`,
`get_messages`, `manage_proposals`, `get_preview`/`confirm_preview` and `send_message`
(`docs/checks/upwork-signin.json`). A deployed callback address would still need Upwork Support approval.

Upwork adapter (`mcp_servers/marketplace/adapters/upwork_live.py`, `MARKETPLACE_MODE=upwork`): the port maps
onto `find_jobs` (search, recommendations, details with the real Connects cost), `get_profile` (Connects),
`get_messages`, `list_freelancer_proposals` (pipeline events) and two writes. A proposal becomes an Upwork
draft (`manage_proposals create`) only after an approved, unconsumed GigBid approval, and Upwork spends
Connects when the user confirms it there; a message is sent with `send_message` after approval. Any
other tool is refused in code. A write is recorded as in flight first, so an unknown outcome is never
retried. The shared approval check now takes the live job instead of a mock-only record.

Upwork's live-mode rules: the inbox keeps Upwork's order and never auto-archives; outcomes from Upwork
events are not learned (terms 8.6); search details are cached for at most 24 hours (8.3); live runs,
their checkpoints and Upwork records are purged after 30 days and on disconnect (8.6, 8.7).

| Check | Actual outcome |
|---|---|
| Adapter tests with a stand-in Upwork server | 5 passed: reads, draft-only proposal behind an approval, refused vs unknown writes, purge, unranked live inbox |
| Live reads on the user's account | search 10 jobs (9 with skills), recommendations 10, job details with Connects cost 10, client history, balance, events (none yet); a forbidden tool refused |
| Full Python regression | 206 passed, 1 Postgres skip |

Live write check (2026-11-09, the user's throwaway account, authorized in chat): Upwork first refused
the draft until the account acknowledged its payment policy; the user confirmed "I understand Upwork's
policies" in chat and the acknowledgement was recorded. Upwork then answered with a next step instead
of a draft (`terms_required`: fixed-price drafts need a duration and a payment mode), which the adapter
had wrongly reported as drafted. With the terms sent, Upwork refused because the account has 0 Connects
and the job costs 10; Upwork checks the balance even for an unsubmitted draft. Fixes: a reply without a
preview id is a refusal that shows Upwork's next step; fixed-price drafts carry the job's posted duration
(or `upwork.default_duration`) and `upwork.payment_mode` (by project), shown in the approval preview through
a new `terms` field on write results; hourly jobs are refused clearly; Upwork's refusal text is no longer
cut at 200 characters; and Settings has an "I understand Upwork's policies" step for new accounts. GigBid's
pricing node already stops a run when Connects are short, so a real run never reaches that refusal.

Still not verified live: a built draft and its preview format (the account needs Connects), message
sends (no conversation exists and starting one would message a stranger) and the proposal and message
event formats (no proposals or messages yet).

The live GitHub import caught two problems that the stand-in tests could not: with the
`/x/repos/readonly` URL GitHub ignored `X-MCP-Tools` and offered 14 tools (the `/readonly` URL
honours it), and the shallowest-first file order imported a generated `next-env.d.ts` and helper
scripts instead of the app's `src/` code. Both are fixed and the import was rerun.
Nothing was committed at check time; no push, branch, PR or publication.
