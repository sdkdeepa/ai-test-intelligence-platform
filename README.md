# AI Test Intelligence Platform

A reference-grade engineering platform that applies LLM-backed analysis to a codebase
and its test suite, with the governance and CI/CD scaffolding a real production system
around AI-generated output would need — not just the analysis itself.

## Problem Statement

Engineering teams routinely under-invest in three things because they're tedious to do
by hand and hard to automate with static analysis alone:

1. **Where is testing risk concentrated in a change?** Line/branch coverage tells you
   what's *tested*, not what's *risky* — a one-line change to an auth check and a
   hundred-line change to a logging format string look identical to a coverage tool but
   are not remotely equivalent in review priority.
2. **What tests should exist but don't?** Spotting an undertested code path requires
   understanding what the code *does*, not just how many lines are covered.
3. **Why did this test fail, and does it matter?** Regression, flake, or environment
   issue — CI failure triage is manual pattern-matching that scales badly with test
   suite size and team turnover.

An LLM can meaningfully help with all three, but "an LLM says so" is not the same thing
as "this is safe to merge." The harder, less-demoed problem is wiring that output into
an engineering workflow *responsibly*: never as a full generated-test-source dump into a
PR thread, never as a silent auto-approval, always with an audit trail and a human in
the loop for anything risky. That's what most of this platform's actual engineering
effort went into, and it's the part a from-scratch AI coding demo usually skips.

## Architecture

```mermaid
flowchart LR
    Dev[Developer] -->|opens/updates PR| GH[GitHub]
    GH -->|webhook, HMAC-signed| API[FastAPI API Layer]
    API --> Ing[Ingestion<br/>diff parsing, event normalization]
    Ing --> Orch[Orchestrator<br/>TaskQueue, async execution]
    Orch --> Risk[Risk Engine]
    Orch --> TestIntel[Test Intelligence Engine]
    Orch --> FailIntel[Failure Intelligence Engine]
    Risk --> Prov[Provider Abstraction<br/>Anthropic / Mock]
    TestIntel --> Prov
    FailIntel --> Prov
    Risk --> Gov[Governance<br/>policy rules, redaction]
    Gov -->|no rule triggered| Pub[GitHub Publisher]
    Gov -->|rule triggered| RQ[(Review Queue)]
    Human[Human Reviewer] -->|approve/reject| RQ
    RQ --> Pub
    Pub -->|status check + PR comment| GH
    Risk --> DB[(PostgreSQL)]
    TestIntel --> DB
    FailIntel --> DB
    Gov --> DB
    DB --> Dash[React Dashboard]
    Dash -->|pending approvals,<br/>findings, suggestions| Human
```

One pipeline — ingestion → orchestration → provider-backed analysis → persistence → API
→ dashboard — shared by all three analysis engines, with governance sitting on top of
the risk-analysis path specifically (the only path that produces an externally-visible
"approved" signal today). See [Architecture](docs/architecture.md) for the full component
breakdown, module dependency rules, and per-sprint implementation-status notes, and
[System Design](docs/system-design.md) for data flow sequence diagrams, the database
schema, and the API surface.

## Core Capabilities

| Capability | What it does | Status |
|---|---|---|
| Risk analysis | Scores a diff's release risk, categorizes it (auth/authz, API contract, schema, security-sensitive, etc.), and gives a release recommendation | Implemented |
| Test intelligence | Suggests specific tests for undertested/high-risk code, with rationale and confidence | Implemented |
| Failure intelligence | Classifies a CI failure as regression/flaky/environment from logs and stack traces | Implemented |
| GitHub PR integration | Webhook-triggered analysis, commit status + PR comment publishing | Implemented |
| Governance & human review | Policy-gated review queue, immutable audit trail, sensitive-data redaction | Implemented |
| CI webhook ingestion (non-PR test-run results) | Feeding raw CI test-run results in independently of a PR | Not implemented — see Production Gaps |
| Multi-provider LLM support | Anthropic Claude (real) + Mock (deterministic, free) implemented; the `LLMProvider` interface is provider-agnostic | OpenAI/other providers not implemented — interface supports it |

## AI vs Deterministic Responsibilities

