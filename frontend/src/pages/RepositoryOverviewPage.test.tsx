import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { renderWithProviders } from '../test/renderWithProviders'
import { RepositoryOverviewPage } from './RepositoryOverviewPage'
import { repositoriesApi } from '../api-client/repositories'
import type { Repository } from '../api-client/types'

vi.mock('../api-client/repositories', () => ({
  repositoriesApi: {
    list: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
  },
}))

const mockedRepositoriesApi = vi.mocked(repositoriesApi)

const SAMPLE_REPOS: Repository[] = [
  { id: 'repo-1', name: 'platform-backend', url: 'https://github.com/x/backend', default_branch: 'main' },
]

describe('RepositoryOverviewPage', () => {
  it('renders registered repositories', async () => {
    mockedRepositoriesApi.list.mockResolvedValue(SAMPLE_REPOS)

    renderWithProviders(<RepositoryOverviewPage />)

    expect(await screen.findByText('platform-backend')).toBeInTheDocument()
    expect(screen.getByText('https://github.com/x/backend')).toBeInTheDocument()
  })

  it('shows an empty state when there are no repositories', async () => {
    mockedRepositoriesApi.list.mockResolvedValue([])

    renderWithProviders(<RepositoryOverviewPage />)

    expect(await screen.findByText(/no repositories registered yet/i)).toBeInTheDocument()
  })

  it('shows an error state when the list request fails', async () => {
    mockedRepositoriesApi.list.mockRejectedValue(new Error('network down'))

    renderWithProviders(<RepositoryOverviewPage />)

    expect(await screen.findByText(/failed to load repositories/i)).toBeInTheDocument()
  })

  it('submits the registration form and clears it on success', async () => {
    mockedRepositoriesApi.list.mockResolvedValue([])
    mockedRepositoriesApi.create.mockResolvedValue({
      id: 'repo-2',
      name: 'new-repo',
      url: 'https://github.com/x/new-repo',
      default_branch: 'main',
    })
    const user = userEvent.setup()

    renderWithProviders(<RepositoryOverviewPage />)
    await screen.findByText(/no repositories registered yet/i)

    await user.type(screen.getByLabelText('Name'), 'new-repo')
    await user.type(screen.getByLabelText('URL'), 'https://github.com/x/new-repo')
    await user.click(screen.getByRole('button', { name: /register repository/i }))

    await waitFor(() => {
      expect(mockedRepositoriesApi.create).toHaveBeenCalledWith({
        name: 'new-repo',
        url: 'https://github.com/x/new-repo',
        default_branch: 'main',
      })
    })
    await waitFor(() => {
      expect(screen.getByLabelText('Name')).toHaveValue('')
    })
  })
})
