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
GitHub pull requests and CI webhooks. A governance layer sits on top: AI-generated risk
findings are advisory, not self-executing — certain conditions (high risk, low
confidence, auth/authz or breaking-change categories, security-sensitive findings,
insufficient evidence) route a result into a human review queue before it can be treated
as an approved signal anywhere outside the platform's own dashboard.

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
- **GitHub integration:** PR webhook ingestion, risk + test-suggestion analysis
  triggering, commit status + PR comment publishing (see GitHub PR Integration below)
- **Governance:** configurable policy rules gate risk results into a human review queue
  before they can be treated as approved; immutable audit trail; sensitive-data
  redaction before any LLM call or audit write (see Governance and Human Review below)
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

## GitHub PR Integration

The platform can trigger AI-backed analysis directly from GitHub pull requests and
publish the results back as a commit status check and a PR comment.

**Setup:**

1. Register the repository with the platform first (`POST /api/v1/repositories`) — the
   webhook is ignored for any repository whose GitHub URL isn't already registered.
2. Set two environment variables (see `.env.example`):
   - `GITHUB_WEBHOOK_SECRET` — required. Requests without a valid
     `X-Hub-Signature-256` HMAC-SHA256 signature against this secret are rejected with
     401. The webhook endpoint fails closed if this isn't set at all.
   - `GITHUB_API_TOKEN` — required to actually fetch PR diffs and publish status
     checks/comments back to GitHub. Without it, webhooks are still received and
     verified and analysis still runs, but nothing is published back to GitHub (a
     `NullGitHubClient` no-ops the outbound calls, same "no key, no provider" pattern
     `PROVIDER_ANTHROPIC_API_KEY` follows).
3. Point a GitHub webhook at `POST /api/v1/webhooks/github` for the `pull_request` event,
   using the same secret as `GITHUB_WEBHOOK_SECRET`.

**What happens on `opened` / `synchronize` / `reopened`:**

- Risk analysis is always triggered.
- Test Intelligence analysis is triggered only when the diff touches non-test source
  (a deterministic heuristic — no LLM call spent deciding this).
- Once analysis completes, governance policy (see Governance and Human Review below) is
  checked first. If nothing triggers: a commit status check (`ai-test-intelligence/risk`
  context) and a single PR comment are published, covering overall risk, top findings,
  recommended tests (when triggered), and a link back to the full analysis in the
  platform dashboard. **The comment never includes full model output** — no raw AI
  rationale text, no full generated test source — by design. If a policy rule triggers:
  a `pending` status and a "human review required" comment are published instead, and
  the run waits in the review queue until a human approves or rejects it.

## Governance and Human Review

Risk findings are advisory, not self-executing. A completed risk assessment is checked
against a fixed set of policy rules before it's allowed to become a `success`/`failure`
commit status on a PR (or, for manually-triggered runs, before it's treated as resolved
at all):

- high release risk (a `block` recommendation, or `risk_score` over a threshold)
- low confidence (`confidence_score` under a threshold)
- authentication/authorization changes
- breaking API or schema changes
- security-sensitive findings
- insufficient evidence for an elevated-risk claim

Any triggered rule creates a **review request** — visible at `/review-queue` in the
dashboard — and, for webhook-originated runs, replaces the automatic status/comment with
a `pending` status and a short "review required" note. Nothing publishes a final
success/failure status for that run except a human decision: `POST
/api/v1/review-queue/{id}/approve` or `/reject`, each requiring a reviewer identity and
accepting an optional reason. Every step — the policy check itself, a triggered
requirement, and the eventual decision — is recorded as an **immutable audit event**
(`GET /api/v1/review-queue/{id}/audit-events`); there is no code path that updates or
deletes one once written. Any sensitive-looking values (API keys, tokens, private key
blocks, password/secret assignments) are redacted before they reach either an LLM
provider or the audit log — see `backend/app/governance/redaction.py`.

Policy thresholds are configurable via environment variables (see `.env.example`,
`GOVERNANCE_*`); `GOVERNANCE_ENABLED=false` disables the gate entirely (every result
auto-approves), which is useful for local development. See
[architecture.md §12](docs/architecture.md#12-governance-and-human-review) for the full
design.

