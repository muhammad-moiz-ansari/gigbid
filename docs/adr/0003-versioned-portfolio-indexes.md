# ADR 3: Authoritative evidence, generation-filtered vector indexes

Accepted for Phase 4 local implementation.

Keep tenant-scoped SQL evidence/source references authoritative. Store typed metadata,
raw/document/chunk hashes, extracted sections and loader/chunker versions. Treat
identical uploads as provenance aliases, preserve unchanged chunks, and atomically
replace/delete source references and lexical records. Invalidate only approvals that
cite affected evidence.

Publish Qdrant vectors under a model-revision namespace and a corpus-fingerprint
generation. Always filter tenant/generation/authorized IDs and rehydrate current
passages from SQL. This avoids presenting stale evidence when SQL and Qdrant cannot
commit atomically. Persist cleanup work on failure and never claim physical removal
until the service acknowledges it.

Use actual Ollama model digests, bounded batch embedding, dimensional/finite checks,
and revision-aware caches. Missing embedding services fail explicitly. No production
fake-vector switch is provided. BM25 remains an explicit lexical mode independent
of model availability.

Qdrant local persistence is the portable development option because Docker is absent.
Short file-locked operations serialize stdio processes; close Qdrant before releasing
the operation lock. A configured Qdrant server remains supported. This changes no
official GigSim files or external integration contracts.

Keep Qdrant/grpc imports lazy: BM25-only MCP subprocesses must not pay vector-stack
startup costs. An existing full-protocol compatibility failure was resolved after
this dependency boundary was corrected; no graph design or approval budget was changed.

Use V0 as the default baseline until Phase 8 supplies valid comparative evidence.
No measured winner is claimed. GitHub MCP and real-model checks remain pending.
