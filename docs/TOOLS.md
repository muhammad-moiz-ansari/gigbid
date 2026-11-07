# MCP tools and controlled access - Phase 3

## Implemented surface

Three servers use the pinned official MCP Python SDK (`mcp==1.30.0`). The agent
client uses `langchain-mcp-adapters==0.3.2`. No dependency versions changed in Phase 3.
All tools declare output schemas. Tool inputs use constrained Pydantic annotations;
write models forbid extra fields, constrain identifiers/keys and fix the action kind
for the particular tool. Context/tenant identity never appears as a tool argument.

The tool and resource/prompt snapshots under `tests/contract/` are generated from
actual SDK discovery. Tests compare them exactly; schema changes require an explicit
review and regeneration. No external server schemas or OAuth contracts are guessed.

Annotations in the table use R=readOnlyHint, D=destructiveHint, I=idempotentHint,
O=openWorldHint. They describe capabilities, not permission grants. Every own-server
tool requires an authenticated principal and shares the tenant's rate limit.

| Tool | Owner/server | Input | Output | R/D/I/O | Auth and execution |
|---|---|---|---|---|---|
| search_evidence | Portfolio | requirement 1-4000 chars, k 1-20, typed optional metadata filters | EvidenceHit[] | T/F/T/F | Tenant-filtered current passages; no arbitrary tenant filter |
| get_case_study | Portfolio | constrained evidence ID | Evidence | T/F/T/F | Tenant ownership checked; deleted/foreign IDs unavailable |
| list_skills | Portfolio | none | string[] | T/F/T/F | Skills from current tenant's metadata |
| search_jobs | Marketplace | query up to 4000 chars | JobSpec[] | T/F/T/T | Through the single marketplace port |
| get_job | Marketplace | constrained job ID | JobSpec | T/F/T/T | Current job, including Connects quote |
| get_client_history | Marketplace | constrained client ID | ClientHistory | T/F/T/T | No invented missing history |
| get_connects_balance | Marketplace | none | ConnectsBalance | T/F/T/T | Balance, lifetime/weekly spend and weekly limit |
| list_messages | Marketplace | constrained conversation ID | MarketplaceMessage[] | T/F/T/T | Tenant-owned conversations only |
| list_events | Marketplace | nonnegative cursor | MarketplaceEvent[] | T/F/T/T | Increasing tenant-scoped event cursor |
| create_proposal_draft | Marketplace | DraftRequest | WriteResult | F/F/T/T | Preview by default; execution requires exact approval |
| submit_proposal | Marketplace | SubmitRequest | WriteResult | F/T/T/T | Exact approval and cost/evidence revalidation; Connects spend is a destructive effect |
| send_message | Marketplace | MessageRequest | WriteResult | F/F/T/T | Additive message write, exact approval and stable key |
| reconcile_write | Marketplace | stable key 8-200 chars | WriteResult or null | T/F/T/T | Read the durable result after response loss |
| free_slots | Workspace | none | CalendarSlot[] | T/F/T/F | Synthetic 30-minute UTC calendar slots |
| create_interview_hold | Workspace | HoldRequest | WriteResult | F/F/T/F | Approved tentative local hold; no invitation |
| create_email_draft | Workspace | EmailRequest | WriteResult | F/F/T/F | Approved local draft; no email sending capability |

Marketplace tools have openWorldHint=true because the port is an external capability
boundary that will eventually target verified official integrations. Currently only
the mock adapter is implemented. Portfolio and Workspace operate on local records.
Local storage, rate counters and audits are infrastructure; read-only tools never
perform marketplace writes or Connects spending.

## Portfolio resources and prompts

- `portfolio://case/{id}` returns inspectable Evidence JSON with source/location,
  type, project, skills, date, industry, outcome, content hash and synthetic flag.
- `portfolio://proposal/{id}` exposes only an actual outcome-labelled portfolio
  proposal; a case study ID is not silently treated as a past proposal.
- `answer_screening_question(question)` and `portfolio_summary(skill)` load versioned
  prompts from `agent/prompts/`. User arguments are JSON-encoded as untrusted data.