The platform deliberately separates probabilistic analysis from deterministic
engineering controls.

### LLM-backed

- Semantic analysis of code changes
- Identification of potential release risk
- Test suggestions for undertested or high-risk code
- Failure classification and likely root-cause hypotheses
- Explanatory rationale for findings and recommendations

### Deterministic

- GitHub webhook signature verification
- Repository registration and event normalization
- Request and schema validation
- Rules that determine when Test Intelligence runs
- Governance policy thresholds and review requirements
- Sensitive-data redaction
- Audit-event persistence
- Human approve/reject decisions
- GitHub status and PR-comment publishing
- CI/CD execution

The LLM produces engineering intelligence; it does not independently authorize a
release. High-risk or policy-sensitive findings are evaluated by deterministic
governance rules and can require explicit human review before a final GitHub status is
published.

## Design Decisions & Trade-offs

Written down here so a reviewer doesn't have to reverse-engineer *why* from the code —
each of these was a real choice with a real alternative, not an oversight.

- **In-process `TaskQueue` (threads), not Celery/Temporal.** Simpler to run and reason
  about for a single-process reference deployment; the interface
  (`orchestration/queue.py`) is the seam a distributed queue would slot behind without
  touching any caller. Trade-off: no horizontal scaling of analysis workers, and a
  process restart loses in-flight (not yet-persisted) work.
- **SQLite for unit/component tests, PostgreSQL only for integration tests and
  production.** Keeps the fast test suite (~10s for 420 tests) free of a database
  dependency; `tests/persistence/postgres/` is what actually proves Postgres-specific
  behavior (JSON columns, migrations, FK enforcement). Trade-off: a bug that only
  manifests on Postgres (a stricter type, a locking behavior) won't be caught by the
  fast suite — `integration.yml` is what catches that class of gap, not `ci.yml`.
- **Statuses API, not the Checks API, for the GitHub commit status.** Checks requires a
  GitHub App installation (a different auth/identity model); Statuses works with a plain
  token, matching the rest of the integration's auth story. Trade-off: no rich Checks UI
  (annotations, requested re-runs) — see Future Evolution.
- **Governance policy is process-wide, not per-repository.** One set of thresholds
  (`GOVERNANCE_*` env vars) for every registered repository. Simpler to configure and
  reason about; the real trade-off is that a monorepo with wildly different risk
  tolerances per subproject can't express that yet.
- **PR comments never include full model output** (full rationale text, full generated
  test source) **by design**, not as a token-budget optimization — a concise, capped
  summary plus a link to the full detail in the dashboard. This is a deliberate scope
  boundary on what belongs in PR history versus what belongs in a reviewed UI, decided
  before it became a token-cost problem.
- **No authentication/authorization model.** Every API endpoint is open; CORS is
  wildcard. This is the single largest gap between "reference implementation" and
  "production-ready" — see Production Gaps. It was deferred deliberately rather than
  built partially, since a half-built auth model creates a false sense of security worse
  than no auth model plus an honest README section about it.
- **Redaction is pattern-based over secret *shapes*, not a secrets-manager
  integration.** Catches AWS/GitHub/Slack tokens, PEM blocks, and generic
  password/secret assignments by regex before they reach an LLM call or the audit log.
  Trade-off: it's a safety net, not a guarantee — a secret in an unrecognized format
  will not be caught. See `backend/app/governance/redaction.py`'s module docstring for
  why it targets values, not the security-related keywords the risk/test-intelligence
  heuristics themselves depend on.
- **Repository removal is soft-delete (an `is_active` flag), not a `DELETE` endpoint.**
  A registered repository accumulates `AnalysisRun`/`RiskFinding`/`ReviewRequest`/
  `AuditEvent` rows that reference it by foreign key; hard-deleting the row would either
  cascade-destroy that history — directly contradicting the immutable-audit-trail
  guarantee `AuditEvent` exists for — or leave orphaned rows behind. Archiving
  (`POST /repositories/{id}/archive`) removes a repository from the default list view
  and stops it accepting new analysis (manual trigger or webhook) while leaving every
  row that already references it fully intact. This is a distinct concern from
  *retention* at scale — see Future Evolution.

