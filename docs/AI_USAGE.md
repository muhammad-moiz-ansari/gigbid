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
