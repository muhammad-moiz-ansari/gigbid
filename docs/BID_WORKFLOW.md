# Phase 5 bid graph and approvals

The bid graph performs intake, parallel analysis/risk/fit using LangGraph Send,
barrier reconciliation, skip/watch/bid selection, pricing, writing, claim checking,
critique and compliance. Failed critiques allow at most two new drafts; each is
verified again. Human edits and renewal never reset that revision allowance.
The generated [bid graph](images/bid.mmd) includes conditional routes.

Pydantic contracts validate analytical handoffs, retrieved evidence, drafts,
decisions, prices, critiques and policy verdicts. Shared raw job input feeds all
parallel branches. Model-produced values cannot change marketplace identity,
requirements, screening questions, budget or Connects cost. Promoted memory,
checkpoint state and append-only execution events remain separate stores.

## Durable execution

Threads use tenant:run_id identifiers and synchronous checkpoint durability.
CHECKPOINT_URL selects AsyncPostgresSaver for postgres/postgresql URLs; local
SQLite uses AsyncSqliteSaver as an explicit development substitute. Workers acquire
a Postgres advisory lock or local process file lock before claiming a thread.
Expired leases cannot cause competing graph writers. Successful parallel branch
writes survive another branch failing; retry continues the saved graph.

Set DATABASE_URL to a SQLAlchemy Postgres URL and CHECKPOINT_URL to a psycopg URL
for the intended Postgres deployment. Existing Compose settings already supply both.
Checkpoint setup requires schema creation privileges. Postgres and Compose runtime
are unverified here because no service/Docker installation is available.

From the project root, after configuring the database, model profile and portfolio:

```powershell
uv run python -m scripts.manage worker
```

This runs the existing queue drainer. It does not start or connect real marketplace
accounts. Open generation uses the configured model profile (hosted Groq by default, or
local Ollama); V0 retrieval requires local nomic-embed-text. Explicit BM25 remains a diagnostic development option.
No production model double or silent retrieval/model substitution is provided.

## Approval boundary

Preview performs a dry run without spending. A real persisted LangGraph interrupt
then stops execution. The authenticated, CSRF-protected decision endpoint serializes
decisions and saves an immutable decision receipt. Its exact response digest must
match the resume value; directly calling Command(resume=...) cannot grant approval.

Approval binds tenant/thread, action kind, destination, text, draft version, price,
marketplace mode, dry-run Connects cost and cited evidence hashes. Graph approvals
also bind policy, profile and the raw job snapshot. The mock transaction checks
these again immediately before writing/charging. Material changes fail closed;
the worker invalidates a rejected active approval. Evidence ingestion/deletion
already invalidates affected reviews. Rejection requires a reason.

Edited text is stored with before/after content and a unified diff in tenant-owned
records, then re-verified, critiqued and compliance-checked. It gets a new draft
version and approval. Sensitive draft content is not put into node trace events.
Older pre-Phase-5 pending reviews need renewal to obtain the new context/receipt.
Renewal rechecks the draft and current profile; material job changes require fresh
analysis rather than silently authorizing the old analysis.

The stable key run_id:action_kind:vVERSION is checkpoint-derived before approval.
On execution/restart the worker reconciles that key first and validates any saved
effect against the approved payload, mode and cost. Ambiguous write responses are
reconciled instead of automatically repeating writes. The mock atomically saves
the effect, key, approval consumption and Connects debit. Crash-after-commit tests
demonstrate one mock effect and one debit across separate worker processes.
Official backends remain unavailable: exactly-once behavior is not claimed for
an external system without verified idempotency and reconciliation capabilities.

## Budgets and conservative claim checking

Durable per-run budgets atomically reserve graph steps and record tokens, API USD
and active node-seconds, including failed structured-model attempts. Parallel node
time is summed, so it is intentionally different from wall-clock latency. Human
approval wait is excluded. Limits and model timeouts/output caps live in config.yaml.
Retries do not reset counters. Missing/malformed inference usage or a reservation
left unfinished by process death causes needs_attention before further generation
or new writes. A human Retry then records an acknowledgement of that unknown usage
(the interrupted nodes and the time) in the ledger and continues within the remaining
budget. A rate-limited or rejected (4xx) request counts as known zero usage.
Recovery reads can still confirm an already completed effect.
The budget ledger is authoritative; checkpoint usage lists summarize completed
nodes. Attempt-level budget events include failures and preserve numeric metrics.
API USD comes from the hosted profile's published per-token prices. It is null for
local Ollama calls, whose hardware cost is not measured.