## Example Workflow

1. A developer opens a PR that touches `app/auth/login.py`.
2. GitHub sends a signed `pull_request` webhook to `POST /api/v1/webhooks/github`.
3. The platform verifies the signature, fetches the PR's diff, and triggers Risk
   analysis (always) and Test Intelligence analysis (since the diff touches non-test
   source).
4. The Risk Engine scores the change, detects the `authentication_authorization`
   category, and produces a risk assessment.
5. Governance policy evaluates that assessment: the auth-change category trips a rule.
   Instead of an automatic commit status, the platform publishes a `pending` status and
   a short PR comment noting review is required, and creates a review request — visible
   at `/review-queue` in the dashboard, with an immutable `policy_evaluated` +
   `review_required` audit trail already recorded.
6. A reviewer opens the dashboard, sees the flagged request with its risk summary and
   reasons, and calls `POST /api/v1/review-queue/{id}/approve` with their identity and
   an optional reason.
7. The platform records the decision (another immutable audit event), then publishes
   the final `success` commit status and a decision comment back to the PR.
8. The developer sees a green check and a clear paper trail of who approved it and why —
   never an AI-generated status that resolved itself.

## Screenshots

The dashboard running locally against `MockProvider` — no real LLM calls, no external
accounts. See Try It Yourself Locally below to reproduce any of these.

**Repository Overview** — registered repositories, with the archive/soft-delete toggle
(deactivates a repo without destroying its analysis history — see Design Decisions).

![Repository Overview](docs/screenshots/01-repository-overview.png)

**Risk Analysis** — a triggered assessment: deterministic heuristic score, category
detection, and the provider's assessment side by side.

![Risk Analysis](docs/screenshots/02-risk-analysis.png)

**Test Suggestions** — generated suggestions with confidence, supporting evidence, and
an accept/reject decision per suggestion.

![Test Suggestions](docs/screenshots/03-test-suggestions.png)

**Failure Intelligence** — a classified CI failure (regression, in this case) with
factual evidence, root-cause hypotheses, and concrete debugging recommendations.

![Failure Intelligence](docs/screenshots/04-failure-intelligence.png)

**Pending Approvals** — a risk result governance flagged (low confidence, in this case)
before it can be treated as approved, with the reviewer identity + reason form that
records the decision.

![Pending Approvals](docs/screenshots/05-pending-approvals.png)

**Analysis Run History** — every run for a repository with per-run LLM invocation
detail (provider, model, tokens, latency, cost) expandable inline.

![Analysis Run History](docs/screenshots/06-analysis-run-history.png)

Not pictured: a GitHub PR showing the published commit status + comment — requires a
real webhook pointed at a publicly reachable URL (see GitHub PR Integration below),
more setup than the rest and skippable for evaluating the platform itself.

## Local Setup

Requires Python 3.12+, Node 22+, and a running PostgreSQL instance — the default
`DATABASE_URL` (see `backend/app/persistence/config.py`) points at
`postgresql+psycopg://postgres:postgres@localhost:5432/ai_test_intelligence`. Easiest
way to get Postgres running is `docker compose up -d postgres` (uses the same service
defined in `docker-compose.yml`, without also building the backend/frontend images);
a local Postgres install works equally well if you point `DATABASE_URL` at it in `.env`.

```
cp .env.example .env
make install        # backend venv + dependencies, frontend npm dependencies
make migrate         # apply database migrations — required before first run, and again
                      # after pulling any change that adds a migration (see migrations/versions/)
make backend         # run the API at http://localhost:8000 (see /health)
make frontend        # run the dashboard dev server (separate terminal) — http://localhost:5173
make test            # run backend tests
make test-cov        # run backend tests with coverage (term + html + xml)
make lint            # ruff check + ruff format --check + mypy
make test-frontend   # run frontend component tests (Vitest)
make e2e             # run Playwright e2e tests (starts its own backend + frontend)
```

If `/review-queue` or any repository-scoped page fails with a `psycopg.errors.UndefinedTable`
error, `make migrate` hasn't been run against the database `DATABASE_URL` currently points
at — this is the single most common local-setup gap, since `make install` only sets up
dependencies and does not touch the database.

