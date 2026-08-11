import { apiClient } from './client'
import type { Repository, RepositoryCreate } from './types'

export const repositoriesApi = {
  list: (): Promise<Repository[]> => apiClient.get('/api/v1/repositories'),
  get: (repoId: string): Promise<Repository> => apiClient.get(`/api/v1/repositories/${repoId}`),
  create: (payload: RepositoryCreate): Promise<Repository> => apiClient.post('/api/v1/repositories', payload),
}
