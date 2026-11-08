# Requirements matrix

Status starts pending; PHASE_STATUS.md records actual implementation and verification.

Phase 2 update: the shared port, provisional mock contract, synthetic fixtures,
deterministic outcomes, fault controls and transactional idempotency are implemented
and locally tested under `tests/mock_marketplace/`. This does not complete R1's
official integrations, R2's MCP acceptance or any subsequent phase.

Phase 3 update: all three own MCP servers now have constrained schemas, structured
outputs, bearer/session authentication, tenant checks, shared rate limiting,
redacted audits and role-filtered client access. In-memory, stdio, HTTP and local
server recovery checks pass. Inspector screenshots and the external integrations
remain pending. See TOOLS.md and the phase log.

Phase 4 update: structured portfolio loaders, metadata/hash provenance, source
alias deduplication, transactional replacement/deletion, persistent tenant-scoped
BM25/Qdrant indexes, model/corpus versions and baseline V0 are implemented. Tests
cover real local Qdrant and Portfolio MCP with labelled test embeddings. Actual
Ollama execution, GitHub MCP ingestion and official corpora remain unverified or
unavailable; no retrieval quality winner is claimed.

Phase 5 update: durable parallel bid routing, validated handoffs, bounded verified
rewrites, durable budgets, saved human decision receipts and context-bound approval
are implemented. Separate worker-process crash checks verify one mock effect/debit;
forged resumes and material changes fail closed. Postgres and real-model execution
remain pending. See BID_WORKFLOW.md and checks/phase5.json.

Phase 6 update: onboarding, metadata-preserving uploads, saved filters, structured
job details, evidence citations, the proposal studio and paragraph regeneration are
implemented. Typed history and authenticated SSE expose actual saved graph activity
with replay, de-duplication and session revocation. See WEB_WORKFLOW.md and
checks/phase6.json for browser/backend results.

Phase 7 step 0 update: R5 claim verification now checks each sentence against the
evidence its paragraph cites (supported, partly supported or unsupported), replacing the
closed grammar that real models could not follow. Qwen3 thinking is disabled through
config.

Phase 7 update: conversation threads with intent classification and approved replies,
event-driven pipeline statuses, Celery/Redis scheduling with duplicate-posting detection,
style and outcome memory in a LangGraph store with explicit promotion rules and durable
forgetting, autonomy-controlled skip archiving, category analytics and checkpoint replay
are implemented. See PHASE_STATUS.md and checks/phase7.json.

| Requirement | Implementation paths | Verification / evidence | External gate |
|---|---|---|---|
| R1 single marketplace port | agent/marketplace_port.py; mcp_servers/marketplace/adapters | contract tests, mock idempotency | Official schemas/accounts |
| R2 three owned MCP servers plus two external | mcp_servers; agent/mcp_client.py | in-memory protocol tests, snapshots, TOOLS.md | Inspector, Upwork, GitHub |
| R3 custom parallel LangGraph | agent/graphs; agent/handoffs.py | parallel branch and reducer tests, diagrams | Real-model quality |
| R4 approval before any send/spend | graph interrupt; approval service; tools | restart, tamper, direct-write bypass, replay tests | Official reconciliation |
| R5 supported factual claims | rag/verify.py | fabricated, deleted and stale evidence tests | Human semantic review |
| R6 measured retrieval | rag/variants; evals/runners | Recall@5, MRR, nDCG, ablations | Official dev data |
| R7 controlled style/outcome memory | agent/memory | promotion/provenance/deletion tests | Real observations |
| R8 observability/budgets | events; agent/model.py; config | actual timestamps, tokens, limits; results JSON | Hosted traces, hidden run |
| R9 injection, PII, polite access | safety; MCP guard; schedules | attack suite, masking, isolation | Official planted attacks |
| R10 deployable multi-user product | apps; infra | migration, auth, Playwright, Compose | Docker/public authorization |
| A1-A7 schemas/auth/dry-run/idempotency | MCP servers, TOOLS.md | schema snapshots, protocol auth tests | Live OAuth, Inspector |
| B1 ingestion/deletion/metadata | rag/ingest; rag/index | dedup, replacement, tenant isolation | Official corpora/GitHub |
| B2 V0,V1,V2,V3,V4,V8 | rag/variants | component comparisons; real dense/rerank checks | Open model downloads |
| B3-B5 claim and retrieval evaluation | rag/verify; evals | labelled metric fixtures; provenance JSON/CSV | Judge labels/panel |
| C1-C7 bid/conversation graphs and memory | agent/graphs; worker | restart/resume, bounds, safe edit/reject | Full Postgres crash demo |
| D all nine web screens | apps/web/src/app | five required Playwright journeys | Browser availability |
| E1 scheduling/background | worker | dedup, saved-search intervals, recovery | Redis |
| E2 CI and 30-job smoke | .github/workflows; evals | command exit codes and regression gates | Official GigSim smoke |
| E3-E6 traces/safety/budgets/packaging | infra; docs/RUNBOOK.md | redaction, service readiness, measured budgets | Docker/traces/public URL |
| Study A 40 tasks / tool variants | evals/runners | tool/argument accuracy and tokens | Labelled tasks + real models |
| Study B hypotheses / ablations | evals; DATA_CARD.md | per-persona/job breakdown | Official gold and outcomes |
| Study C 50 jobs / three architectures | evals/runners | same data/model/budget comparison | Real models and dev data |
| Two open model configurations | agent/config.yaml | quality/speed/hardware results | Inference services |
| Judge calibration 30 labels | evals/runners | Cohen kappa, human provenance | Real labels |
| X2 controlled proposal experiments | docs/EXTENSION.md; evals | assignment, significance test, intervals | Official independent outcomes |
| Failure taxonomy >=10 failed jobs | docs; evals | inspected actual failures, attempted fixes | Real failure sample |
| Submission artifacts | docs; README; Portfolio package | report <=10 pages, write-up 1200-1800 words, demo script, checklist | Recording, public links, publication |

User authorization covers local work only. Submission instructions describe required
eventual artifacts; they do not authorize deployment, commits or publication.
