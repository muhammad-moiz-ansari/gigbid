# Development marketplace (Phase 2)

This is an original synthetic simulator, **not instructor GigSim**. No marketplace
account or external network service is contacted. Official files remain reserved for
`gigsim/`; fixtures live in `dev_support/fixtures/`.

## Port and adapter boundaries

`agent/marketplace_port.py` owns the shared typed interface, capability flags,
readiness metadata, and error categories. Its read operations cover job search,
individual jobs, client history, Connects balances, proposal inspection, conversation
messages, and cursor-based event history. Writes use `WriteRequest`/`WriteResult`;
reconciliation reads the recorded result by stable idempotency key. Read responses
remain JSON-compatible typed dictionaries; callers do not need simulator internals.

`marketplace()` chooses `mock`, `gigsim` or `upwork` from configuration. Optional mode
arguments help contract checks without modifying global settings. Unknown modes are
rejected. Each official adapter explicitly implements the interface but advertises
no capabilities and raises `Unavailable`. No guessed REST routes, MCP tool mappings,
OAuth flows or live writes are implemented. `status` reports that boundary honestly.

## Synthetic data and accounts

The job fixtures include an exact duplicate posting under another identifier, an
off-platform/free-work scam, a planted prompt injection, and an unmatched job.
Search deliberately returns the duplicate so later Scout deduplication can be tested.
Job content is data only. Reading it never creates proposals or authorizes actions.

Fixtures also contain three original client histories and deterministic simulation
settings. Each seeded tenant starts with 100 synthetic Connects. Seeding is
repeat-safe and does not reset spent Connects, existing jobs, faults or outcomes.
An existing unseeded user has an empty feed and zero balance. Unknown tenants fail.

## Write guarantees and limits

- Dry runs return the exact action and current Connects quote without creating a
  proposal/message, reserving a key, spending Connects, consuming approval, or
  consuming the fault scenario's remaining-attempt counter.
- Real local effects require the existing exact tenant/run/action approval binding.
  The simulator independently checks that binding; it does not implement the later
  approval graph or MCP layer in this phase.
- An effect, Connects debit, event, approval consumption and idempotency record share
  one transaction. SQLite uses `BEGIN IMMEDIATE`; Postgres uses a tenant user-row
  lock. Postgres runtime behavior is not verified on this workstation.
- Replaying a key and identical run/action returns the saved result before checking
  mutable costs, a deleted job or consumed approval. A changed run, text, price,
  destination, action kind, version or evidence binding conflicts without new effects.
- Different keys cannot submit twice for the same tenant/job ID. Distinct duplicate
  job IDs are intentionally separate marketplace postings; Scout content deduplication
  belongs to a later phase.
- Submission spends the current job's Connects once. Local draft creation and sending
  an approved message cost zero. Weekly usage resets by ISO week in UTC; lifetime
  spend and remaining balance are retained.
- A precommit crash rolls back the whole effect. A lost postcommit response raises
  `AmbiguousWrite`; reconcile the stable key before any retry. A failed reconciliation
  does not mean the write failed. External exactly-once guarantees are not claimed.
- Marketplace writes reject workspace holds/email kinds and unknown conversations.
  Repeated message writes produce one outbound message and one message event.

## Deterministic client outcomes

Outcome advancement is an explicit local control, never a freelancer send. Each
tick advances eligible proposals one stage: submitted -> viewed -> replied ->
interview -> hired, or terminal lost at a failed conditional stage. Drafts and
terminal proposals do not advance. Reply/interview/hire transitions add visibly
synthetic inbound messages. Every transition appends a unique, increasing event.

Each submitted proposal snapshots the simulator seed and conditional probabilities.
A SHA-256 draw over seed, job ID, proposal text, price and current stage decides the
next status. Tenant IDs, random proposal/run IDs and time do not affect the draw.
New configuration affects future proposals only. Same inputs reproduce the same
statuses; identifiers remain unique. Repeated tick keys return the stored result
and never produce a second transition. No LLM client or hidden GigSim preference
model is simulated. These outcomes validate infrastructure, not proposal quality or
official reply/hire rates.

## Fault scenarios

`FaultScenario` accepts `none`, `outage`, `rate_limit`, `server_error`, `timeout`,
and `ambiguous_write`. Set `operations` to target particular interface operations
and `remaining` to an exact number of affected calls, or null for persistent faults.
The attempt counter is durable and tenant scoped. Clearing/resetting the scenario
reproduces the sequence. A timeout is an immediate deterministic exception rather
than a real sleep. Rate-limit errors expose status 429 and `retry_after`; server
errors expose 503. Ambiguous responses affect executed writes only, after commit.

## Local commands

Run from the project root after Phase 1 migrations and account registration. Obtain
the tenant ID from the authenticated `/auth/me` response. These commands do not start
workers or MCP servers and refuse development mutations outside mock mode.

```powershell
uv run python -m dev_support.mock_marketplace status
uv run python -m dev_support.mock_marketplace seed --tenant YOUR_USER_ID
uv run python -m dev_support.mock_marketplace fault --tenant YOUR_USER_ID --json '{"mode":"server_error","operations":["search"],"remaining":2}'
uv run python -m dev_support.mock_marketplace fault --tenant YOUR_USER_ID --json '{"mode":"none"}'
uv run python -m dev_support.mock_marketplace configure --tenant YOUR_USER_ID --json '{"seed":4016,"reply_probability":1,"interview_probability":1,"hire_probability":1}'
uv run python -m dev_support.mock_marketplace advance --tenant YOUR_USER_ID --tick-key local-demo-tick-0001
```

Advancement needs an already approved and submitted local proposal. It does not
create one or bypass approval. Do not start later-phase workflows until requested.
The existing UI only exposes its earlier, limited fault selector; advanced Phase 2
controls above are intentionally CLI controls rather than new UI or MCP features.

## Checks and sources

```powershell
uv run python -m pytest tests/mock_marketplace -q
uv run python -m pytest tests/mock_marketplace tests/unit/test_auth.py tests/unit/test_foundation.py tests/integration/test_approval.py -q
uv run python -m ruff check .
```

Tests use isolated SQLite databases and synthetic users. Simulator tests are separate
from MCP and official GigSim contract tests. Compatibility tests exercise existing
approval behavior without adding later-phase implementation. The pre-existing
full-MCP graph failure documented in PHASE_STATUS.md is outside this phase.

Implementation API references checked: [SQLAlchemy ORM documentation](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html)
and [Pydantic TypeAdapter documentation](https://docs.pydantic.dev/latest/concepts/type_adapter/).
No dependency versions were changed.
