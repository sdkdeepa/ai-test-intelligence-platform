import { Card } from '../components/Card'
import { ConfidenceMeter } from '../components/ConfidenceMeter'
import { EvidenceList } from '../components/EvidenceList'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { Button } from '../components/form'
import { usePendingReview } from '../state/usePendingReview'
import { useAcceptTestSuggestion, useRejectTestSuggestion } from '../state/useTestIntelligence'
import type { Repository, TestSuggestion } from '../api-client/types'
import '../styles/dashboard.css'
import '../pages/TestSuggestionsPage.css'

export function HumanReviewPage() {
  const { items, isLoading, isError } = usePendingReview()

  return (
    <div>
      <h1 className="page-title">Human Review</h1>
      <p className="page-subtitle">Pending test suggestions awaiting a decision, across all repositories.</p>

      <Card>
        {isLoading && <LoadingState label="Loading pending suggestions…" />}
        {isError && <ErrorState message="Failed to load pending suggestions." />}
        {!isLoading && !isError && items.length === 0 && (
          <EmptyState message="No suggestions are waiting for review." />
        )}
        {items.length > 0 && (
          <ul className="finding-list">
            {items.map(({ repo, suggestion }) => (
              <ReviewItemRow key={suggestion.id} repo={repo} suggestion={suggestion} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function ReviewItemRow({ repo, suggestion }: { repo: Repository; suggestion: TestSuggestion }) {
  const accept = useAcceptTestSuggestion(repo.id)
  const reject = useRejectTestSuggestion(repo.id)

  return (
    <li className="finding-list__item">
      <div className="finding-list__header">
        <span className="finding-list__file">
          {repo.name} — {suggestion.test_type} — {suggestion.file_path}
        </span>
        <StatusBadge value={suggestion.status} />
      </div>
      <ConfidenceMeter value={suggestion.confidence} label="confidence" />
      {suggestion.rationale && <p className="finding-list__rationale">{suggestion.rationale}</p>}
      <pre className="suggestion-code">{suggestion.suggested_test_code}</pre>
      <details>
        <summary>Evidence ({suggestion.evidence.length})</summary>
        <EvidenceList items={suggestion.evidence} />
      </details>
      <div className="suggestion-actions">
        <Button variant="primary" disabled={accept.isPending} onClick={() => accept.mutate(suggestion.id)}>
          Accept
        </Button>
        <Button variant="danger" disabled={reject.isPending} onClick={() => reject.mutate(suggestion.id)}>
          Reject
        </Button>
      </div>
    </li>
  )
}