- Resource and prompt calls use the same authentication, rate limit and audit path
  as tools. Data embedded in jobs, passages or client messages cannot supply identity
  or an approval. The local host decides whether to use these templates.

Portfolio MCP wraps the existing retriever; Phase 3 does not change ingestion or
retrieval algorithms. Protocol tests explicitly use the BM25 diagnostic to avoid
inventing a working embedding service. Real dense retrieval/model initialization
remains an independent requirement for subsequent phases.

## Authentication and trust

HTTP uses Streamable HTTP with SDK bearer middleware, JSON responses, Host/Origin
checks and resource validation. A delegated token is random, stored hashed and
bound to exactly one configured MCP endpoint. Its lifetime is at most one hour and
never exceeds its parent app session. Parent logout/revocation/expiry invalidates
children. Credentials for one owned MCP endpoint are rejected by the other endpoints.
The gateway mints children internally and deletes them when its context closes.

These are first-party local bearer credentials, not an implemented general OAuth
authorization server. The SDK metadata points to the local API, but OAuth discovery,
dynamic registration and Upwork OAuth are not claimed. A raw app session is rejected
by the HTTP MCP endpoint. No credential is put in a tool argument, URL, snapshot or
audit record. TLS and deployment identity configuration belong to deployment work.

Stdio receives a revocable parent app-session token through `GIGBID_MCP_TOKEN`, never
through command arguments or stdout. The client passes a limited environment to
subprocesses rather than all provider/account secrets. Each tool/resource/prompt
call rechecks the session. An HTTP caller can never use the server's inherited stdio
credential as a fallback.

| Server | Trust rationale | Integration state |
|---|---|---|
| Own Portfolio | Read-only exposure of explicitly uploaded, tenant-owned evidence with provenance | Implemented and protocol-tested |
| Own Marketplace | A single approved/idempotent port boundary; schemas constrain operations | Implemented and tested against original mock |
| Own Workspace | Narrow local calendar/email draft operations; no invitation or email send | Implemented and protocol-tested local mock |
| Official Upwork MCP | Intended official marketplace access, avoiding scraping and session cookies | Pending verified contract, OAuth and separate account authorization; unavailable adapter |
| Third-party GitHub MCP | Intended scoped repository ingestion through a separately reviewed server | Pending server/credentials/tool verification; not connected in Phase 3 |

## Approval and side effects

Every write requires a stable key and defaults to `dry_run=true`. Its preview shows
the exact action payload and expected Connects cost. Dry runs do not create the
intended marketplace/calendar/email effect or consume approval; they still produce
an audit and count toward rate limits.

Execution verifies the approval's tenant, run, action kind, text/version, destination,
price, quoted cost and referenced evidence hashes. Changed Connects quotes, deleted
evidence, changed drafts or unavailable calendar slots block execution. The existing
approval workflow must obtain renewed approval; tools cannot grant it themselves.
Unknown external schemas remain unavailable rather than returning synthetic success.

The Workspace mock serializes writes with a tenant lock, includes run ID in the
idempotency fingerprint and reserves canonical offered UTC slots. A different key
cannot reserve an already-held slot. Repeated requests return their original result.
Email drafts are additive local records. No real calendar or mail service is used.

## Deadlines, retry and recovery

`MCP_SERVER_TIMEOUT_SECONDS` bounds server operations. A synchronous adapter may
finish after its caller's deadline, so a timed-out write is explicitly ambiguous.
Late completion/error is separately audited. Do not interpret cancellation, timeout
or transport loss as proof that a write failed; reconcile its stable key.

The gateway applies per-call client deadlines and bounded exponential backoff to
transient **read** failures. It does not retry permission, validation or authentication
failures. It honors Retry-After: a delay beyond the configured short retry window
surfaces recoverable work instead of polling early. Writes get one attempt, including
dry-run tool calls. Restarts reuse stable keys through the existing workflow.

