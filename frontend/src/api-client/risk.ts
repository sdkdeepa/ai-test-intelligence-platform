import { apiClient } from './client'
import type { AnalysisRunTriggered, RiskAnalysisRequest, RiskFinding } from './types'

export const riskApi = {
  trigger: (repoId: string, payload: RiskAnalysisRequest): Promise<AnalysisRunTriggered> =>
    apiClient.post(`/api/v1/repositories/${repoId}/risk-analysis`, payload),
  listFindings: (repoId: string): Promise<RiskFinding[]> =>
    apiClient.get(`/api/v1/repositories/${repoId}/risk-findings`),
}
