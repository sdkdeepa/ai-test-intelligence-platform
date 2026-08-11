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

## Documentation

- [Architecture](docs/architecture.md) — high-level architecture, component diagram,
  repository layout, module organization, provider abstraction, observability, testing,
  and CI/CD strategy.
- [System Design](docs/system-design.md) — data flow diagrams, database schema, and API
  boundaries.

## Stack

- **Backend:** Python 3.12, FastAPI, Pydantic Settings, structlog
- **Frontend:** React, TypeScript, Vite, React Router, TanStack Query
- **LLM providers:** Anthropic Claude (primary), Mock (test/CI) — OpenAI not yet implemented
- **Persistence:** PostgreSQL, SQLAlchemy 2.0, Alembic
- **Observability:** Prometheus-compatible `/metrics`, structured JSON logging, optional
  LangSmith trace/experiment/dataset integration (disabled by default — see
  `docs/architecture.md`)
- **CI/CD:** GitHub Actions — lint/type/unit (`ci.yml`), PostgreSQL integration
  (`integration.yml`), Playwright e2e (`e2e.yml`), Docker build + compose validation
  (`docker.yml`); all required on `main`. A separate, manually-triggered workflow
  (`live-smoke.yml`) covers the real Anthropic provider — see CI/CD below.

## Getting Started

Requires Python 3.12+, Node 22+, and (optionally) Docker.

```
cp .env.example .env
make install     # backend venv + dependencies, frontend npm dependencies
make backend     # run the API at http://localhost:8000 (see /health)
make frontend    # run the dashboard dev server (separate terminal) — http://localhost:5173
make test        # run backend tests
make test-cov    # run backend tests with coverage (term + html + xml)
make lint        # ruff check + ruff format --check + mypy
make test-frontend  # run frontend component tests (Vitest)
make e2e         # run Playwright e2e tests (starts its own backend + frontend)
```

Or via Docker:

```
docker compose up --build
```

Backend serves on `:8000`, frontend on `:4173` when run via Docker (`:5173` under
`npm run dev`).

## CI/CD

Everything below runs against `MockProvider` (`PROVIDER_DEFAULT_PROVIDER=mock`, the
default) — no automatic workflow ever calls a real LLM or spends API budget. Four
workflows are required checks on `main`; a fifth is opt-in and manual.

| Workflow | Trigger | What it checks |
|---|---|---|
| `ci.yml` | every push/PR | Backend: Ruff lint, Ruff format check, mypy, PyTest (incl. API contract tests under `tests/api/`) with coverage. Frontend: oxlint, Vitest component tests, production build (`tsc -b && vite build`). |
| `integration.yml` | every push/PR | Spins up a PostgreSQL 16 service container, runs Alembic migrations (upgrade to head, then a downgrade/upgrade round trip) and the repository-layer integration suite against it — see `tests/persistence/postgres/`. |
| `e2e.yml` | every push/PR | Installs Playwright + Chromium and runs `frontend/e2e/` (`playwright.config.ts`) against a real backend (MockProvider, disposable SQLite) and a real Vite dev server, both started by Playwright itself. |
| `docker.yml` | every push/PR | Builds the backend and frontend Docker images independently, then validates `docker-compose.yml` (`docker compose config` + `docker compose build`). Build-only — nothing is pushed to a registry. |
| `live-smoke.yml` | **manual** (`workflow_dispatch`) only | Runs `tests/providers/test_anthropic_live.py` against the real Anthropic API, using an `ANTHROPIC_API_KEY` repository secret. The only workflow permitted to make paid calls; never runs automatically. |

Test results, coverage reports, and the Playwright HTML report are uploaded as workflow
artifacts (14-day retention) on every run, pass or fail, so a CI failure can be
diagnosed without re-running locally.

