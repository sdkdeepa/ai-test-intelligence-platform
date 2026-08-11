import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { renderWithProviders } from '../test/renderWithProviders'
import { ReviewQueuePage } from './ReviewQueuePage'
import { reviewQueueApi } from '../api-client/review'
import type { ReviewRequest } from '../api-client/types'

vi.mock('../api-client/review', () => ({
  reviewQueueApi: {
    list: vi.fn(),
    get: vi.fn(),
    listAuditEvents: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
  },
}))

const mockedReviewQueueApi = vi.mocked(reviewQueueApi)

const PENDING_REVIEW_REQUEST: ReviewRequest = {
  id: 'review-1',
  analysis_run_id: 'run-1',
  repo_id: 'repo-1',
  status: 'pending',
  reasons: ['high_release_risk', 'authentication_or_authorization_change'],
  risk_summary: { risk_score: 0.82, confidence_score: 0.7, release_recommendation: 'block' },
  github_owner: 'acme',
  github_repo: 'widgets',
  github_head_sha: 'abc123',
  github_pr_number: 42,
  reviewer: null,
  review_reason: null,
  created_at: '2026-08-11T00:00:00',
  decided_at: null,
}

describe('ReviewQueuePage', () => {
  it('renders a pending review request with its reasons and PR reference', async () => {
    mockedReviewQueueApi.list.mockResolvedValue([PENDING_REVIEW_REQUEST])

    renderWithProviders(<ReviewQueuePage />, { route: '/review-queue', path: '/review-queue' })

    expect(await screen.findByText(/acme\/widgets #42/)).toBeInTheDocument()
    const reasons = within(screen.getByTestId('review-reasons'))
    expect(reasons.getByText(/high release risk/)).toBeInTheDocument()
    expect(reasons.getByText(/authentication or authorization change/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
  })

  it('shows an empty state when nothing is pending', async () => {
    mockedReviewQueueApi.list.mockResolvedValue([])

    renderWithProviders(<ReviewQueuePage />, { route: '/review-queue', path: '/review-queue' })

    expect(await screen.findByText(/nothing is waiting for review/i)).toBeInTheDocument()
  })

  it('disables approve/reject until a reviewer name is entered', async () => {
    mockedReviewQueueApi.list.mockResolvedValue([PENDING_REVIEW_REQUEST])

    renderWithProviders(<ReviewQueuePage />, { route: '/review-queue', path: '/review-queue' })
    await screen.findByText(/acme\/widgets #42/)

    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /reject/i })).toBeDisabled()
  })

  it('approving calls the approve endpoint with the entered reviewer and reason', async () => {
    mockedReviewQueueApi.list.mockResolvedValue([PENDING_REVIEW_REQUEST])
    mockedReviewQueueApi.approve.mockResolvedValue({ ...PENDING_REVIEW_REQUEST, status: 'approved' })
    const user = userEvent.setup()

    renderWithProviders(<ReviewQueuePage />, { route: '/review-queue', path: '/review-queue' })
    await screen.findByText(/acme\/widgets #42/)

    await user.type(screen.getByLabelText(/reviewer/i), 'alice')
    await user.type(screen.getByLabelText(/reason/i), 'looks fine')
    await user.click(screen.getByRole('button', { name: /approve/i }))

    await waitFor(() => {
      expect(mockedReviewQueueApi.approve).toHaveBeenCalledWith('review-1', { reviewer: 'alice', reason: 'looks fine' })
    })
  })

  it('rejecting calls the reject endpoint', async () => {
    mockedReviewQueueApi.list.mockResolvedValue([PENDING_REVIEW_REQUEST])
    mockedReviewQueueApi.reject.mockResolvedValue({ ...PENDING_REVIEW_REQUEST, status: 'rejected' })
    const user = userEvent.setup()

    renderWithProviders(<ReviewQueuePage />, { route: '/review-queue', path: '/review-queue' })
    await screen.findByText(/acme\/widgets #42/)

    await user.type(screen.getByLabelText(/reviewer/i), 'bob')
    await user.click(screen.getByRole('button', { name: /reject/i }))

    await waitFor(() => {
      expect(mockedReviewQueueApi.reject).toHaveBeenCalledWith('review-1', { reviewer: 'bob', reason: undefined })
    })
  })

  it('shows "manually triggered" for a review request with no linked PR', async () => {
    mockedReviewQueueApi.list.mockResolvedValue([
      { ...PENDING_REVIEW_REQUEST, github_owner: null, github_repo: null, github_pr_number: null },
    ])

    renderWithProviders(<ReviewQueuePage />, { route: '/review-queue', path: '/review-queue' })

    expect(await screen.findByText(/manually triggered/i)).toBeInTheDocument()
  })
})
