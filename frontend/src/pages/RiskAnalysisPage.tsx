import { useState } from 'react'
import type { FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { Card } from '../components/Card'
import { ConfidenceMeter } from '../components/ConfidenceMeter'
import { EvidenceList } from '../components/EvidenceList'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { Button, TextAreaField, TextField } from '../components/form'
import { ApiError } from '../api-client/client'
import { usePollAnalysisRunStatus } from '../state/useAnalysisRuns'
import { useRiskFindings, useTriggerRiskAnalysis } from '../state/useRisk'
import '../styles/dashboard.css'
import './RiskAnalysisPage.css'

export function RiskAnalysisPage() {
  const { repoId } = useParams<{ repoId: string }>()
  if (!repoId) return null
  return <RiskAnalysisPageContent repoId={repoId} />
}

function RiskAnalysisPageContent({ repoId }: { repoId: string }) {
  const queryClient = useQueryClient()
  const { data: findings, isLoading, isError } = useRiskFindings(repoId)
  const trigger = useTriggerRiskAnalysis(repoId)

  const [diff, setDiff] = useState('')
  const [commitSha, setCommitSha] = useState('')
  const [prNumber, setPrNumber] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | undefined>(undefined)

  const activeRun = usePollAnalysisRunStatus(repoId, activeRunId, () => {
    void queryClient.invalidateQueries({ queryKey: ['repositories', repoId, 'risk-findings'] })
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    trigger.mutate(
      {
        diff,
        commit_sha: commitSha || undefined,
        pr_number: prNumber ? Number(prNumber) : undefined,
        trigger: 'manual',
      },
      {
        onSuccess: (result) => setActiveRunId(result.analysis_run_id),
        onError: (error) => setFormError(error instanceof ApiError ? error.message : 'Failed to trigger analysis.'),
      },
    )
  }

  return (
    <div>
      <h1 className="page-title">Risk Analysis</h1>
      <p className="page-subtitle">Trigger PR risk analysis and review findings for this repository.</p>

      <div className="risk-page__grid">
        <Card title="Trigger Risk Analysis">
          <form onSubmit={handleSubmit}>
            <TextAreaField
              label="Diff"
              htmlFor="risk-diff"
              hint="unified diff"
              value={diff}
              onChange={(e) => setDiff(e.target.value)}
              required
            />
            <TextField
              label="Commit SHA"
              htmlFor="risk-commit-sha"
              value={commitSha}
              onChange={(e) => setCommitSha(e.target.value)}
            />
            <TextField
              label="PR Number"
              htmlFor="risk-pr-number"
              type="number"
              value={prNumber}
              onChange={(e) => setPrNumber(e.target.value)}
            />
            {formError && <ErrorState message={formError} />}
            <Button type="submit" disabled={trigger.isPending || diff.trim() === ''}>
              {trigger.isPending ? 'Submitting…' : 'Run Risk Analysis'}
            </Button>
            {activeRunId && activeRun.data && (
              <p className="risk-page__run-status">
                Run <code>{activeRunId}</code>: <StatusBadge value={activeRun.data.status} />
              </p>
            )}
          </form>
        </Card>

        <Card title="Risk Findings">
          {isLoading && <LoadingState label="Loading findings…" />}
          {isError && <ErrorState message="Failed to load risk findings." />}
          {findings && findings.length === 0 && <EmptyState message="No risk findings yet for this repository." />}
          {findings && findings.length > 0 && (
            <ul className="finding-list">
              {findings.map((finding) => (
                <li key={finding.id} className="finding-list__item">
                  <div className="finding-list__header">
                    <span className="finding-list__file">{finding.file_path}</span>
                    <StatusBadge value={finding.release_recommendation} />
                  </div>
                  <div className="finding-list__scores">
                    <span>Risk score: {finding.risk_score.toFixed(2)}</span>
                    <ConfidenceMeter value={finding.confidence_score} label="confidence" />
                  </div>
                  <p className="finding-list__categories">
                    {finding.categories.length > 0 ? finding.categories.join(', ') : 'No categories detected'}
                  </p>
                  {finding.rationale && <p className="finding-list__rationale">{finding.rationale}</p>}
                  <details>
                    <summary>Evidence ({finding.evidence.length})</summary>
                    <EvidenceList items={finding.evidence} />
                  </details>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
