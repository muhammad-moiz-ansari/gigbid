# Crash and resume

Source: isolated worker recovery test with labelled model doubles. The first worker exited with code 73 after the mock commit. The restarted worker recovered one proposal and the test verified one eight-Connects debit.

Recorded trace ID `3edc423e-e71e-4f9f-a968-0bcd6275c6d7`
Final run status `submitted`

This export includes event names, node names, and status only.

| Elapsed seconds | Recorded event | Node or status |
|---:|---|---|
| 0.00 | `worker:started` |  |
| 0.14 | `node:started` | intake, started |
| 0.15 | `node:intake` | intake, completed, running |
| 0.17 | `node:started` | analyst, started |
| 0.17 | `node:started` | risk, started |
| 0.18 | `node:started` | matcher, started |
| 0.23 | `node:matcher` | matcher, completed |
| 0.24 | `node:analyst` | analyst, completed |
| 0.24 | `node:risk` | risk, completed |
| 0.26 | `node:started` | reconcile, started |
| 0.28 | `node:reconcile` | reconcile, completed, running |
| 0.29 | `node:started` | pricing, started |
| 0.35 | `node:pricing` | pricing, completed |
| 0.36 | `node:started` | writer, started |
| 0.40 | `node:writer` | writer, completed |
| 0.41 | `node:started` | verifier, started |
| 0.43 | `node:verifier` | verifier, completed |
| 0.44 | `node:started` | critic, started |
| 0.48 | `node:critic` | critic, completed |
| 0.49 | `node:started` | compliance, started |
| 0.53 | `node:compliance` | compliance, completed, running |
| 0.54 | `node:started` | preview, started |
| 0.56 | `node:preview` | preview, completed, awaiting_approval |
| 0.61 | `worker:finished` | awaiting_approval |
| 0.64 | `human:approve` |  |
| 5.88 | `worker:started` |  |
| 5.98 | `node:approval` | approval, completed, approved |
| 6.02 | `node:started` | execute, started |
| 10.55 | `worker:started` |  |
| 10.73 | `node:execute` | execute, completed, submitted |
| 10.78 | `worker:finished` | submitted |