Discovery and failure are independent per server. Tools returned under an unexpected
server/name are discarded. Each call opens a fresh SDK session, trading extra
handshakes for simple recovery after server restart. Availability/error codes are
persisted per tenant with a timestamp and supplied trace ID. `/status` reports the
last observed MCP states and drives the existing marketplace-unavailable banner.
This is observed state, not an independent continuous health probe. Queued runs are
retained; existing recoverable runs can be explicitly retried after service recovery.

Role allowlists are enforced both when presenting tools and at invocation:

| Role | Available names |
|---|---|
| Scout | search_jobs, list_events |
| Intake | get_job |
| Job Analyst / Compliance Guard | none |
| Risk Assessor | get_client_history |
| Fit Matcher | search_evidence |
| Pricing Strategist | get_connects_balance, get_client_history |
| Writer | search_evidence, get_case_study |
| Verifier / Critic | get_case_study |
| Client Liaison | list_messages, search_evidence, free_slots |
| Approved-action executor | create_proposal_draft, submit_proposal, send_message, reconcile_write, create_interview_hold, create_email_draft |

Agent capabilities use this MCP gateway. App authentication, durable queues,
checkpoints, approval records and health/audit persistence remain infrastructure;
they are not tools that models can invoke directly.

## Rate limit and audit

The configured per-user fixed-window limit is shared by all three servers and all
that user's sessions, with SQLite transaction locking / Postgres user-row locking.
The default is a provisional development limit; tune it below verified official
limits when GigSim becomes available. Postgres runtime behavior is still unverified.

Audit entries append actor/tenant, tool, argument hash, redacted arguments, result
summary/hash or error code, timestamp and trace ID. Body/text contents are replaced
by hashes/lengths rather than copied into logs. Email/phone/payment/token patterns
are masked. Trace IDs come from the HTTP request or stdio environment. JSON log
numbers remain numbers after redaction. Audits are append-only in application code;
this is not a claim of tamper-proof database storage.

## Run and verify locally

Keep the Phase 1 database migrated. Stdio servers are managed by the gateway. For
standalone local HTTP testing, open three terminals and run from the project root:

```powershell
$env:MCP_TRANSPORT = 'http'
uv run python -m mcp_servers.portfolio.server
# Separate terminal, with MCP_TRANSPORT=http:
uv run python -m mcp_servers.marketplace.server
# Separate terminal, with MCP_TRANSPORT=http:
uv run python -m mcp_servers.workspace.server
```

Defaults bind only to 127.0.0.1, at ports 8001/8002/8003 and `/mcp`. Configure the
matching `*_MCP_URL` and explicit allowed hosts when changing local addresses.
Select `MCP_TRANSPORT=http` for the gateway process too. Token issuance is internal
to `agent.mcp_client.gateway`; no credential should be pasted into a public page.

```powershell
uv run python -m pytest tests/mcp tests/contract -q
uv run python -m pytest -q
uv run python -m ruff check .
# Only after intentionally reviewing a schema change:
uv run python -m scripts.mcp_snapshot
```

Tests use the SDK's real in-memory client and actual local stdio/HTTP transports.
The local process recovery test stops and restarts a real marketplace MCP subprocess.
Graph compatibility tests use labelled deterministic models and lexical retrieval;
they are not real-model or official GigSim checks.

MCP Inspector screenshots are **pending**: no Inspector UI session was exercised in
this phase, so no screenshots are fabricated. Inspector evidence, official-service
verification, third-party connections and research comparisons remain outstanding.

Primary API references reviewed: [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
[MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools),
and [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization).
Installed pinned SDK/adapter source was also inspected for context injection,
resource validation and structured result handling.

## Phase 4 portfolio update

The existing Portfolio tools now read versioned, incrementally maintained SQL/BM25
and Qdrant indexes. Tool output schemas and role permissions are unchanged. Upload
metadata, source aliases, replacement/deletion and cache cleanup are described in
DATA_CARD.md and RUNBOOK.md. V0's real Qdrant path is tested through an in-memory MCP
session using explicitly labelled test vectors. Real Ollama semantic execution is
still pending; GitHub ingestion remains unavailable. No Phase 5 graph work was added.
