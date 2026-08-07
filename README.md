# AI Test Intelligence Platform

An engineering platform that applies LLM-backed analysis to a codebase and its test
suite to answer three questions:

1. **Where is testing risk concentrated?** — coverage/risk scoring relative to change
   frequency, complexity, and existing test coverage.
2. **What tests should exist but don't?** — AI-generated test suggestions for
   undertested or high-risk code.
3. **Why did this test fail, and does it matter?** — AI-assisted CI failure triage:
   regression vs. flaky vs. environment, with flaky-pattern clustering over time.

These three capabilities share one ingestion → orchestration → provider-backed
analysis → persistence → API → dashboard pipeline, integrating primarily through
GitHub pull requests and CI webhooks.

This is a production-quality reference platform, built incrementally in scoped
engineering sprints — not a tutorial or hackathon project.

## Status

**Sprint 0 complete: architecture and system design.** No application code has been
written yet. See below for the full design before any implementation begins.

## Documentation

- [Architecture](docs/architecture.md) — high-level architecture, component diagram,
  repository layout, module organization, provider abstraction, observability, testing,
  and CI/CD strategy.
- [System Design](docs/system-design.md) — data flow diagrams, database schema, and API
  boundaries.
- [Development Roadmap](docs/development-roadmap.md) — sprint sequencing and explicitly
  deferred decisions.

## Stack (planned)

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL
- **Frontend:** React, TypeScript, Vite
- **LLM providers:** Anthropic Claude (primary), OpenAI (secondary), Mock (test/CI)
- **CI/CD:** GitHub Actions

## Working Agreement

This repository is built in discrete, explicitly-scoped sprints. Each sprint report
includes every file created/modified, the updated repository tree, and test/validation
results, and stops for review before the next sprint begins.