Or via Docker:

```
docker compose up --build
```

Backend serves on `:8000`, frontend on `:4173` when run via Docker (`:5173` under
`npm run dev`). Both Dockerfiles run as a non-root user and define a `HEALTHCHECK`
against their own serving port. Migrations are not run automatically on container
startup — run `make migrate` (or `docker compose exec backend alembic upgrade head`)
against the compose-managed Postgres the first time, same as the non-Docker path above.

Every provider integration (Anthropic, GitHub) falls back to a safe no-op without
credentials configured — `MockProvider` for LLM calls, `NullGitHubClient` for the GitHub
API — so the platform runs end-to-end locally with zero external accounts required.
`GOVERNANCE_ENABLED=false` additionally disables the review-queue gate for local
iteration, if you want every risk result to auto-approve while developing.

## Try It Yourself Locally

With the backend and frontend both running (`make backend`, `make frontend`), the
fastest way to see every core capability work end to end, with zero external accounts:

1. Register a repository from the dashboard's **Repositories** page (any name/URL —
   nothing needs to resolve to a real GitHub repo for manual triggering).
2. Open the repo, go to **Risk Analysis**, and paste a diff into the Diff field. Two
   worth trying:
   - A routine change (auto-approves, shows up immediately in Risk Findings):
     ```
     diff --git a/app/utils/formatting.py b/app/utils/formatting.py
     index 1111111..2222222 100644
     --- a/app/utils/formatting.py
     +++ b/app/utils/formatting.py
     @@ -3,3 +3,3 @@
     -    return f"{m}m"
     +    return f"{m}m {s}s"
     ```
   - An authentication-touching change (trips governance — check **Pending Approvals**
     in the nav afterward instead of Risk Findings):
     ```
     diff --git a/app/auth/login.py b/app/auth/login.py
     index 1111111..2222222 100644
     --- a/app/auth/login.py
     +++ b/app/auth/login.py
     @@ -10,8 +10,8 @@ def handle_login(username, password):
          user = find_user(username)
          if user is None:
              raise ValueError("unknown user")
     -    if not check_password(user, password):
     +    if not authenticate(user, password):
              raise ValueError("invalid credentials")
     ```
3. On the **Test Suggestions** tab, the trigger form takes source code + a requirement
   description rather than a diff (test-coverage gaps are about the code's current
   state, not what changed — see Design Decisions). Try a deliberate gap between the
   two, e.g. code that only validates one of two inputs a requirement describes:
   ```python
   def calculate_discount(price, discount_percent):
       if discount_percent < 0 or discount_percent > 100:
           raise ValueError("discount_percent must be between 0 and 100")
       return price - (price * discount_percent / 100)
   ```
   with the requirement text `The discount calculation should reject negative prices
   and should return the original price unchanged when discount_percent is 0.`

**On `MockProvider`'s output specifically**: since it's not a real LLM, its response
can't be parsed into a structured suggestion — every result you get locally by default
will show *"the provider response could not be parsed as JSON... deterministic
fallback"* and a `# TODO:` stub instead of real generated content. That's not a bug;
it's the engine's own graceful-degradation path (see `analysis/*/engine.py`), and it's
exercised by design so the platform is fully clickable without an API key. Configure
`PROVIDER_ANTHROPIC_API_KEY` + `PROVIDER_DEFAULT_PROVIDER=anthropic` to see real
generated output instead — optional, and it spends real API budget.

## AI Evaluation Strategy

The automated test suites described below validate that the platform behaves correctly
as software. AI evaluation is a separate concern: it asks whether the intelligence
produced by the platform is accurate, useful, and stable enough to trust in an
engineering workflow.

