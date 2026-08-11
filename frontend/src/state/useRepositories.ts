import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { repositoriesApi } from '../api-client/repositories'
import type { RepositoryCreate } from '../api-client/types'

export function useRepositories() {
  return useQuery({ queryKey: ['repositories'], queryFn: repositoriesApi.list })
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
