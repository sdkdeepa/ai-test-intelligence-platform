import { useQueries, useQuery } from '@tanstack/react-query'

import { repositoriesApi } from '../api-client/repositories'
import { testIntelligenceApi } from '../api-client/testIntelligence'
import type { Repository, TestSuggestion } from '../api-client/types'

export interface PendingReviewItem {
  repo: Repository
  suggestion: TestSuggestion
}

/**
 * There's no cross-repo "list all pending test suggestions" endpoint (each
 * repository's suggestions are scoped to it — see api-client/testIntelligence.ts),
 * so the review queue is built client-side: list repositories, fetch each
 * one's suggestions, and filter to pending. Fine at this platform's current
 * scale; would need a dedicated backend aggregation endpoint if the number
 * of registered repositories grew large.
 */
export function usePendingReview() {
  const repositories = useQuery({ queryKey: ['repositories'], queryFn: () => repositoriesApi.list() })

  const suggestionQueries = useQueries({
    queries: (repositories.data ?? []).map((repo) => ({
      queryKey: ['repositories', repo.id, 'test-suggestions'],
      queryFn: () => testIntelligenceApi.listSuggestions(repo.id),
      enabled: repositories.isSuccess,
    })),
  })

  const isLoading = repositories.isLoading || suggestionQueries.some((q) => q.isLoading)
  const isError = repositories.isError || suggestionQueries.some((q) => q.isError)

  const items: PendingReviewItem[] = []
  if (repositories.data) {
    repositories.data.forEach((repo, index) => {
      const suggestions = suggestionQueries[index]?.data ?? []
      for (const suggestion of suggestions) {
        if (suggestion.status === 'pending') {
          items.push({ repo, suggestion })
        }
      }
    })
  }

  return { items, isLoading, isError }
}
