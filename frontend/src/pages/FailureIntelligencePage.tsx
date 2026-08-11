import { useState } from 'react'
import type { FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { Card } from '../components/Card'
import { EvidenceList } from '../components/EvidenceList'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { Button, TextAreaField } from '../components/form'
import { ApiError } from '../api-client/client'
import { usePollAnalysisRunStatus } from '../state/useAnalysisRuns'
import { useFailureFindings, useTriggerFailureIntelligence } from '../state/useFailureIntelligence'
import '../styles/dashboard.css'
import './RiskAnalysisPage.css'

export function FailureIntelligencePage() {
  const { repoId } = useParams<{ repoId: string }>()
  if (!repoId) return null
  return <FailureIntelligencePageContent repoId={repoId} />
}

function FailureIntelligencePageContent({ repoId }: { repoId: string }) {
  const queryClient = useQueryClient()
  const { data: findings, isLoading, isError } = useFailureFindings(repoId)
  const trigger = useTriggerFailureIntelligence(repoId)

  const [pytestOutput, setPytestOutput] = useState('')
  const [ciLog, setCiLog] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | undefined>(undefined)

  const activeRun = usePollAnalysisRunStatus(repoId, activeRunId, () => {
    void queryClient.invalidateQueries({ queryKey: ['repositories', repoId, 'failure-findings'] })
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    trigger.mutate(
      {
        pytest_output: pytestOutput || undefined,
        ci_log: ciLog || undefined,
        trigger: 'manual',
      },
      {
        onSuccess: (result) => setActiveRunId(result.analysis_run_id),
        onError: (error) => setFormError(error instanceof ApiError ? error.message : 'Failed to trigger analysis.'),
      },
    )
  }

  const hasInput = pytestOutput.trim() !== '' || ciLog.trim() !== ''

  return (
    <div>
      <h1 className="page-title">Failure Intelligence</h1>
      <p className="page-subtitle">Analyze CI/test failures: classification, root cause, and debugging guidance.</p>

      <div className="risk-page__grid">
        <Card title="Analyze a Failure">
          <form onSubmit={handleSubmit}>
            <TextAreaField
              label="PyTest Output"
              htmlFor="fi-pytest-output"
              value={pytestOutput}
              onChange={(e) => setPytestOutput(e.target.value)}
            />
            <TextAreaField
              label="CI Log"
              htmlFor="fi-ci-log"
              rows={4}
              value={ciLog}
              onChange={(e) => setCiLog(e.target.value)}
            />
            {formError && <ErrorState message={formError} />}
            <Button type="submit" disabled={trigger.isPending || !hasInput}>
              {trigger.isPending ? 'Submitting…' : 'Analyze Failure'}
            </Button>
            {activeRunId && activeRun.data && (
              <p className="risk-page__run-status">
                Run <code>{activeRunId}</code>: <StatusBadge value={activeRun.data.status} />
              </p>
            )}
          </form>
        </Card>

        <Card title="Failure Findings">
          {isLoading && <LoadingState label="Loading findings…" />}
          {isError && <ErrorState message="Failed to load failure findings." />}
          {findings && findings.length === 0 && <EmptyState message="No failure findings yet." />}
          {findings && findings.length > 0 && (
            <ul className="finding-list">
              {findings.map((finding) => (
                <li key={finding.id} className="finding-list__item">
                  <div className="finding-list__header">
                    <span className="finding-list__file">Analysis run {finding.analysis_run_id.slice(0, 8)}</span>
                    <StatusBadge value={finding.classification} />
                  </div>
                  {finding.confidence_score !== null && (
                    <p className="finding-list__categories">Confidence: {finding.confidence_score.toFixed(2)}</p>
                  )}
                  {finding.rationale && <p className="finding-list__rationale">{finding.rationale}</p>}

                  <details open>
                    <summary>Factual evidence ({finding.evidence.length})</summary>
                    <EvidenceList items={finding.evidence} />
                  </details>
                  <details>
                    <summary>AI-generated root cause hypotheses ({finding.root_cause_hypotheses.length})</summary>
                    <EvidenceList items={finding.root_cause_hypotheses} emptyText="No hypotheses generated." />
                  </details>
                  <details>
                    <summary>Missing evidence ({finding.missing_evidence.length})</summary>
                    <EvidenceList items={finding.missing_evidence} />
                  </details>
                  <details>
                    <summary>Debugging recommendations ({finding.debugging_recommendations.length})</summary>
                    <EvidenceList items={finding.debugging_recommendations} />
                  </details>
                  {finding.suggested_bug_report && (
                    <details>
                      <summary>Suggested bug report</summary>
                      <p className="finding-list__rationale">{finding.suggested_bug_report}</p>
                    </details>
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
