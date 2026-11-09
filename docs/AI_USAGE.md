# AI-assisted implementation record

Codex assisted with the local project implementation using file inspection, patches,
terminal commands and official documentation. No commits, pushes, PRs, real account
connections or publishing actions were performed by the assistant.

Phase 3 affected the MCP servers/shared schemas, delegated authentication, the MCP
client, observed availability in the API, local protocol tests, schema snapshots,
configuration and documentation. Detailed scope and check evidence are in the phase
log and TOOLS.md. Existing retrieval and graph implementations were exercised only
for compatibility, not extended into a subsequent phase.

A real caught mistake: the original client called LangChain tools without a full
ToolCall, losing the structured artifact, then decoded only the first text block of
a list result. This caused the previously recorded full-MCP graph failure. The fix
preserves the artifact and tests list/null decoding through real protocol sessions.
Another caught mistake was applying string-based log redaction to an entire JSON
message: it masked numeric durations and made invalid JSON. The filter now redacts
parsed JSON values and a test verifies that numeric timing values remain intact.

All synthetic fixtures/model doubles are labelled. Passing protocol tests are not
evidence of official GigSim outcomes, real-model quality or completed human studies.

Phase 4 affected ingestion parsers/models, corpus/BM25/Qdrant indexing, V0 integration,
upload/index-status endpoints, configuration, generated API types, synthetic fixtures,
tests and data/index documentation. Portalocker was promoted from an existing pinned
transitive dependency to a direct dependency for cross-process local-index locking.

A caught compatibility issue: eagerly importing Qdrant/grpc made BM25-only fresh MCP
subprocesses load the vector stack unnecessarily. A full-protocol compatibility test
failed during this work. Moving vector imports behind actual vector operations was
followed by a passing focused regression, without changing graph design or budgets.
Another caught issue was releasing the local operation lock before closing Qdrant;
the close now occurs inside the lock, verified with concurrent threads and a reopened
process. Semantic quality is not inferred from the fixed vectors used in these tests.

Phase 7 (from 2026-11-08) uses Claude Code (Claude Opus) for implementation, tests and
documentation. Step 0 affected agent/model.py, agent/config.yaml, agent/nodes/workflow.py,
rag/verify.py, the v3 writer/liaison prompts, apps/api/routers/workflow.py,
BidWorkspace.tsx, tests/support.py, grounding and approval tests, and these docs.

A real caught mistake: every earlier check used scripted stand-in models that always write
perfectly formatted text, so 160 tests passed while the product had never produced a
proposal with a real model. The first real-model smoke test showed qwen3 thinking by
default (empty answers and timeouts) and a qwen3:8b writer that never satisfied the closed
grammar, so every draft was removed. Both were fixed in step 0: with real models the writer's draft now passes verification
and the Critic. The Compliance model's repeated false positives were then made advisory
warnings, and a real-model proposal reached approval and was submitted exactly once.

Phase 7 steps 1-8 (Claude Code) affected the conversation graph and new `agent/nodes/liaison.py`,
`agent/categories.py`, the memory store and promotion rules, the worker (runtime, pipeline,
scout, schedule, tasks, replay), new API modules (`conversations.py`, messages, pipeline,
memory, analytics and replay routers), approvals, the mock marketplace's message events,
Compose, the web components (new `ApprovalPanel` and `RunViewer`), tests and these docs.

A real caught mistake in existing code: `stage_approval` reused any approval with the same
binding unless it was invalidated, including one that was already approved and consumed. A
replay that recreated an identical preview would have shown a dead, already-used approval.
Writing the replay test exposed it; reuse is now limited to still-pending approvals.

The real-model fixes and hosted profile (Claude Code) affected agent/model.py, agent/config.yaml,
agent/handoffs.py, agent/budgets.py, agent/nodes/workflow.py and liaison.py, new prompts (writer
v4, answer v2, pricing v2, risk v2), apps/api/config.py, the retry endpoint, BidWorkspace.tsx, the
new `scripts/smoke.py`, the Makefile, `.env.example`, tests and these docs.

A real caught mistake: the first forced-fallback check against Groq marked the run's usage as
unknown although the provider had rejected the request (404) and generated nothing, which would
have stopped a healthy run as needs_attention. Rejected 4xx requests now count as known zero
usage while timeouts and 5xx stay unknown, with a test for each case and a repeated real check.
Another: gpt-oss-120b failed Groq's strict JSON-schema validation at an 800-token cap, so the
provider now uses JSON mode with the schema in the system prompt and larger caps; eight of eight
real calls then validated.

The quality review (Claude Code) affected rag/verify.py, agent/nodes/workflow.py and liaison.py,
agent/handoffs.py, agent/model.py, agent/config.yaml, agent/graphs/bid_graph.py, new prompts
(writer v5, answer v3, liaison v4, pricing v3, risk v3, json_mode v1), the mock jobs fixture,
infra/docker-compose.yml, scripts/smoke.py, tests and these docs.

Real caught mistakes: the smoke check counted submissions, so a reply sent without its interview
slots and $50 bids on a $900 job passed unnoticed until the drafts were read; it now reports
quality warnings. The earlier plan-only screening answers contradicted the PDF, which asks for
evidence citations. And my own field names (`spend` next to `paid_per_hire`) led the pricing model
to describe the client's $4,000 total as "per hire"; reading the price reasons caught it, and the
fields are now `total_spend` and `average_paid_per_hire`.

The Compose and integration work (Claude Code) affected infra/docker-compose.yml, the new GitHub
import in rag/ingest/github.py, its endpoint and Settings form, agent/config.yaml, apps/api/config.py,
the generated API client, the Playwright folder move to apps/web/tests/e2e, tests and these docs.
A real caught mistake: in Compose the API and worker would each have kept their own embedded vector
index inside their containers; a shared Qdrant service now serves the API, worker and Portfolio MCP
server.
The live GitHub import caught two more of my mistakes: the tool limit I documented was not applied
by GitHub with the URL I chose, and the file order I wrote imported a generated file and helper
scripts instead of the app's source; listing the server's tools and reading the imported files
showed both.

The Upwork sign-in (Claude Code) added apps/api/auth/upwork.py, apps/api/auth/tokens.py, the
integrations router, the Settings panel, configuration and tests. A real caught mistake: appending
the encryption key to `.env`, which had no final newline, glued it onto the GitHub token line;
checking the variable names caught it and the line was split back before anything used it.
Building the Upwork adapter caught three more: the shared approval check compared the job with a
mock-only record, which would have refused every live proposal; my first readiness flag claimed the
adapter was externally verified although no live write had run; and my first adapter tests sent
writes that silently defaulted to dry runs. Failing tests and a review of the claims caught them.
The live Upwork write check caught one more of mine: the adapter treated any non-error reply as a
draft, so Upwork's "terms required" answer was reported as drafted. A reply without a preview id is now
a refusal that shows Upwork's next step, with a test for it.

Phase 8 (Claude Code, 2026-11-09) added the evaluation harness, composable retrieval pipelines and the studies.
Three Claude subagents wrote the synthetic dev set, one persona each, to a written specification; their gold
labels are therefore AI-authored, which the data card states. The tool-study tasks, rubric judge prompt and
hypotheses were written by Claude before any run. Evaluation itself made AI mistakes visible: the outcome-aware
boost reversed its order when BM25 scores were negative (found by a new test), and the first real run showed the
12,000-token thread budget could not fit even one of the two critic revisions the graph allows.