The repository already has a foundation for this — `observability/eval_datasets.py`'s
three representative-scenario datasets (risk analysis, test intelligence, failure
intelligence) and `experiments.py`'s replay mechanism, both LangSmith-backed and
optional (see [Architecture §8](docs/architecture.md#8-observability-strategy)). But
that foundation is explicitly not a grading harness: `experiments.py`'s own docstring
calls it out — no automated scoring, no baseline comparison, no CI gate. A versioned
golden-dataset pipeline with regression detection is the next layer to build on top of
that foundation, not a from-scratch build.

Evaluation should be capability-specific:

### Risk Analysis

Evaluate:

- risk-category classification accuracy
- recall on known high-risk changes
- false-positive rate on low-risk changes
- evidence quality
- release-recommendation accuracy
- confidence calibration

### Test Intelligence

Evaluate:

- relevance of suggested tests
- coverage of important edge and negative cases
- duplicate or redundant suggestions
- executability of generated tests where source is produced
- usefulness of rationale

### Failure Intelligence

Evaluate:

- regression/flaky/environment classification accuracy
- likely root-cause accuracy
- confidence calibration
- debugging-recommendation usefulness

### Golden Dataset

A production evaluation suite should be versioned and include representative examples
such as:

- low-risk and high-risk code changes
- authentication/authorization changes
- API and schema changes
- security-sensitive changes
- known historical regressions
- flaky tests
- environment failures
- ambiguous or insufficient-evidence cases

Deterministic checks should be used wherever the expected property is deterministic,
such as schema validity or required fields. Semantic quality can use task-specific
scoring, carefully calibrated model-based evaluation, and human review where necessary.

Prompt, model, provider, and evaluation-dataset changes should be evaluated against a
stable baseline before promotion so that quality regressions are visible rather than
hidden behind a successful software test run.

## Testing Strategy

- **420 backend tests** (pytest), **96% line coverage**, run in ~10-15s with zero
  external dependencies (`MockProvider`, in-memory SQLite).
- **36 frontend component tests** (Vitest + React Testing Library).
- **PostgreSQL integration suite** (`tests/persistence/postgres/`) — migrations, FK
  enforcement, and repository behavior against a real Postgres 16 instance.
- **Playwright e2e** (`frontend/e2e/`) — the primary user flows against a real backend
  (MockProvider, disposable SQLite) and a real Vite dev server.
- **Provider contract tests** — a shared suite run against every `LLMProvider`
  implementation, including a manually-triggered live-Anthropic variant that never runs
  in automatic CI.
- **Webhook/governance integration tests** — the full webhook → policy evaluation →
  review queue → approve/reject → GitHub-publish loop, driven with a fake `GitHubClient`
  and no live repository or network access.

Full breakdown, including what each suite deliberately does *not* cover, in
[Architecture §9](docs/architecture.md#9-testing-strategy).

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

## Production Gaps

This is a reference implementation, not a deployed production system. The following
gaps are **known and deliberate** — flagged here explicitly rather than left for a
reviewer to discover, per the Sprint 14 hardening review this section is a product of:

- **No authentication/authorization model.** Every API endpoint is open; CORS is
  wildcard. This is the largest gap. A production deployment needs this before it's
  reachable from anywhere but a trusted internal network.
- **No multi-tenancy.** One shared database, one shared governance policy configuration,
  no tenant isolation.
- **No horizontal scaling of analysis workers.** The in-process `TaskQueue` (threads)
  doesn't survive a process restart or scale beyond one process — see Design Decisions.
- **Governance policy is process-wide, not per-repository.** A monorepo or
  multi-team deployment can't express different risk tolerances per project yet.
- **No rate limiting** on any endpoint, including the GitHub webhook receiver.
- **No secrets-manager integration.** `GITHUB_API_TOKEN`, `PROVIDER_ANTHROPIC_API_KEY`,
  and `GITHUB_WEBHOOK_SECRET` are plain environment variables — fine for this reference
  deployment, not for a real one holding real repository access tokens.
- **Redaction is a regex safety net, not a guarantee.** It catches recognizable secret
  *shapes*; a credential in an unrecognized format passes through unredacted.
- **The Docker healthcheck only proves the process is alive and serving HTTP**, not that
  the database is reachable — a real production readiness probe needs to check that too.
- **No OpenTelemetry tracing** across ingestion → orchestration → provider call →
  persistence — structured logging and LangSmith tracing exist, distributed tracing
  does not.
- **CI webhook ingestion (raw CI test-run results, independent of a PR) is not
  implemented** — only the PR-triggered path exists today.
- **No database backup/restore strategy documented or automated.**
- **Every status-column enum (`analysis_runs.status`, `test_suggestions.status`, etc.)
  except `review_requests.status` is validated at the application level only, not with a
  database CHECK constraint** — Sprint 14 closed the gap for the newest, governance-
  critical table; the others remain application-validated-only by scope decision, not
  because the gap wasn't noticed.

## Scaling to 10x Usage

See Production Gaps above for what's missing today; this section describes how those
gaps would actually get closed under materially higher load, not a separate list.

The current architecture is intentionally optimized for a single-process reference
deployment. At materially higher usage, the first architectural pressure would be the
in-process `TaskQueue`: analysis work is tied to one process, in-flight work is not
durable, and LLM-provider rate limits become a shared bottleneck.

At roughly 10x usage, the architecture would evolve without changing the three
intelligence engines themselves:

1. **Move analysis jobs to a durable distributed queue** behind the existing
   `TaskQueue` interface, using a system such as Celery or Temporal, so API ingestion
   and analysis execution can scale independently.
2. **Run analysis asynchronously with horizontally-scaled workers**, keeping webhook
   handling fast while longer model calls execute outside the request path.
3. **Persist job state before execution** so process or worker restarts do not lose
   accepted work, and use idempotency controls to avoid duplicate analysis from repeated
   webhook delivery.
4. **Introduce provider-level concurrency and rate-limit controls**, including bounded
   retries and backpressure rather than allowing traffic spikes to fan out directly to
   the model provider.
5. **Add per-repository or per-team governance configuration** instead of the current
   process-wide thresholds.
6. **Add authentication, RBAC, and tenant isolation** before supporting multiple teams
   on shared infrastructure.
7. **Add production observability and cost controls**, including distributed tracing,
   queue depth, worker saturation, provider latency/error rates, token usage, and
   per-team usage budgets.
8. **Scale persistence deliberately**, with PostgreSQL connection pooling, backup and
   restore procedures, retention policies, and indexing driven by actual query and
   audit-volume patterns.

Caching would be applied selectively. Stable metadata or reusable repository context may
be cacheable, but risk decisions and governance outcomes should not be blindly reused
across commits because the code, evidence, model version, prompt version, or policy may
have changed.

## Future Evolution

Natural next increments, roughly in order of likely value:

1. **Authentication/authorization** — the prerequisite for deploying this anywhere
   multi-user or internet-reachable.
2. **A GitHub App integration** replacing the Statuses-API approach, unlocking the
   Checks API's richer UI (annotations, requested re-runs) without changing the
   underlying webhook/governance flow.
3. **A distributed task queue** (Celery or Temporal) behind the existing `TaskQueue`
   interface, once real concurrency demands outgrow a single process.
4. **Per-repository governance policy configuration**, letting a monorepo or
   multi-team deployment express different risk tolerances per project.
5. **CI webhook ingestion** for raw test-run results, completing the Failure
   Intelligence Engine's trigger path independent of a PR.
6. **OpenTelemetry tracing** across the full request/analysis lifecycle.
7. **Additional LLM providers** (the `LLMProvider` interface already supports this;
   only Anthropic and Mock are implemented today).
8. **Tiered data retention for high-volume tables** (`analysis_runs`, `risk_findings`,
   `llm_invocations`) — distinct from repository archiving above, and worth being
   explicit about the difference: archiving a repository is small (one row, `{id, name,
   url, ...}`) and reversible, aimed at "stop this repo from cluttering my view." At real
   scale, the tables that actually grow unbounded are the ones recording *every analysis
   run*, not the repository list itself. `audit_events` specifically should never be
   time-boxed the way the others could — it's the compliance record Sprint 13's
   governance model exists to produce, and a 30/60-day retention window there would
   defeat the point (see Governance and Human Review). A sound version of this feature
   varies retention by table: aggressive pruning for raw `llm_invocations` latency/cost
   logs nobody needs after a few months, longer or indefinite retention for
   `risk_findings`/`audit_events`, with cold storage rather than deletion where the data
   has long-tail value (a team's risk-trend history) but doesn't need to stay query-fast.
