# Development Roadmap

This roadmap sequences the work described in [architecture.md](architecture.md) and
[system-design.md](system-design.md) into sprints. It is a proposal for ordering, not a
commitment — each sprint below still requires explicit go-ahead before starting, per the
project's working agreement. Nothing past the current sprint is implemented by default.

## Sequencing Principles

1. **Bottom-up through the dependency chain.** `architecture.md §5` establishes
   `api`/`ingestion` → `orchestration` → `analysis engines` → `providers`/`persistence`
   as the dependency direction. We build from the bottom of that chain up, so every
   sprint has something real underneath it to integrate against instead of scaffolding
   against interfaces that don't exist yet.
2. **One engine before three.** All three analysis engines share the same
   orchestration/provider/persistence spine, so proving that spine end-to-end with one
   engine (Risk, the least generative and easiest to validate) de-risks the other two
   before they're built.
3. **Deterministic before live.** The `MockProvider` and provider abstraction land
   before any real Anthropic/OpenAI integration, so the test suite and CI are never
   blocked on external API access.
4. **Dashboard after data exists.** Frontend work starts once there's at least one real
   API endpoint returning real findings — building UI against a schema that might still
   change wastes effort.

## Sprint Sequence (Proposed)

| Sprint | Focus | Depends on |
|---|---|---|
| 0 | Architecture & design (this sprint) | — |
| 1 | Repo scaffolding: backend/frontend skeletons, tooling, local dev environment, base CI (`ci.yml`) | Sprint 0 |
| 2 | Provider abstraction: `LLMProvider` interface, `PromptSpec`/`LLMResponse`, `MockProvider`, `ProviderRegistry` — deterministic and config-driven; no real provider yet | Sprint 1 |
| 3 | Persistence layer: SQLAlchemy models, Alembic migrations, repository pattern for core entities | Sprint 1 |
| 4 | Orchestration: `TaskQueue` interface + in-process implementation, `AnalysisEngine` interface | Sprints 2, 3 |
| 5 | Risk Engine (first full vertical slice): ingestion → orchestration → risk analysis → persistence → API read endpoint | Sprint 4 |
| 6 | CI integration test workflow (`integration.yml`) against dockerized Postgres | Sprint 5 |
| 7 | Test Intelligence Engine | Sprint 5 |
| 8 | Triage Engine + flaky-test clustering | Sprint 5 |
| 9 | Frontend dashboard: repo overview + risk findings view | Sprint 5 |
| 10 | GitHub PR integration: status checks, PR comments with findings | Sprints 5–8 |
| 11 | Observability: structured logging, metrics endpoint, tracing | Ongoing, formalized once real traffic exists |

Sprints 7, 8, and 9 are independent of each other once Sprint 5 lands and may be
reordered based on priority at that time.

## Explicitly Deferred Decisions

These are acknowledged gaps, tracked here so they aren't silently forgotten:

- **Authentication/authorization model** — no auth exists until a sprint explicitly
  scopes it. Needed before any real deployment.
- **Multi-tenancy** — current schema assumes a single organization's repositories;
  tenant isolation is a schema and API-layer decision to make deliberately, not retrofit.
- **Deployment target** — container platform, serverless, or PaaS is undecided; local
  Docker Compose is sufficient through at least Sprint 6.
- **Distributed task queue** — Celery/Temporal replacing the in-process `TaskQueue`
  implementation, triggered by actual concurrency needs, not anticipated ones.
- **Versioning/release process** — deferred until there's a deployable artifact.
- **Real provider integration (`AnthropicProvider`/`OpenAIProvider`)** — deliberately not
  bundled into Sprint 2. The Risk Engine's first vertical slice (Sprint 5) is expected to
  run on `MockProvider`; wiring a real provider behind the existing `ProviderRegistry` is
  its own future sprint, gated on there being a live-provider smoke-test workflow to keep
  it out of normal CI (see `architecture.md §10`).

## Sprint Log

- **Sprint 0 (2026-08-06):** Architecture and system design established. No application
  code written. Deliverables: this roadmap, `architecture.md`, `system-design.md`,
  updated `README.md`.
- **Sprint 1 (2026-08-06):** Repository scaffold and development foundation. FastAPI
  backend (health endpoint, config, structured logging), React/Vite/TS frontend shell,
  Dockerfiles, `docker-compose.yml`, `Makefile`, `.env.example`. No business logic.
- **Sprint 2 (2026-08-07):** Provider abstraction. `LLMProvider` interface, `PromptSpec`/
  `LLMResponse` models, deterministic `MockProvider`, `ProviderSettings`,
  `ProviderRegistry` resolving providers per analysis engine from configuration. No real
  provider, analysis engine, or persistence code — see the scoping notes in
  `architecture.md §7`.
