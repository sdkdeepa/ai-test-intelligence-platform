import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { repositoriesApi } from '../api-client/repositories'
import type { RepositoryCreate } from '../api-client/types'

export function useRepositories(includeArchived = false) {
  return useQuery({
    queryKey: ['repositories', { includeArchived }],
    queryFn: () => repositoriesApi.list(includeArchived),
  })
}

export function useRepository(repoId: string | undefined) {
  return useQuery({
    queryKey: ['repositories', repoId],
    queryFn: () => repositoriesApi.get(repoId as string),
    enabled: repoId !== undefined,
  })
}

export function useCreateRepository() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: RepositoryCreate) => repositoriesApi.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] })
    },
  })
}

export function useArchiveRepository() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (repoId: string) => repositoriesApi.archive(repoId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] })
    },
  })
}

export function useUnarchiveRepository() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (repoId: string) => repositoriesApi.unarchive(repoId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] })
    },
  })
}
