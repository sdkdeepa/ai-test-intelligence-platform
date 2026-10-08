# AI Test Intelligence Platform

A reference implementation for analyzing pull-request risk, suggesting targeted tests, and investigating CI failures. LLMs generate findings and explanations; deterministic policy and human review control release-related actions.

![Architecture](docs/screenshots/architecture.png)

## What it does

| Capability | Behavior |
| --- | --- |
| Risk analysis | Reviews diffs, identifies sensitive changes, and recommends a risk level |
| Test intelligence | Suggests tests for changed or undertested code, with rationale and confidence |
| Failure intelligence | Classifies test failures and proposes debugging hypotheses |
| GitHub integration | Accepts signed PR webhooks and publishes commit statuses and concise comments |
| Governance | Applies policy thresholds, routes sensitive findings for review, and records audit events |

The application supports Anthropic Claude and a deterministic mock provider. OpenAI is not implemented. CI test-run webhook ingestion is also not implemented; see [Limitations](#limitations).

## Request flow

1. GitHub sends a signed PR event; the backend verifies it and retrieves the diff.
2. Background analysis produces risk findings and, for non-test source changes, test suggestions.
3. Deterministic governance policy decides whether human review is required.
4. The platform publishes a concise GitHub status/comment, or a pending status until a reviewer approves or rejects the finding.
5. The dashboard shows analysis details, review decisions, and audit history.

The model never independently approves a release. See [Architecture](docs/architecture.md) for component boundaries and [System design](docs/system-design.md) for detailed request flows.

## Technology

Python, FastAPI, Pydantic, React, TypeScript, PostgreSQL, SQLite for fast tests, Anthropic Claude, GitHub webhooks/Statuses API, Docker, GitHub Actions, pytest, and frontend tests. A mock provider supports local development without paid model calls.

## Local setup

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

## Try it locally

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

## Dashboard

![Repository Overview](docs/screenshots/01-repository-overview.png)

![Risk Analysis](docs/screenshots/02-risk-analysis.png)

![Test Suggestions](docs/screenshots/03-test-suggestions.png)

![Failure Intelligence](docs/screenshots/04-failure-intelligence.png)

![Pending Approvals](docs/screenshots/05-pending-approvals.png)

![Analysis Run History](docs/screenshots/06-analysis-run-history.png)

## Testing and CI

Run the backend and frontend test commands documented in the setup sections above. The fast backend suite uses SQLite; PostgreSQL-specific behavior is exercised separately in integration tests. CI also checks formatting, frontend tests, and build paths. Mock-provider testing does not require model API credentials.

## Design trade-offs

- **Provider boundary:** model-specific calls stay behind `LLMProvider`; the deterministic mock supports reproducible tests.
- **Background queue:** an in-process thread queue is simple locally, but does not provide durable jobs or horizontal worker scaling.
- **Persistence:** SQLite keeps component tests fast; PostgreSQL integration tests catch database-specific differences.
- **GitHub Statuses API:** avoids requiring a GitHub App, but lacks richer Checks API annotations.
- **Human review:** policy, not model output, determines when review is required; comments deliberately omit full generated test source.

Additional implementation decisions are in [Architecture](docs/architecture.md).

## Limitations

This is a reference implementation, not a deployed multi-tenant service. It does not provide application-wide authentication/authorization; the API and permissive CORS settings are unsuitable for public exposure. Policy thresholds are process-wide, redaction is pattern-based rather than comprehensive, and the in-process queue loses unfinished jobs on restart. CI-result webhook ingestion and additional model providers remain future work.

See [Architecture](docs/architecture.md) for the corresponding scaling and security trade-offs.
