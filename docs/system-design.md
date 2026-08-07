# System Design

Companion to [architecture.md](architecture.md). This document covers data flow,
database schema, and API boundaries in detail.

## 1. Data Flow: PR-Triggered Analysis

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant GH as GitHub Actions
    participant API as API Layer
    participant Ing as Ingestion Service
    participant Orch as Orchestrator
    participant Risk as Risk Engine
    participant Gen as Test Intelligence Engine
    participant Prov as Provider Abstraction
    participant DB as PostgreSQL

    Dev->>GH: Open / update PR
    GH->>API: POST /webhooks/github (PR event)
    API->>Ing: normalize event
    Ing->>Orch: enqueue AnalysisRun(type=risk, generation)
    Orch->>Risk: run(context)
    Orch->>Gen: run(context)
    Risk->>Prov: generate(risk prompt)
    Prov-->>Risk: LLMResponse
    Risk->>DB: write RiskFindings
    Gen->>Prov: generate(test suggestion prompt)
    Prov-->>Gen: LLMResponse
    Gen->>DB: write TestSuggestions
    Orch->>DB: mark AnalysisRun complete
    API->>GH: POST status check + PR comment
    GH-->>Dev: Check result visible on PR
```

## 2. Data Flow: CI Failure Triage

```mermaid
sequenceDiagram
    participant CI as CI Test Run
    participant API as API Layer
    participant Ing as Ingestion Service
    participant Orch as Orchestrator
    participant Triage as Triage Engine
    participant Prov as Provider Abstraction
    participant DB as PostgreSQL

    CI->>API: POST /webhooks/ci (test results)
    API->>Ing: normalize test run + results
    Ing->>DB: persist TestRun, TestResults
    Ing->>Orch: enqueue AnalysisRun(type=triage)
    Orch->>Triage: run(context: failed TestResults)
    Triage->>DB: read historical TestResults for same TestCase
    Triage->>Prov: generate(triage prompt)
    Prov-->>Triage: LLMResponse (classification + rationale)
    Triage->>DB: write FlakyTestFindings / classification
    Orch->>DB: mark AnalysisRun complete
