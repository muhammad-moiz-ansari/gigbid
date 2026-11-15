# Skipped scam

Source: local Groq and Ollama V2 smoke run dated 15 November 2026, using synthetic jobs and the mock marketplace.

Recorded trace ID `ea0afba1-75ad-4848-8b32-a30cda142ed1`
Final run status `skip`

This export includes event names, node names, and status only.

| Elapsed seconds | Recorded event | Node or status |
|---:|---|---|
| 0.00 | `worker:started` |  |
| 2.57 | `node:started` | intake, started |
| 3.39 | `node:intake` | intake, completed, running |
| 3.42 | `node:started` | analyst, started |
| 4.17 | `node:started` | risk, started |
| 4.19 | `node:started` | matcher, started |
| 7.00 | `node:analyst` | analyst, completed |
| 7.58 | `node:risk` | risk, completed |
| 10.04 | `node:matcher` | matcher, completed |
| 10.06 | `node:started` | reconcile, started |
| 10.09 | `node:reconcile` | reconcile, completed, skip |
| 11.16 | `worker:finished` | skip |
