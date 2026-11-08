# Phase 6 web workflow

The core UI uses the real API, durable run records and approval decisions. It does
not animate invented agent progress. Phase 7 features already present in the initial
repository were preserved; this phase does not extend conversations or scheduling.

## Use the local workflow

Start the API, web and worker using RUNBOOK.md. Real generation requires the
configured Ollama models, and dense V0 requires its embedding model. No production
test-model switch was added. Synthetic development examples remain visibly labelled.

1. Register or sign in. Settings opens for a new account.
2. Save persona, fixed/hourly rates, weekly Connects budget and opportunity filters.
   Marketplace selection shows the configured backend. Other modes are disabled;
   official integrations and real account connection remain unavailable.
3. Paste portfolio text or upload PDF, Markdown, text or JSON. Choose evidence type,
   skills, project, persona, date, industry and proposal outcome where applicable.
   These metadata are sent with both pasted text and file uploads.
4. In the inbox, filter by text or decision. Saved skill, budget and Connects filters
   apply to the feed. Analysed fit ranks opportunities; cards show risk, decision,
   suggested bid and application cost. Unanalysed jobs are explicitly labelled.
5. Open a job and analyse it. The studio shows structured requirements, deliverables,
   timeline, needs to clarify, risk/fit, pricing reasoning and requirement-to-evidence
   matches. Citations open on hover or keyboard focus; Enter opens the source passage,
   and Escape dismisses the tooltip.
6. Inspect the grounded proposal, screening answers, removed claims, Critic and
   Compliance feedback. The dry-run summary displays destination, version, price and
   Connects cost. Approval is disabled while the cover letter has unsaved edits.
7. Save edits for rechecking, or regenerate a selected paragraph. Both invalidate
   the old review and require new verification and approval. Paragraphs are separated
   by blank lines and keep their own citations. Regeneration preserves other
   paragraphs; an invalid paragraph index is rejected before saving a decision.
8. Approve the exact action, or reject with a reason. Evidence-invalidated reviews
   show an inactive-review message and a recheck/renew action. Backend authorization,
   material-context checks and idempotency remain authoritative.

Pending review and completed actions come from SQL/checkpoints, so reloading the
browser restores them. Unsaved textarea edits are local and are discarded on a full
reload. They cannot be approved until saved and rechecked. Sign-out clears cached
workspace data and prevents old in-flight responses from populating a new session.
Source deletion invalidates reviews using affected evidence. Marketplace outages
show a degraded banner while retaining queued work and already displayed data.

## Actual event streaming

Authenticated `GET /runs/{run_id}/history?after=ID&limit=100` returns a tenant-owned,
paged history with `next_cursor` and `has_more`. `limit` is bounded to 500. Payloads
are redacted on read, including older audit records. Numeric usage metrics survive.

`GET /runs/{run_id}/events?after=ID` streams saved events as SSE frames with event
IDs. The browser first backfills history and then connects after its final cursor.
Automatic reconnects send Last-Event-ID, which the server combines with the query
cursor. New events are de-duplicated by ID. A reconnect button also supports manual
history reload. The UI retains the most recent 1,000 events and labels that limit.

Node-start events are persisted when a graph step reserves its budget. Completion
events come from actual graph updates; failures and human decisions are retained.
The viewer distinguishes history loading, live delivery, reconnecting and expired
sessions, and refreshes run state after streamed updates. Heartbeats are comments,
not synthetic activity. Open streams recheck session revocation/expiry. No database
transaction remains open across a stream yield.

The viewer exposes local trace IDs. Public trace links are unavailable until an
actual hosted tracing integration is configured and verified; none are invented.
Protocol handling follows the [SSE standard](https://html.spec.whatwg.org/multipage/server-sent-events.html).

## Browser verification

The Playwright configuration starts a separate API, real durable graph worker and
Next.js web server on loopback ports 8106 and 3100. Its opt-in server is under
`tests/e2e_server.py`; it uses original synthetic marketplace data, explicit BM25
retrieval and labelled deterministic model doubles. Its databases live only under
`.cache/e2e/<run-id>`. It does not connect real accounts or run later-phase scouting.
Production code never imports the test server or model doubles.

From the project root:

```powershell
uv run python -m pytest tests/integration/test_streaming.py tests/integration/test_phase6_workflow.py -q
uv run python -m scripts.openapi
cd apps/web
npm run generate
npm run typecheck
npm run build
# Use the installed Chrome browser; omit the variable for installed Playwright Chromium.
$env:PLAYWRIGHT_CHANNEL = 'chrome'
node node_modules/@playwright/test/cli.js test
```

Browser journeys cover profile/upload persistence, inbox-to-approved submission,
refresh/replay, evidence focus, edit/recheck, reasoned rejection, paragraph validation,
mobile navigation, empty filters and outage recovery.
The additional account-switching journey checks stale evidence reviews and verifies
that a new account cannot see the previous workspace's cached jobs or portfolio.
The desktop sidebar scrolls within the viewport so every navigation and sign-out
control stays reachable; mobile navigation uses an independent horizontal row.
Backend tests additionally use
real local HTTP streams to verify cursor replay, new events, tenant isolation and
session revocation. The browser tests do not establish real-model quality or Postgres
production behavior. See `checks/phase6.json` for actual results and limitations.

Phase 6 stops here. The remaining plan is Phase 7 conversations/scheduling/memory,
Phase 8 retrieval studies, Phase 9 official integrations, Phase 10 full reliability
and packaging, and Phase 11 extension and submission artifacts. These phases remain
unauthorized until individually requested; existing partial code is not acceptance.

## Phase 7 additions

- **Messages:** client messages are grouped by conversation. Each new client message queues
  a reply turn on that conversation's single durable thread. The reply studio shows the
  thread, the detected intent (question, negotiation, interview or scam), offered interview
  slots and the exact reply to approve. Scam signals get no reply. A new message that arrives
  while a reply waits for review cancels that review and redrafts.
- **Pipeline:** cards move forward from marketplace events (drafted, submitted, viewed,
  replied, interview, then hired or lost). Mock mode adds an "Advance simulated outcomes"
  button; outcomes also advance on a schedule.
- **Inbox:** skipped jobs are hidden behind a Skipped filter. With "Archive jobs the agents
  recommend skipping" on in Settings, skip decisions are archived automatically; with it off
  they show as Recommended skip with a Confirm button. Any job can be skipped with a reason,
  and duplicate postings found by the scout carry a badge. Nothing is sent without approval.
- **Analytics:** reply and hire rate by job category, Connects spent, median and 95th
  percentile tokens, active seconds and API USD per proposal, and top rejection reasons.
- **Settings memory:** promoted style rules (the same word removed in five approved edits)
  and outcome notes (three recorded outcomes in one job category) with their supporting
  observations. Forget removes the entry, records a tombstone and changes the next run.
- **Agent runs:** `/runs` lists runs; `/runs/ID` shows live activity and saved checkpoints
  with Replay buttons. This screen was empty before Phase 7.

Browser journeys now also cover a client reply approved with offered slots, forgetting a
memory entry and skipping a job (nine journeys in total). The memory journey seeds its rule
through a test-only route in `tests/e2e_server.py`; production code has no such route.
