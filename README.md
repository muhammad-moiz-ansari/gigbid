# GigBid

An evidence-grounded freelancer copilot with human approval before outgoing actions.

**Current handoff: Phase 0 complete; Phase 1 local foundation finished and stopped.** The user
requires explicit instructions before each subsequent phase. Later-phase code
started under the original authorization is preserved but unfinished.

The foundation includes FastAPI, Next.js/TypeScript, multi-user sign-in, tenant-scoped
storage, migrations, generated API types, and visibly labelled synthetic examples.
Local development uses SQLite. Postgres/Redis Compose configuration is provided;
Docker startup has not been verified on this workstation.

Phase 1 checks passed: five foundation tests, Ruff, generated API types, TypeScript
and the production web build. Postgres/Compose execution remains an environment
blocker. See the phase log for exact commands and unfinished later-phase work.

See [local startup and checks](docs/RUNBOOK.md), [phase status](docs/PHASE_STATUS.md),
[requirements](docs/REQUIREMENTS.md), and [missing dependencies](docs/DEPENDENCIES.md).

Official GigSim, persona data, policy update, live accounts, real-model evaluations,
human ratings and public deployment are pending. No official outcomes are claimed.
No commits or external publication actions have been performed.
