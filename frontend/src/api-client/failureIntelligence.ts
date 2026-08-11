import { apiClient } from './client'
import type { AnalysisRunTriggered, FailureFinding, FailureIntelligenceRequest } from './types'

export const failureIntelligenceApi = {
  trigger: (repoId: string, payload: FailureIntelligenceRequest): Promise<AnalysisRunTriggered> =>
    apiClient.post(`/api/v1/repositories/${repoId}/failure-intelligence`, payload),
  listFindings: (repoId: string): Promise<FailureFinding[]> =>
    apiClient.get(`/api/v1/repositories/${repoId}/failure-findings`),
}
