import { useQuery } from '@tanstack/react-query'

import { analysisRunsApi } from '../api-client/analysisRuns'

const TERMINAL_STATES = new Set(['completed', 'failed'])

export function useAnalysisRuns(repoId: string | undefined) {
  return useQuery({
    queryKey: ['repositories', repoId, 'analysis-runs'],
    queryFn: () => analysisRunsApi.list(repoId as string),
    enabled: repoId !== undefined,
  })
}

export function useLLMInvocations(repoId: string | undefined, runId: string | undefined) {
  return useQuery({
    queryKey: ['repositories', repoId, 'analysis-runs', runId, 'llm-invocations'],
    queryFn: () => analysisRunsApi.listLLMInvocations(repoId as string, runId as string),
    enabled: repoId !== undefined && runId !== undefined,
  })
}

/**
 * Polls a just-triggered analysis run's status until it reaches a terminal
 * state (completed/failed), then stops. `onTerminal` is how callers refresh
 * the findings list that just became current.
 */
export function usePollAnalysisRunStatus(
  repoId: string | undefined,
  runId: string | undefined,
  onTerminal?: () => void,
) {
  return useQuery({
    queryKey: ['repositories', repoId, 'analysis-runs', runId, 'status'],
    queryFn: async () => {
      const result = await analysisRunsApi.getStatus(repoId as string, runId as string)
      if (TERMINAL_STATES.has(result.status)) {
        onTerminal?.()
      }
      return result
    },
    enabled: repoId !== undefined && runId !== undefined,
    refetchInterval: (query) => (query.state.data && TERMINAL_STATES.has(query.state.data.status) ? false : 750),
  })
}
