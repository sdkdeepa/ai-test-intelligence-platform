import { apiClient } from './client'
import type { Repository, RepositoryCreate } from './types'

export const repositoriesApi = {
  list: (includeArchived = false): Promise<Repository[]> =>
    apiClient.get(`/api/v1/repositories${includeArchived ? '?include_archived=true' : ''}`),
  get: (repoId: string): Promise<Repository> => apiClient.get(`/api/v1/repositories/${repoId}`),
  create: (payload: RepositoryCreate): Promise<Repository> => apiClient.post('/api/v1/repositories', payload),
  archive: (repoId: string): Promise<Repository> => apiClient.post(`/api/v1/repositories/${repoId}/archive`),
  unarchive: (repoId: string): Promise<Repository> => apiClient.post(`/api/v1/repositories/${repoId}/unarchive`),
}
