# Dependency register

The instructor's **Student Starter Kit v0.1** has been received. Its original
sample files and illustrative policy are preserved under `data/sample/` and
`data/policy_pack/`. It does not include GigSim, the full persona corpora, the
grading policy/update, or a labelled development set. The table below refers
to those separate inputs.

To import the two sample jobs and portfolio passage into an existing mock-mode
tenant, run `python -m scripts.manage seed --tenant TENANT_ID --starter-kit`.
This is additive and does not reset Connects. The sample jobs have no client
references, so each gets an unverified mock client with no recorded activity.
The sample freelancer and unlinked client history remain reference data. The
normal seed and evaluation fixtures remain available as before.

| Missing input/service | Affected acceptance | Local substitute | Replacement / blocked verification |
|---|---|---|---|
| Instructor GigSim and contract | R1, A2, C6, outcomes | dev_support/mock_marketplace | Import unchanged to gigsim; map verified contract and run official suite |
| Three persona corpora | B1, B4 | Original synthetic examples | Import to data/personas; provenance-check and reindex |
| Policy pack and November 2 update | Compliance, change study | Versioned provisional rules | Import actual pack; record real diff and effort; never infer update |
| Labelled dev set | Retrieval, decisions, architecture studies | Synthetic harness only | Import dev set, record hashes and rerun; hidden set never stored |
| Human labels/panel | Judge calibration, pairwise quality | None | Collect 30 real labels and anonymised ratings |
| Docker | Full Compose startup and crash tests | SQLite local option | Verified 2026-11-08: full stack started, API crash demo submitted once on Postgres |
| Model provider and hardware | Open profile and model comparison | Hosted Groq gpt-oss (key in `.env`) or local Ollama Qwen3; labelled test client in tests | Real runs recorded in PHASE_STATUS.md; local qwen3:1.7b fallback not pulled; no model comparison yet |
| Upwork account | OAuth and live capabilities | Mock marketplace by default; `MARKETPLACE_MODE=upwork` for live | Sign-in and reads verified 2026-11-08; live writes only with the user's explicit authorization |
| GitHub token | Repository ingestion through GitHub's MCP server | Read-only `GITHUB_TOKEN` in `.env` | Verified 2026-11-08 with a live import of a public repository |
| Trace host credentials | Public trace links | Persisted local events | Configure Langfuse and verify traces before linking |
| Deployment/publication authorization | Public URLs/packages/article | Local artifacts only | Obtain separate explicit authorization after local review |

Installing dependencies requires package-registry network access. Environment failures
are recorded in PHASE_STATUS.md and must not be represented as passing checks.

Phase 2: the original mock now includes durable proposals/messages/events,
idempotent Connects accounting, configurable deterministic outcomes and reproducible
fault controls. Its shared port contract is locally tested; this is not verification
against official GigSim. All starter-kit and live-integration blockers above remain.

Phase 3: three owned MCP servers are implemented and locally protocol-tested. HTTP
uses first-party audience-bound credentials; general OAuth and Upwork OAuth are not
claimed. Inspector screenshots await actual inspection. Third-party connections and
official contracts remain absent; their operations do not return synthetic success.

Phase 4: portfolio ingestion and index lifecycle are locally tested. Qdrant local
persistence works without Docker, including reopened-process checks. The real local
Ollama `/api/tags` probe timed out; real open-model embedding execution remains
pending. Dense tests use explicit test vectors, not reported model results. GitHub
MCP ingestion has an unavailable boundary until a scoped, verified integration is
provided. Official corpus and evaluation blockers remain unchanged.

Phase 5: persisted approval, replay protection and worker crash recovery are tested
locally with SQLite and the original mock. AsyncPostgresSaver and advisory locking
are implemented; real Postgres verification is an explicit optional skipped check
until a disposable service is supplied. Model HTTP contract tests use labelled
responses, not real inference. Open-model generation/hardware measurements and
official backend exactly-once guarantees remain unverified.

Phase 6: real local HTTP/SSE and installed Chrome browser checks are available and
implemented. Browser runs use isolated SQLite, a real graph worker and labelled
model doubles. The core UI, replay and approval paths are locally verified; this
does not resolve real-model, official-integration, hosted-trace or Postgres blockers.
No Phase 7 work has been started.

Real-model fixes: generation runs on hosted open-weight models through Groq with the user's key,
kept only in the git-ignored `.env`; embeddings run locally on Ollama `nomic-embed-text`, which
now executes for real. Free-tier rate limits apply: a rate-limited call waits at most 10 s and
then uses the fallback model. Official inputs and hosted traces remain blocked.
Compose now passes the model settings and runs Ollama for embeddings, a shared Qdrant store
and the MCP servers over HTTP; the full stack and the Postgres checkpoint test ran on 2026-11-08.
