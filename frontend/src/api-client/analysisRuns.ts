import { apiClient } from './client'
import type { AnalysisRun, AnalysisRunTriggered, LLMInvocation } from './types'

export const analysisRunsApi = {
  list: (repoId: string): Promise<AnalysisRun[]> => apiClient.get(`/api/v1/repositories/${repoId}/analysis-runs`),
  getStatus: (repoId: string, runId: string): Promise<AnalysisRunTriggered> =>
    apiClient.get(`/api/v1/repositories/${repoId}/analysis-runs/${runId}`),
  listLLMInvocations: (repoId: string, runId: string): Promise<LLMInvocation[]> =>
    apiClient.get(`/api/v1/repositories/${repoId}/analysis-runs/${runId}/llm-invocations`),
}
