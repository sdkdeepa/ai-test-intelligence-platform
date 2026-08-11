import { apiClient } from './client'
import type { AuditEvent, ReviewDecisionRequest, ReviewRequest } from './types'

export const reviewQueueApi = {
  list: (status = 'pending'): Promise<ReviewRequest[]> =>
    apiClient.get(`/api/v1/review-queue?status=${encodeURIComponent(status)}`),
  get: (reviewRequestId: string): Promise<ReviewRequest> => apiClient.get(`/api/v1/review-queue/${reviewRequestId}`),
  listAuditEvents: (reviewRequestId: string): Promise<AuditEvent[]> =>
    apiClient.get(`/api/v1/review-queue/${reviewRequestId}/audit-events`),
  approve: (reviewRequestId: string, payload: ReviewDecisionRequest): Promise<ReviewRequest> =>
    apiClient.post(`/api/v1/review-queue/${reviewRequestId}/approve`, payload),
  reject: (reviewRequestId: string, payload: ReviewDecisionRequest): Promise<ReviewRequest> =>
    apiClient.post(`/api/v1/review-queue/${reviewRequestId}/reject`, payload),
}
