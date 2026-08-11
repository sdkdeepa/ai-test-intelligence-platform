import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { renderWithProviders } from '../test/renderWithProviders'
import { AnalysisRunHistoryPage } from './AnalysisRunHistoryPage'
import { analysisRunsApi } from '../api-client/analysisRuns'
import type { AnalysisRun, LLMInvocation } from '../api-client/types'

vi.mock('../api-client/analysisRuns', () => ({
  analysisRunsApi: { list: vi.fn(), getStatus: vi.fn(), listLLMInvocations: vi.fn() },
}))

const mockedAnalysisRunsApi = vi.mocked(analysisRunsApi)

const SAMPLE_RUN: AnalysisRun = {
  id: 'run-1',
  repo_id: 'repo-1',
  type: 'risk',
  trigger: 'manual',
  status: 'completed',
  started_at: '2026-08-10T12:00:00Z',
  finished_at: '2026-08-10T12:00:05Z',
}

const SAMPLE_INVOCATION: LLMInvocation = {
  id: 'invocation-1',
  analysis_run_id: 'run-1',
  provider: 'mock',
  model: 'mock-default',
  input_tokens: 42,
  output_tokens: 17,
  latency_ms: 12.5,
  request_id: null,
  estimated_cost: null,
  created_at: '2026-08-10T12:00:02Z',
}

describe('AnalysisRunHistoryPage', () => {
  it('lists analysis runs with engine type and state', async () => {
    mockedAnalysisRunsApi.list.mockResolvedValue([SAMPLE_RUN])

    renderWithProviders(<AnalysisRunHistoryPage />, {
      route: '/repositories/repo-1/runs',
      path: '/repositories/:repoId/runs',
    })

    expect(await screen.findByText('risk')).toBeInTheDocument()
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('shows an empty state when there are no runs', async () => {
    mockedAnalysisRunsApi.list.mockResolvedValue([])

    renderWithProviders(<AnalysisRunHistoryPage />, {
      route: '/repositories/repo-1/runs',
      path: '/repositories/:repoId/runs',
    })

    expect(await screen.findByText(/no analysis runs yet/i)).toBeInTheDocument()
  })

  it('reveals LLM invocation detail (provider/model/tokens/latency) on toggle', async () => {
    mockedAnalysisRunsApi.list.mockResolvedValue([SAMPLE_RUN])
    mockedAnalysisRunsApi.listLLMInvocations.mockResolvedValue([SAMPLE_INVOCATION])
    const user = userEvent.setup()

    renderWithProviders(<AnalysisRunHistoryPage />, {
      route: '/repositories/repo-1/runs',
      path: '/repositories/:repoId/runs',
    })
    await screen.findByText('risk')

    await user.click(screen.getByRole('button', { name: /show invocations/i }))

    expect(await screen.findByText('mock-default')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('17')).toBeInTheDocument()
    expect(screen.getByText('13 ms')).toBeInTheDocument()
  })
})
