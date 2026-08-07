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

**Sprint 1 complete: repository scaffold and development foundation.** A running
FastAPI backend (health endpoint, config, structured logging) and a React/Vite/TS
frontend shell exist and are containerized. No business logic, providers, or analysis
engines are implemented yet — see [Development Roadmap](docs/development-roadmap.md)
for what's next.

## Documentation

- [Architecture](docs/architecture.md) — high-level architecture, component diagram,
  repository layout, module organization, provider abstraction, observability, testing,
  and CI/CD strategy.
- [System Design](docs/system-design.md) — data flow diagrams, database schema, and API
  boundaries.
- [Development Roadmap](docs/development-roadmap.md) — sprint sequencing and explicitly
  deferred decisions.

## Stack

- **Backend:** Python 3.12, FastAPI, Pydantic Settings, structlog
- **Frontend:** React, TypeScript, Vite
- **LLM providers:** Anthropic Claude (primary), OpenAI (secondary), Mock (test/CI) — not yet implemented (Sprint 3)
- **Persistence:** PostgreSQL, SQLAlchemy 2.0 — not yet implemented (Sprint 2)
- **CI/CD:** GitHub Actions — not yet implemented

## Getting Started

Requires Python 3.12+, Node 22+, and (optionally) Docker.

```
cp .env.example .env
make install     # backend venv + dependencies, frontend npm dependencies
make backend     # run the API at http://localhost:8000 (see /health)
make frontend    # run the dashboard dev server (separate terminal)
make test        # run backend tests
```

Or via Docker:

```
docker compose up --build
```

Backend serves on `:8000`, frontend on `:4173` when run via Docker (`:5173` under
`npm run dev`).

## Working Agreement

This repository is built in discrete, explicitly-scoped sprints. Each sprint report
includes every file created/modified, the updated repository tree, and test/validation
results, and stops for review before the next sprint begins.
