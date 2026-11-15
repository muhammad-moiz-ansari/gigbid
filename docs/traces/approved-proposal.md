# Approved mock proposal

Source: local Groq and Ollama V2 smoke run dated 15 November 2026, using synthetic jobs and the mock marketplace.

Recorded trace ID `c520d51d-68da-4e69-861c-8e080e415245`
Final run status `submitted`

This export includes event names, node names, and status only.

| Elapsed seconds | Recorded event | Node or status |
|---:|---|---|
| 0.00 | `worker:started` |  |
| 5.46 | `node:started` | intake, started |
| 6.70 | `node:intake` | intake, completed, running |
| 6.73 | `node:started` | analyst, started |
| 7.73 | `node:started` | risk, started |
| 7.75 | `node:started` | matcher, started |
| 11.12 | `node:analyst` | analyst, completed |
| 11.89 | `node:risk` | risk, completed |
| 30.89 | `node:matcher` | matcher, completed |
| 30.93 | `node:started` | reconcile, started |
| 30.96 | `node:reconcile` | reconcile, completed, running |
| 30.98 | `node:started` | pricing, started |
| 34.94 | `node:pricing` | pricing, completed |
| 34.97 | `node:started` | writer, started |
| 37.66 | `node:writer` | writer, completed |
| 37.69 | `node:started` | verifier, started |
| 43.33 | `node:verifier` | verifier, completed |
| 43.35 | `node:started` | critic, started |
| 45.32 | `node:critic` | critic, completed |
| 45.34 | `node:started` | compliance, started |
| 46.81 | `node:compliance` | compliance, completed, running |
| 46.83 | `node:started` | preview, started |
| 48.13 | `node:preview` | preview, completed, awaiting_approval |
| 49.25 | `worker:finished` | awaiting_approval |
| 49.35 | `human:approve` |  |
| 49.38 | `worker:started` |  |
| 53.19 | `node:approval` | approval, completed, approved |
| 54.36 | `node:started` | execute, started |
| 55.64 | `node:execute` | execute, completed, submitted |
| 56.93 | `worker:finished` | submitted |
