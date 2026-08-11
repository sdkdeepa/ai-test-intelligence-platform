import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { failureIntelligenceApi } from '../api-client/failureIntelligence'
import type { FailureIntelligenceRequest } from '../api-client/types'

export function useFailureFindings(repoId: string | undefined) {
  return useQuery({
    queryKey: ['repositories', repoId, 'failure-findings'],
    queryFn: () => failureIntelligenceApi.listFindings(repoId as string),
    enabled: repoId !== undefined,
  })
}

export function useTriggerFailureIntelligence(repoId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: FailureIntelligenceRequest) => failureIntelligenceApi.trigger(repoId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories', repoId, 'analysis-runs'] })
    },
  })
}
