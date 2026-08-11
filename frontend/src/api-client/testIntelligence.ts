import { apiClient } from './client'
import type { AnalysisRunTriggered, TestIntelligenceRequest, TestSuggestion } from './types'

export const testIntelligenceApi = {
  trigger: (repoId: string, payload: TestIntelligenceRequest): Promise<AnalysisRunTriggered> =>
    apiClient.post(`/api/v1/repositories/${repoId}/test-intelligence`, payload),
  listSuggestions: (repoId: string): Promise<TestSuggestion[]> =>
    apiClient.get(`/api/v1/repositories/${repoId}/test-suggestions`),
  accept: (suggestionId: string): Promise<TestSuggestion> =>
    apiClient.post(`/api/v1/test-suggestions/${suggestionId}/accept`),
  reject: (suggestionId: string): Promise<TestSuggestion> =>
    apiClient.post(`/api/v1/test-suggestions/${suggestionId}/reject`),
}
