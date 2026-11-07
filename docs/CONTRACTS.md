# Contracts and declared targets

All identifiers are opaque strings. Every owned record is tenant scoped. A graph
thread is a tenant-qualified run identifier. Job state, append-only redacted events,
and promoted memory are separate. Parallel analyses use an additive reducer.

Evidence carries a stable content hash, tenant, source, location, type, persona,
project, skills, date, industry and outcome. Removal invalidates approval and future
retrieval; a source hash change replaces chunks rather than appending duplicates.

Marketplace modes are mock, gigsim and upwork. Capabilities explicitly distinguish
read, draft, submit, message and reconciliation. Mock write effects and their
idempotency records share one transaction. Reusing a key with a different payload
is a conflict. Dry runs never spend Connects or create an external draft.

Approval binds tenant, run/thread, action, draft version/hash, destination, price,
Connects quote and evidence hashes. Edits and changes to preconditions invalidate it.
The tool rechecks the binding at execution. Approval is a durable LangGraph interrupt,
never a model instruction. Unknown external write outcomes require reconciliation.

Provisional targets (not measurements): analysis p95 <= 60 seconds, proposal p95 <=
120 seconds, 24 graph steps, 12,000 model tokens, 180 active seconds, API USD <= 0.10
per proposal. Local execution records hardware/throughput separately, with API cost
null rather than an invented USD equivalent. Targets remain subject to experiments.
