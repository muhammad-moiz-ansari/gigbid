# ADR 2: Controlled MCP execution and local delegated credentials

Accepted for Phase 3 local implementation.

All three owned servers use the official SDK. Keep constrained tool inputs,
declared structured outputs, request-context identity and common redacted auditing.
Read annotations do not bypass authentication, tenant filtering or rate limits.

HTTP MCP tokens are audience-bound, hashed, short-lived children of revocable app
sessions. Stdio uses environment credentials. This first-party bearer design does
not pretend to implement Upwork OAuth or a general authorization server.

Use fresh SDK client sessions for each call and independent per-server discovery.
This costs handshakes but allows one server to fail without disabling healthy tools
and avoids retaining stale transports after restart. Role lists constrain exposed
tools and a second runtime check constrains invocation. Returned names must belong
to the server that advertised them.

Preserve structured MCP artifacts by invoking LangChain tools as full ToolCalls.
Otherwise the adapter can discard the artifact and list-valued tools may be reduced
to one text block. Regression tests cover lists, null results and real transports.

Timeouts cannot reliably cancel synchronous adapter writes. Treat these outcomes as
ambiguous, do not auto-retry writes, and use the stable key to reconcile. Audit late
completion separately. Existing approval and idempotency enforcement stays at the
side-effect boundary rather than trusting model text.

No retrieval algorithm, graph design, third-party integration or next-phase feature
was introduced. Inspector screenshots and official integrations remain pending.
