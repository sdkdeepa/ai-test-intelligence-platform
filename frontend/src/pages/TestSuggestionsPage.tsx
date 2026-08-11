import { useState } from 'react'
import type { FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { Card } from '../components/Card'
import { ConfidenceMeter } from '../components/ConfidenceMeter'
import { EvidenceList } from '../components/EvidenceList'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { Button, TextAreaField } from '../components/form'
import { ApiError } from '../api-client/client'
import { usePollAnalysisRunStatus } from '../state/useAnalysisRuns'
import {
  useAcceptTestSuggestion,
  useRejectTestSuggestion,
  useTestSuggestions,
  useTriggerTestIntelligence,
} from '../state/useTestIntelligence'
import '../styles/dashboard.css'
import './TestSuggestionsPage.css'

export function TestSuggestionsPage() {
  const { repoId } = useParams<{ repoId: string }>()
  if (!repoId) return null
  return <TestSuggestionsPageContent repoId={repoId} />
}

function TestSuggestionsPageContent({ repoId }: { repoId: string }) {
  const queryClient = useQueryClient()
  const { data: suggestions, isLoading, isError } = useTestSuggestions(repoId)
  const trigger = useTriggerTestIntelligence(repoId)
  const accept = useAcceptTestSuggestion(repoId)
  const reject = useRejectTestSuggestion(repoId)

  const [sourceCode, setSourceCode] = useState('')
  const [requirementText, setRequirementText] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | undefined>(undefined)

  const activeRun = usePollAnalysisRunStatus(repoId, activeRunId, () => {
    void queryClient.invalidateQueries({ queryKey: ['repositories', repoId, 'test-suggestions'] })
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    trigger.mutate(
      {
        source_code: sourceCode || undefined,
        requirement_text: requirementText || undefined,
        trigger: 'manual',
      },
      {
        onSuccess: (result) => setActiveRunId(result.analysis_run_id),
        onError: (error) => setFormError(error instanceof ApiError ? error.message : 'Failed to trigger analysis.'),
      },
    )
  }

  const hasInput = sourceCode.trim() !== '' || requirementText.trim() !== ''

  return (
    <div>
      <h1 className="page-title">Test Suggestions</h1>
      <p className="page-subtitle">AI-generated test suggestions for this repository.</p>

      <div className="risk-page__grid">
        <Card title="Trigger Test Intelligence">
          <form onSubmit={handleSubmit}>
            <TextAreaField
              label="Source Code"
              htmlFor="ti-source-code"
              value={sourceCode}
              onChange={(e) => setSourceCode(e.target.value)}
            />
            <TextAreaField
              label="Requirement Text"
              htmlFor="ti-requirement-text"
              rows={3}
              value={requirementText}
              onChange={(e) => setRequirementText(e.target.value)}
            />
            {formError && <ErrorState message={formError} />}
            <Button type="submit" disabled={trigger.isPending || !hasInput}>
              {trigger.isPending ? 'Submitting…' : 'Run Test Intelligence'}
            </Button>
            {activeRunId && activeRun.data && (
              <p className="risk-page__run-status">
                Run <code>{activeRunId}</code>: <StatusBadge value={activeRun.data.status} />
              </p>
            )}
          </form>
        </Card>

        <Card title="Suggestions">
          {isLoading && <LoadingState label="Loading suggestions…" />}
          {isError && <ErrorState message="Failed to load test suggestions." />}
          {suggestions && suggestions.length === 0 && <EmptyState message="No test suggestions yet." />}
          {suggestions && suggestions.length > 0 && (
            <ul className="finding-list">
              {suggestions.map((suggestion) => (
                <li key={suggestion.id} className="finding-list__item">
                  <div className="finding-list__header">
                    <span className="finding-list__file">
                      {suggestion.test_type} — {suggestion.file_path}
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
                  {suggestion.status === 'pending' && (
                    <div className="suggestion-actions">
                      <Button
                        variant="primary"
                        disabled={accept.isPending}
                        onClick={() => accept.mutate(suggestion.id)}
                      >
                        Accept
                      </Button>
                      <Button
                        variant="danger"
                        disabled={reject.isPending}
                        onClick={() => reject.mutate(suggestion.id)}
                      >
                        Reject
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
