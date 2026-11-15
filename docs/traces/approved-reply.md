# Approved mock client reply

Source: local Groq and Ollama V2 smoke run dated 15 November 2026, using synthetic jobs and the mock marketplace.

Recorded trace ID `5828a778-0989-4e20-824f-80adb771079c`
Final run status `sent`

This export includes event names, node names, and status only.

| Elapsed seconds | Recorded event | Node or status |
|---:|---|---|
| 0.00 | `worker:started` |  |
| 2.90 | `node:started` | intake, started |
| 10.74 | `node:intake` | intake, completed, running |
| 10.77 | `node:started` | classify, started |
| 12.48 | `node:classify` | classify, completed, running |
| 12.50 | `node:started` | draft, started |
| 15.86 | `node:draft` | draft, completed |
| 15.89 | `node:started` | verifier, started |
| 21.12 | `node:verifier` | verifier, completed |
| 21.15 | `node:started` | compliance, started |
| 22.31 | `node:compliance` | compliance, completed, running |
| 22.33 | `node:started` | preview, started |
| 23.37 | `node:preview` | preview, completed, awaiting_approval |
| 24.35 | `worker:finished` | awaiting_approval |
| 24.42 | `human:approve` |  |
| 24.45 | `worker:started` |  |
| 27.24 | `node:approval` | approval, completed, approved |
| 28.21 | `node:started` | execute, started |
| 29.41 | `node:execute` | execute, completed, sent |
| 30.68 | `worker:finished` | sent |
