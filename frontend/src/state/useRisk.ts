import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { riskApi } from '../api-client/risk'
import type { RiskAnalysisRequest } from '../api-client/types'

export function useRiskFindings(repoId: string | undefined) {
  return useQuery({
    queryKey: ['repositories', repoId, 'risk-findings'],
    queryFn: () => riskApi.listFindings(repoId as string),
    enabled: repoId !== undefined,
  })
}

export function useTriggerRiskAnalysis(repoId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: RiskAnalysisRequest) => riskApi.trigger(repoId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories', repoId, 'analysis-runs'] })
    },
  })
}