Phase 7 step 0 replaced the earlier closed grammar, which a real qwen3:8b writer never
satisfied: in the 2026-11-08 smoke test every draft was removed and the run was blocked.
Drafts are now plain paragraphs that end with `[evidence_id]` citations. The verifier
splits each paragraph into sentences. Questions, plans ("I would ...") and courtesy or
client-need sentences are kept. A sentence about past work must cite current evidence,
use only numbers that appear in it, not contradict a negation in it, and share at least
60% of its words with it (30-60% is partly supported). Unsupported and partly supported
sentences are removed before the Critic and counted before and after. Prefixing a past
achievement with "Proposed approach" or "Question" still cannot bypass the check.
Screening answers are checked the same way, and invented question labels are removed.
Citations stay in the studio; the client receives plain text. Thresholds live in
`agent/config.yaml`. Word overlap is a deterministic check, not semantic proof.

Compliance blocks only on rule checks: off-platform contact or payment, free work,
guarantees, contact details, injected text, banned phrases, the word limit and a failed
Critique. The compliance model (prompt v2) reviews the plain outgoing text and its concerns
appear in the studio as warnings for the human reviewer; it cannot block or approve. In real
runs a small model without portfolio access repeatedly flagged verified claims as fabricated.

Models receive only what each node needs. Evidence is trimmed to id, text, project, skills,
date and outcome, and marketplace job and client IDs are removed from every model input.
Screening answers cite evidence for experience questions and are "I would" plans otherwise.
Risk flags are validated against `policy.risk_flags` in config, and planted instructions raise
the risk score to at least `thresholds.injection_risk` (0.5) so the reviewer sees them, without
forcing a skip.

The claim checker reads curly quotes and non-breaking hyphens as plain text. A plan sentence that
names a portfolio project or says "as demonstrated in" counts as a claim and needs a citation,
and a "This/That/It..." sentence after a removed one is removed too. The Critic sends back a
model draft whose cover letter cites no evidence, quoting up to two removed sentences; a human
edit or a regenerated paragraph is reviewed as written.

Pricing gets the client's total spend, hires and average paid per hire, the fit score and the
Connects facts. Code keeps the bid within `pricing.budget_share` of the job budget (60-100%,
never below the floor), and when fit x bid is below Connects x `connect_usd` x `min_return` the
run stops as "watch" with the reason. Market statistics wait for GigSim's historical jobs.
Interview times come from the calendar tool and are added to the reply when the action is
built, so the approval preview shows exactly what is sent.

## Checks and limits

```powershell
uv run python -m pytest tests/integration/test_bid_durability.py tests/unit/test_phase5_grounding.py tests/unit/test_model_usage.py -q
uv run python -m pytest -q
uv run python -m scripts.graphs
```

For a disposable real Postgres checkpoint database, set
GIGBID_TEST_POSTGRES_CHECKPOINT_URL and run the optional Postgres restart test. It is
explicitly skipped when the service is absent. That check still uses labelled test
models and mock marketplace data; it does not verify production SQL/domain storage
or real inference. Real model/hardware and official integration checks remain pending.
Phase 6 UI work and all later phases are outside this handoff.

The implementation uses the pinned LangGraph 1.2.20 and checkpointer packages.
API behavior was checked against the official documentation for
[interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts),
[persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and
[graph routing](https://docs.langchain.com/oss/python/langgraph/graph-api).

## Conversation graph (Phase 7)

One durable thread per client conversation: intake (thread, job context and evidence),
classify (small-model intent with a rule-based scam override), draft, verifier, compliance,
preview, approval and send. Each new client message starts the next turn on the same thread.
Draft versions keep increasing so action keys stay unique, and a message that is already
being answered is never queued twice. Interview requests get free calendar slots from the
Workspace MCP; no calendar hold is created. Compliance blocks any dollar amount below the
user's minimum bid.

## Memory (Phase 7)

Promoted memory lives in a LangGraph store (SQLite locally, Postgres when `CHECKPOINT_URL`
is a Postgres URL) under per-tenant `style` and `outcome` namespaces. Both graphs are
compiled with the store and nodes read it with `get_store()`. Style rules come only from
approved text edits (the same word removed in five distinct runs). Outcome notes come from
replied, interview, hired and lost events grouped by a configurable skill-to-category map
(three outcomes in one category). Raw tool output never becomes memory. The writer and
liaison receive memory as labelled context, pricing receives the category's outcome note,
and the Critic sends back a draft that uses a word the user keeps removing. Forgetting an
entry deletes it and records a tombstone so later observations cannot promote it again.

## Replay (Phase 7)

`scripts.manage replay` and `/runs/{id}/replay` re-run a thread from a saved checkpoint as a
new branch with a fresh budget; earlier totals stay in the ledger. A replay that reaches
preview always needs a new approval, because only a still-pending approval is reused. A
replayed execute step reconciles its stable key, so a submitted proposal is never sent twice.
