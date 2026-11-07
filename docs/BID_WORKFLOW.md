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

From the project root, after configuring the database, Ollama models and portfolio:

```powershell
uv run python -m scripts.manage worker
```

This runs the existing queue drainer. It does not start or connect real marketplace
accounts. Open generation requires the configured qwen3 models; V0 retrieval also
requires nomic-embed-text. Explicit BM25 remains a diagnostic development option.
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
or new writes. Recovery reads can still confirm an already completed effect.
The budget ledger is authoritative; checkpoint usage lists summarize completed
nodes. Attempt-level budget events include failures and preserve numeric metrics.
API USD is unreported/null for local Ollama calls; hardware cost is not measured.

The verifier accepts exact complete current evidence passages and a closed grammar
of future plans and questions. Prefixing a past achievement with "Proposed approach"
or "Question" cannot bypass it. Partial quotes are removed because they can drop
negation. Multi-paragraph quotes retain context. Unsupported screening answers are
also removed, and compliance scans both question labels and answer content.
Screening labels must match questions from the actual marketplace job; invented
labels are removed and recorded as unsupported rather than sent with the proposal.
Versioned writer/liaison v2 prompts describe the accepted grammar. This intentionally
restricts prose variety. Reported before/after counts measure this deterministic
grammar check, not semantic accuracy or a real-model quality score.

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
