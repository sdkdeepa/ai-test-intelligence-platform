import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'

import { renderWithProviders } from '../test/renderWithProviders'
import { FailureIntelligencePage } from './FailureIntelligencePage'
import { failureIntelligenceApi } from '../api-client/failureIntelligence'
import type { FailureFinding } from '../api-client/types'

vi.mock('../api-client/failureIntelligence', () => ({
  failureIntelligenceApi: { trigger: vi.fn(), listFindings: vi.fn() },
}))
vi.mock('../api-client/analysisRuns', () => ({
  analysisRunsApi: { getStatus: vi.fn(), list: vi.fn(), listLLMInvocations: vi.fn() },
}))

const mockedFailureIntelligenceApi = vi.mocked(failureIntelligenceApi)

const SAMPLE_FINDING: FailureFinding = {
  id: 'finding-1',
  analysis_run_id: 'run-1',
  test_result_id: null,
  test_case_id: null,
  classification: 'regression',
  confidence_score: 0.55,
  rationale: 'Deterministic classification: regression (confidence 0.55). Historical signal: no data.',
  root_cause_hypotheses: ['a recent refactor may have changed rounding behavior'],
  evidence: ['an assertion failure was found in the supplied output'],
  missing_evidence: ['No test_case_id supplied — historical flaky/recurring-pattern clustering was not attempted.'],
  debugging_recommendations: ['Bisect recent commits touching the failing code path.'],
  suggested_bug_report: 'add() returns 5 instead of 4 for inputs (2, 3)',
}

describe('FailureIntelligencePage', () => {
  it('renders the classification badge and separates facts from hypotheses', async () => {
    mockedFailureIntelligenceApi.listFindings.mockResolvedValue([SAMPLE_FINDING])

    renderWithProviders(<FailureIntelligencePage />, {
      route: '/repositories/repo-1/failure-intelligence',
      path: '/repositories/:repoId/failure-intelligence',
    })

    expect(await screen.findByText('regression')).toBeInTheDocument()
    expect(
      screen.getByText('an assertion failure was found in the supplied output'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('a recent refactor may have changed rounding behavior'),
    ).toBeInTheDocument()
    // The two sections must be visibly distinct labels, not merged into one list.
    expect(screen.getByText(/factual evidence/i)).toBeInTheDocument()
    expect(screen.getByText(/ai-generated root cause hypotheses/i)).toBeInTheDocument()
  })

  it('shows an empty state when there are no findings', async () => {
    mockedFailureIntelligenceApi.listFindings.mockResolvedValue([])

    renderWithProviders(<FailureIntelligencePage />, {
      route: '/repositories/repo-1/failure-intelligence',
      path: '/repositories/:repoId/failure-intelligence',
    })

    expect(await screen.findByText(/no failure findings yet/i)).toBeInTheDocument()
  })
})
