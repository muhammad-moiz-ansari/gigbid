# Dependency register

| Missing input/service | Affected acceptance | Local substitute | Replacement / blocked verification |
|---|---|---|---|
| Instructor GigSim and contract | R1, A2, C6, outcomes | dev_support/mock_marketplace | Import unchanged to gigsim; map verified contract and run official suite |
| Three persona corpora | B1, B4 | Original synthetic examples | Import to data/personas; provenance-check and reindex |
| Policy pack and November 2 update | Compliance, change study | Versioned provisional rules | Import actual pack; record real diff and effort; never infer update |
| Labelled dev set | Retrieval, decisions, architecture studies | Synthetic harness only | Import dev set, record hashes and rerun; hidden set never stored |
| Human labels/panel | Judge calibration, pairwise quality | None | Collect 30 real labels and anonymised ratings |
| Docker | Full Compose startup and crash tests | SQLite local option | Install Docker Desktop; validate full service stack |
| Ollama models/hardware | Open profile and model comparison | Test-only deterministic client | Pull configured open models; run real inference and record hardware |
| Upwork approved credentials/contract | OAuth and live capabilities | Fail-closed boundary | Verify official tools/auth, encrypted token lifecycle, no live writes without authorization |
| GitHub MCP credentials/server | Repository ingestion | Uploaded text only | Connect scoped third-party MCP and validate actual contract |
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
