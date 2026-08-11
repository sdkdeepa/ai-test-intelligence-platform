// Typed against the backend's Pydantic response/request models
// (backend/app/api/*.py) — field-for-field, so a backend contract change
// surfaces here as a type error rather than a silent runtime mismatch.
// See docs/architecture.md §6.

export interface Repository {
  id: string
  name: string
  url: string
  default_branch: string
}

export interface RepositoryCreate {
  name: string
  url: string
  default_branch?: string
}

export type AnalysisState = 'pending' | 'running' | 'completed' | 'failed'

export interface AnalysisRunTriggered {
  analysis_run_id: string
  status: string
}

export interface AnalysisRun {
  id: string
  repo_id: string
  type: string
  trigger: string
  status: AnalysisState
  started_at: string | null
  finished_at: string | null
}

export interface LLMInvocation {
  id: string
  analysis_run_id: string
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  latency_ms: number
  request_id: string | null
  estimated_cost: number | null
  created_at: string
}

export type ReleaseRecommendation = 'block' | 'caution' | 'proceed'

export interface RiskFinding {
  id: string
  analysis_run_id: string
  file_path: string
  risk_score: number
  rationale: string | null
  categories: string[]
  evidence: string[]
  confidence_score: number
  affected_components: string[]
  recommended_regression_scope: string[]
  release_recommendation: ReleaseRecommendation
}

export interface RiskAnalysisRequest {
  diff: string
  commit_sha?: string
  pr_number?: number
  trigger?: string
}

export type TestSuggestionStatus = 'pending' | 'accepted' | 'rejected'

export interface TestSuggestion {
  id: string
  analysis_run_id: string
  repo_id: string
  file_path: string
  target_function: string | null
  suggested_test_code: string
  rationale: string | null
  status: TestSuggestionStatus
  test_type: string
  evidence: string[]
  assumptions: string[]
  confidence: number
  uncovered_risks: string[]
  recommended_follow_up_validation: string[]
}

export interface TestIntelligenceRequest {
  source_code?: string
  requirement_text?: string
  api_specification?: string
  diff?: string
  existing_test_context?: string
  file_path?: string
  commit_sha?: string
  pr_number?: number
  trigger?: string
}

export type FailureClassification = 'regression' | 'flaky' | 'environment' | 'unknown'

export interface FailureFinding {
  id: string
  analysis_run_id: string
  test_result_id: string | null
  test_case_id: string | null
  classification: FailureClassification
  confidence_score: number | null
  rationale: string | null
  root_cause_hypotheses: string[]
  evidence: string[]
  missing_evidence: string[]
  debugging_recommendations: string[]
  suggested_bug_report: string | null
}

export interface FailureIntelligenceRequest {
  pytest_output?: string
  playwright_output?: string
  stack_trace?: string
  ci_log?: string
  application_log?: string
  environment_info?: string
  test_name?: string
  test_case_id?: string
  trigger?: string
}

export type ReviewRequestStatus = 'pending' | 'approved' | 'rejected'

export interface ReviewRequest {
  id: string
  analysis_run_id: string
  repo_id: string
  status: ReviewRequestStatus
  reasons: string[]
  risk_summary: {
    risk_score?: number
    confidence_score?: number
    categories?: string[]
    release_recommendation?: string
    [key: string]: unknown
  }
  github_owner: string | null
  github_repo: string | null
  github_head_sha: string | null
  github_pr_number: number | null
  reviewer: string | null
  review_reason: string | null
  created_at: string
  decided_at: string | null
}

export interface AuditEvent {
  id: string
  review_request_id: string | null
  analysis_run_id: string | null
  repo_id: string | null
  event_type: string
  actor: string | null
  payload: Record<string, unknown>
  created_at: string
}

export interface ReviewDecisionRequest {
  reviewer: string
  reason?: string
}