```

## 3. Database Schema (High-Level)

```mermaid
erDiagram
    REPOSITORIES ||--o{ COMMITS : has
    REPOSITORIES ||--o{ ANALYSIS_RUNS : has
    REPOSITORIES ||--o{ TEST_CASES : has
    COMMITS ||--o{ TEST_RUNS : triggers
    TEST_RUNS ||--o{ TEST_RESULTS : produces
    TEST_CASES ||--o{ TEST_RESULTS : recorded_in
    TEST_CASES ||--o{ FLAKY_TEST_FINDINGS : flagged_in
    ANALYSIS_RUNS ||--o{ RISK_FINDINGS : produces
    ANALYSIS_RUNS ||--o{ TEST_SUGGESTIONS : produces
    ANALYSIS_RUNS ||--o{ FLAKY_TEST_FINDINGS : produces
    ANALYSIS_RUNS }o--|| LLM_PROVIDER_CONFIGS : used

    REPOSITORIES {
        uuid id PK
        string name
        string url
        string default_branch
        timestamp created_at
    }
    COMMITS {
        uuid id PK
        uuid repo_id FK
        string sha
        int pr_number
        string author
        string branch
        jsonb diff_stats
        timestamp created_at
    }
    TEST_RUNS {
        uuid id PK
        uuid commit_id FK
        string ci_provider
        string status
        timestamp started_at
        timestamp finished_at
        string raw_log_ref
    }
    TEST_CASES {
        uuid id PK
        uuid repo_id FK
        string name
        string file_path
    }
    TEST_RESULTS {
        uuid id PK
        uuid test_run_id FK
        uuid test_case_id FK
        string status
        int duration_ms
        text error_message
    }
    FLAKY_TEST_FINDINGS {
        uuid id PK
        uuid test_case_id FK
        uuid analysis_run_id FK
        float confidence_score
        text pattern_summary
        timestamp first_detected_at
        timestamp last_seen_at
    }
    RISK_FINDINGS {
        uuid id PK
        uuid analysis_run_id FK
        uuid repo_id FK
        string file_path
        float risk_score
        text rationale
    }
    TEST_SUGGESTIONS {
        uuid id PK
        uuid analysis_run_id FK
        uuid repo_id FK
        string file_path
        string target_function
        text suggested_test_code
        text rationale
        string status
        timestamp created_at
    }
    ANALYSIS_RUNS {
        uuid id PK
        uuid repo_id FK
        string trigger
        string type
        string status
        uuid provider_config_id FK
        int token_usage
        numeric cost
        timestamp started_at
        timestamp finished_at
    }
    LLM_PROVIDER_CONFIGS {
        uuid id PK
        string provider_name
        string model
        bool is_active
        jsonb config_json
    }
```

**Notes:**

- `analysis_runs` is the anchor entity for observability and cost accounting — every
  engine invocation belongs to exactly one run, and every finding traces back to the run
  (and therefore the provider/model) that produced it.
- `test_suggestions.status` (`pending` / `accepted` / `rejected`) makes suggestion
  review an explicit workflow state rather than an implicit one, so acceptance-rate
  becomes a measurable signal on generation quality.
- Schema is intentionally high-level here; exact column types, indexes, and constraints
  are defined when persistence code is implemented, not in this design doc.

## 4. API Boundaries

All endpoints are versioned under `/api/v1`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/repositories` | Register a repository with the platform |
| `GET` | `/repositories/{id}` | Repository detail |
| `POST` | `/repositories/{id}/analysis-runs` | Manually trigger an analysis run |
| `GET` | `/repositories/{id}/analysis-runs/{run_id}` | Analysis run status/result |
| `GET` | `/repositories/{id}/risk-findings` | List risk findings |
| `GET` | `/repositories/{id}/test-suggestions` | List test suggestions |
| `POST` | `/test-suggestions/{id}/accept` | Mark a suggestion accepted |
| `POST` | `/test-suggestions/{id}/reject` | Mark a suggestion rejected |
| `GET` | `/repositories/{id}/flaky-tests` | List flaky test findings |
| `POST` | `/webhooks/github` | GitHub PR/commit event ingestion |
| `POST` | `/webhooks/ci` | CI test-run result ingestion |

**Boundary rules:**

- The API layer only talks to `persistence/` (reads) and `orchestration/` (to enqueue
  work on `POST` endpoints that trigger analysis). It never imports an analysis engine
  or a provider implementation directly.
- Webhook endpoints are the only unauthenticated-by-default surface (secured instead by
  provider signature verification — e.g. GitHub's HMAC signature) since they're called
  by external systems, not end users; every other endpoint sits behind whatever
  authentication model is adopted (deferred — see roadmap).
- All analysis-triggering endpoints return immediately with an `analysis_run_id` in
  `pending` state; clients poll (or later, subscribe) for completion. No endpoint blocks
  on an LLM call.
- Response schemas are Pydantic models shared between the endpoint definition and the
  OpenAPI spec FastAPI generates automatically — the frontend's typed API client is
  intended to be generated from that spec rather than hand-synced.

## 5. Module Contracts

- **`AnalysisEngine` interface** (implemented by Risk, Generation, Triage engines):
  `run(context: AnalysisContext) -> AnalysisResult`. `AnalysisContext` carries the repo,
  commit/PR reference, and any engine-specific inputs (e.g. failed test results for
  triage). The orchestrator depends only on this interface, never on a concrete engine.
- **`LLMProvider` interface**: see [architecture.md §7](architecture.md#7-provider-abstraction-strategy).
- **`TaskQueue` interface**: `enqueue(job) -> job_id`, `status(job_id) -> JobStatus`.
  The in-process implementation runs jobs on an async worker pool within the API
  process; the interface is the seam a future Celery/Temporal-backed implementation
  would slot behind without changing any caller.
- **Repository pattern**: each persistence entity is accessed through a repository
  class (e.g. `RiskFindingRepository`), never through raw SQLAlchemy sessions from
  outside `persistence/` — this is what lets engines and API routes stay agnostic to
  schema details.
