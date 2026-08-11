import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { renderWithProviders } from '../test/renderWithProviders'
import { RiskAnalysisPage } from './RiskAnalysisPage'
import { riskApi } from '../api-client/risk'
import { analysisRunsApi } from '../api-client/analysisRuns'
import type { RiskFinding } from '../api-client/types'

vi.mock('../api-client/risk', () => ({
  riskApi: { trigger: vi.fn(), listFindings: vi.fn() },
}))
vi.mock('../api-client/analysisRuns', () => ({
  analysisRunsApi: { getStatus: vi.fn(), list: vi.fn(), listLLMInvocations: vi.fn() },
}))

const mockedRiskApi = vi.mocked(riskApi)
const mockedAnalysisRunsApi = vi.mocked(analysisRunsApi)

const SAMPLE_FINDING: RiskFinding = {
  id: 'finding-1',
  analysis_run_id: 'run-1',
  file_path: 'app/auth/login.py',
  risk_score: 0.82,
  rationale: 'Deterministic assessment: risk_score=0.82, categories=authentication_authorization.',
  categories: ['authentication_authorization'],
  evidence: ['authentication_authorization: app/auth/login.py — file path suggests authentication logic'],
  confidence_score: 0.75,
  affected_components: ['app/auth'],
  recommended_regression_scope: ['Unit tests for all directly changed files'],
  release_recommendation: 'block',
}

describe('RiskAnalysisPage', () => {
  it('renders existing risk findings with score, recommendation, and evidence', async () => {
    mockedRiskApi.listFindings.mockResolvedValue([SAMPLE_FINDING])

    renderWithProviders(<RiskAnalysisPage />, {
      route: '/repositories/repo-1/risk',
      path: '/repositories/:repoId/risk',
    })

    expect(await screen.findByText('app/auth/login.py')).toBeInTheDocument()
    expect(screen.getByText('block')).toBeInTheDocument()
    expect(screen.getByText(/risk score: 0.82/i)).toBeInTheDocument()
  })

  it('triggers analysis and polls until the run completes', async () => {
    mockedRiskApi.listFindings.mockResolvedValue([])
    mockedRiskApi.trigger.mockResolvedValue({ analysis_run_id: 'run-42', status: 'pending' })
    mockedAnalysisRunsApi.getStatus.mockResolvedValueOnce({ analysis_run_id: 'run-42', status: 'running' })
    mockedAnalysisRunsApi.getStatus.mockResolvedValueOnce({ analysis_run_id: 'run-42', status: 'completed' })
    const user = userEvent.setup()

    renderWithProviders(<RiskAnalysisPage />, {
      route: '/repositories/repo-1/risk',
      path: '/repositories/:repoId/risk',
    })
    await screen.findByText(/no risk findings yet/i)

    await user.type(screen.getByLabelText(/diff/i), 'diff --git a/x b/x')
    await user.click(screen.getByRole('button', { name: /run risk analysis/i }))

    expect(await screen.findByText('run-42')).toBeInTheDocument()
    expect(await screen.findByText('completed')).toBeInTheDocument()
  })

  it('the submit button is disabled until a diff is entered', async () => {
    mockedRiskApi.listFindings.mockResolvedValue([])

    renderWithProviders(<RiskAnalysisPage />, {
      route: '/repositories/repo-1/risk',
      path: '/repositories/:repoId/risk',
    })
    await screen.findByText(/no risk findings yet/i)

    expect(screen.getByRole('button', { name: /run risk analysis/i })).toBeDisabled()
  })
})
