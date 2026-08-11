import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { Card } from '../components/Card'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { useAnalysisRuns, useLLMInvocations } from '../state/useAnalysisRuns'
import '../styles/dashboard.css'
import './AnalysisRunHistoryPage.css'

export function AnalysisRunHistoryPage() {
  const { repoId } = useParams<{ repoId: string }>()
  if (!repoId) return null
  return <AnalysisRunHistoryPageContent repoId={repoId} />
}

function AnalysisRunHistoryPageContent({ repoId }: { repoId: string }) {
  const { data: runs, isLoading, isError } = useAnalysisRuns(repoId)
  const [expandedRunId, setExpandedRunId] = useState<string | undefined>(undefined)

  return (
    <div>
      <h1 className="page-title">Analysis Run History</h1>
      <p className="page-subtitle">Every analysis run for this repository, with per-run LLM invocation detail.</p>

      <Card>
        {isLoading && <LoadingState label="Loading run history…" />}
        {isError && <ErrorState message="Failed to load analysis runs." />}
        {runs && runs.length === 0 && <EmptyState message="No analysis runs yet for this repository." />}
        {runs && runs.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Engine</th>
                <th>Trigger</th>
                <th>State</th>
                <th>Started</th>
                <th>Finished</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <RunRow
                  key={run.id}
                  repoId={repoId}
                  run={run}
                  expanded={expandedRunId === run.id}
                  onToggle={() => setExpandedRunId(expandedRunId === run.id ? undefined : run.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

function RunRow({
  repoId,
  run,
  expanded,
  onToggle,
}: {
  repoId: string
  run: { id: string; type: string; trigger: string; status: string; started_at: string | null; finished_at: string | null }
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr>
        <td>{run.type}</td>
        <td>{run.trigger}</td>
        <td>
          <StatusBadge value={run.status} />
        </td>
        <td>{formatTimestamp(run.started_at)}</td>
        <td>{formatTimestamp(run.finished_at)}</td>
        <td>
          <button type="button" className="run-row__toggle" onClick={onToggle}>
            {expanded ? 'Hide invocations' : 'Show invocations'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6}>
            <LLMInvocationsPanel repoId={repoId} runId={run.id} />
          </td>
        </tr>
      )}
    </>
  )
}

function LLMInvocationsPanel({ repoId, runId }: { repoId: string; runId: string }) {
  const { data: invocations, isLoading, isError } = useLLMInvocations(repoId, runId)

  if (isLoading) return <LoadingState label="Loading invocations…" />
  if (isError) return <ErrorState message="Failed to load LLM invocations." />
  if (!invocations || invocations.length === 0) {
    return <EmptyState message="No LLM invocations recorded for this run." />
  }

  return (
    <table className="data-table data-table--nested">
      <thead>
        <tr>
          <th>Provider</th>
          <th>Model</th>
          <th>Input Tokens</th>
          <th>Output Tokens</th>
          <th>Latency</th>
          <th>Estimated Cost</th>
        </tr>
      </thead>
      <tbody>
        {invocations.map((invocation) => (
          <tr key={invocation.id}>
            <td>{invocation.provider}</td>
            <td className="data-table__mono">{invocation.model}</td>
            <td>{invocation.input_tokens}</td>
            <td>{invocation.output_tokens}</td>
            <td>{invocation.latency_ms.toFixed(0)} ms</td>
            <td>{invocation.estimated_cost !== null ? `$${invocation.estimated_cost.toFixed(6)}` : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}
