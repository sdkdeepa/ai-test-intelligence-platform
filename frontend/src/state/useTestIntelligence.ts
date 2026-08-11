import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { testIntelligenceApi } from '../api-client/testIntelligence'
import type { TestIntelligenceRequest } from '../api-client/types'

export function useTestSuggestions(repoId: string | undefined) {
  return useQuery({
    queryKey: ['repositories', repoId, 'test-suggestions'],
    queryFn: () => testIntelligenceApi.listSuggestions(repoId as string),
    enabled: repoId !== undefined,
  })
}

export function useTriggerTestIntelligence(repoId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: TestIntelligenceRequest) => testIntelligenceApi.trigger(repoId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories', repoId, 'analysis-runs'] })
    },
  })
}

export function useAcceptTestSuggestion(repoId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (suggestionId: string) => testIntelligenceApi.accept(suggestionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories', repoId, 'test-suggestions'] })
      void queryClient.invalidateQueries({ queryKey: ['pending-test-suggestions'] })
    },
  })
}

export function useRejectTestSuggestion(repoId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (suggestionId: string) => testIntelligenceApi.reject(suggestionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories', repoId, 'test-suggestions'] })
      void queryClient.invalidateQueries({ queryKey: ['pending-test-suggestions'] })
    },
  })
}
