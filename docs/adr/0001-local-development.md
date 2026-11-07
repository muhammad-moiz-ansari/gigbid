# ADR 1: Explicit local substitutes and persistence

Accepted for local development, 2026-11-07.

The workspace initially contained only README.md; Git status was clean. No applicable
AGENTS.md was found in the workspace or ancestor directories. The assignment PDF
and Instructions.md were read before implementation.

Official GigSim, persona corpora, policy pack, November 2 update and evaluation data
are absent. Reserve their assignment paths; use original labelled fixtures under
dev_support only. Official adapters fail closed until their contracts are supplied.

Use Python/FastAPI, hand-written LangGraph, MCP SDK, Next.js/TypeScript, SQLAlchemy,
Celery/Redis, Qdrant, Ollama and optional Langfuse. Postgres is the Compose target.
SQLite with the official SQLite checkpointer is a local development option because
Docker is unavailable on this workstation. It is not evidence of Postgres verification.

No real-model service is assumed. Real open-profile runs fail visibly if Ollama is
unavailable. Deterministic model doubles are restricted to explicitly marked tests.
No live accounts, publishing, Git mutations or public deployment are authorized.
