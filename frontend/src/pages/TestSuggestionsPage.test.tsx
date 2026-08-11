import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { renderWithProviders } from '../test/renderWithProviders'
import { TestSuggestionsPage } from './TestSuggestionsPage'
import { testIntelligenceApi } from '../api-client/testIntelligence'
import type { TestSuggestion } from '../api-client/types'

vi.mock('../api-client/testIntelligence', () => ({
  testIntelligenceApi: {
    trigger: vi.fn(),
    listSuggestions: vi.fn(),
    accept: vi.fn(),
    reject: vi.fn(),
  },
}))

const mockedTestIntelligenceApi = vi.mocked(testIntelligenceApi)

const PENDING_SUGGESTION: TestSuggestion = {
  id: 'suggestion-1',
  analysis_run_id: 'run-1',
  repo_id: 'repo-1',
  file_path: 'app/util/math.py',
  target_function: 'add',
  suggested_test_code: 'def test_add():\n    assert add(1, 2) == 3',
  rationale: 'covers the primary addition path',
  status: 'pending',
  test_type: 'unit',
  evidence: ['source/diff content was supplied'],
  assumptions: [],
  confidence: 0.6,
  uncovered_risks: [],
  recommended_follow_up_validation: ['Run the suggested test locally (pytest)'],
}

describe('TestSuggestionsPage', () => {
  it('renders a pending suggestion with accept/reject actions', async () => {
    mockedTestIntelligenceApi.listSuggestions.mockResolvedValue([PENDING_SUGGESTION])

    renderWithProviders(<TestSuggestionsPage />, {
      route: '/repositories/repo-1/test-suggestions',
      path: '/repositories/:repoId/test-suggestions',
    })

    expect(await screen.findByText(/app\/util\/math\.py/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /accept/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
  })

  it('does not show actions for an already-decided suggestion', async () => {
    mockedTestIntelligenceApi.listSuggestions.mockResolvedValue([{ ...PENDING_SUGGESTION, status: 'accepted' }])

    renderWithProviders(<TestSuggestionsPage />, {
      route: '/repositories/repo-1/test-suggestions',
      path: '/repositories/:repoId/test-suggestions',
    })

    await screen.findByText(/app\/util\/math\.py/)
    expect(screen.queryByRole('button', { name: /accept/i })).not.toBeInTheDocument()
  })

  it('accepting a suggestion calls the accept endpoint', async () => {
    mockedTestIntelligenceApi.listSuggestions.mockResolvedValue([PENDING_SUGGESTION])
    mockedTestIntelligenceApi.accept.mockResolvedValue({ ...PENDING_SUGGESTION, status: 'accepted' })
    const user = userEvent.setup()

    renderWithProviders(<TestSuggestionsPage />, {
      route: '/repositories/repo-1/test-suggestions',
      path: '/repositories/:repoId/test-suggestions',
    })
    await screen.findByText(/app\/util\/math\.py/)

    await user.click(screen.getByRole('button', { name: /accept/i }))

    await waitFor(() => {
      expect(mockedTestIntelligenceApi.accept).toHaveBeenCalledWith('suggestion-1')
    })
  })

  it('rejecting a suggestion calls the reject endpoint', async () => {
    mockedTestIntelligenceApi.listSuggestions.mockResolvedValue([PENDING_SUGGESTION])
    mockedTestIntelligenceApi.reject.mockResolvedValue({ ...PENDING_SUGGESTION, status: 'rejected' })
    const user = userEvent.setup()

    renderWithProviders(<TestSuggestionsPage />, {
      route: '/repositories/repo-1/test-suggestions',
      path: '/repositories/:repoId/test-suggestions',
    })
    await screen.findByText(/app\/util\/math\.py/)

    await user.click(screen.getByRole('button', { name: /reject/i }))

    await waitFor(() => {
      expect(mockedTestIntelligenceApi.reject).toHaveBeenCalledWith('suggestion-1')
    })
  })
})
