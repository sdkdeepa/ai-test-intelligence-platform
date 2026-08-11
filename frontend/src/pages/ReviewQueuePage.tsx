import { useState } from 'react'

import { Card } from '../components/Card'
import { ConfidenceMeter } from '../components/ConfidenceMeter'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { Button, TextField } from '../components/form'
import { usePendingReviewRequests, useApproveReviewRequest, useRejectReviewRequest } from '../state/useReviewQueue'
import type { ReviewRequest } from '../api-client/types'
import '../styles/dashboard.css'
import './ReviewQueuePage.css'

export function ReviewQueuePage() {
  const { data, isLoading, isError } = usePendingReviewRequests()

  return (
    <div>
      <h1 className="page-title">Pending Approvals</h1>
      <p className="page-subtitle">
        Risk assessments flagged by policy — high release risk, low confidence, authentication/authorization or
        breaking-change categories, security-sensitive findings, or insufficient evidence — awaiting a human
        decision before their result can be treated as approved. See the audit trail behind each decision via the
        platform API's <code>/review-queue/&#123;id&#125;/audit-events</code> endpoint.
      </p>

      <Card>
        {isLoading && <LoadingState label="Loading pending approvals…" />}
        {isError && <ErrorState message="Failed to load the review queue." />}
        {!isLoading && !isError && (data?.length ?? 0) === 0 && (
          <EmptyState message="Nothing is waiting for review right now." />
        )}
        {data && data.length > 0 && (
          <ul className="finding-list">
            {data.map((reviewRequest) => (
              <ReviewRequestRow key={reviewRequest.id} reviewRequest={reviewRequest} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function ReviewRequestRow({ reviewRequest }: { reviewRequest: ReviewRequest }) {
  const approve = useApproveReviewRequest()
  const reject = useRejectReviewRequest()
  const [reviewer, setReviewer] = useState('')
  const [reason, setReason] = useState('')

  const busy = approve.isPending || reject.isPending
  const canDecide = reviewer.trim().length > 0

  const summary = reviewRequest.risk_summary
  const prLabel =
    reviewRequest.github_owner && reviewRequest.github_repo && reviewRequest.github_pr_number
      ? `${reviewRequest.github_owner}/${reviewRequest.github_repo} #${reviewRequest.github_pr_number}`
      : 'Manually triggered — no linked pull request'

  return (
    <li className="finding-list__item review-request">
      <div className="finding-list__header">
        <span className="finding-list__file">{prLabel}</span>
        {summary.release_recommendation && <StatusBadge value={summary.release_recommendation} />}
      </div>

      {typeof summary.risk_score === 'number' && (
        <ConfidenceMeter value={summary.risk_score} label="risk score" />
      )}

      <div className="review-request__reasons">
        <span className="review-request__reasons-label">Flagged for:</span>
        <ul data-testid="review-reasons">
          {reviewRequest.reasons.map((reason_) => (
            <li key={reason_}>{reason_.replace(/_/g, ' ')}</li>
          ))}
        </ul>
      </div>

      <form
        className="review-request__form"
        onSubmit={(event) => event.preventDefault()}
      >
        <TextField
          label="Reviewer"
          htmlFor={`reviewer-${reviewRequest.id}`}
          hint="required"
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          placeholder="your name or handle"
        />
        <TextField
          label="Reason"
          htmlFor={`reason-${reviewRequest.id}`}
          hint="optional"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="why you're approving or rejecting"
        />
        <div className="suggestion-actions">
          <Button
            variant="primary"
            disabled={busy || !canDecide}
            onClick={() => approve.mutate({ id: reviewRequest.id, payload: { reviewer, reason: reason || undefined } })}
          >
            Approve
          </Button>
          <Button
            variant="danger"
            disabled={busy || !canDecide}
            onClick={() => reject.mutate({ id: reviewRequest.id, payload: { reviewer, reason: reason || undefined } })}
          >
            Reject
          </Button>
        </div>
        {(approve.isError || reject.isError) && (
          <ErrorState message="Failed to record the decision. It may have already been decided — refresh and try again." />
        )}
      </form>
    </li>
  )
}
