import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { reviewQueueApi } from '../api-client/review'
import type { ReviewDecisionRequest } from '../api-client/types'

export function usePendingReviewRequests() {
  return useQuery({ queryKey: ['review-queue', 'pending'], queryFn: () => reviewQueueApi.list('pending') })
}

export function useReviewRequest(reviewRequestId: string | undefined) {
  return useQuery({
    queryKey: ['review-queue', reviewRequestId],
    queryFn: () => reviewQueueApi.get(reviewRequestId as string),
    enabled: reviewRequestId !== undefined,
  })
}

export function useReviewAuditEvents(reviewRequestId: string | undefined) {
  return useQuery({
    queryKey: ['review-queue', reviewRequestId, 'audit-events'],
    queryFn: () => reviewQueueApi.listAuditEvents(reviewRequestId as string),
    enabled: reviewRequestId !== undefined,
  })
}

export function useApproveReviewRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ReviewDecisionRequest }) => reviewQueueApi.approve(id, payload),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({ queryKey: ['review-queue'] })
      void queryClient.invalidateQueries({ queryKey: ['review-queue', id, 'audit-events'] })
    },
  })
}

export function useRejectReviewRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ReviewDecisionRequest }) => reviewQueueApi.reject(id, payload),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({ queryKey: ['review-queue'] })
      void queryClient.invalidateQueries({ queryKey: ['review-queue', id, 'audit-events'] })
    },
  })
}
