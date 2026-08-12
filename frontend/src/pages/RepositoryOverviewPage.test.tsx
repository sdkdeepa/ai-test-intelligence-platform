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
    archive: vi.fn(),
    unarchive: vi.fn(),
  },
}))

const mockedRepositoriesApi = vi.mocked(repositoriesApi)

const SAMPLE_REPOS: Repository[] = [
  { id: 'repo-1', name: 'platform-backend', url: 'https://github.com/x/backend', default_branch: 'main', is_active: true },
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
      is_active: true,
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

  it('archives an active repository', async () => {
    mockedRepositoriesApi.list.mockResolvedValue(SAMPLE_REPOS)
    mockedRepositoriesApi.archive.mockResolvedValue({ ...SAMPLE_REPOS[0], is_active: false })
    const user = userEvent.setup()

    renderWithProviders(<RepositoryOverviewPage />)
    await screen.findByText('platform-backend')

    await user.click(screen.getByRole('button', { name: /^archive$/i }))

    await waitFor(() => {
      expect(mockedRepositoriesApi.archive).toHaveBeenCalledWith('repo-1')
    })
  })

  it('does not show archived repositories by default', async () => {
    mockedRepositoriesApi.list.mockImplementation((includeArchived) =>
      Promise.resolve(includeArchived ? SAMPLE_REPOS : []),
    )

    renderWithProviders(<RepositoryOverviewPage />)

    expect(await screen.findByText(/no repositories registered yet/i)).toBeInTheDocument()
    expect(mockedRepositoriesApi.list).toHaveBeenCalledWith(false)
  })

  it('shows archived repositories and an unarchive action when the toggle is checked', async () => {
    const archivedRepo = { ...SAMPLE_REPOS[0], is_active: false }
    mockedRepositoriesApi.list.mockImplementation((includeArchived) =>
      Promise.resolve(includeArchived ? [archivedRepo] : []),
    )
    mockedRepositoriesApi.unarchive.mockResolvedValue({ ...archivedRepo, is_active: true })
    const user = userEvent.setup()

    renderWithProviders(<RepositoryOverviewPage />)
    await screen.findByText(/no repositories registered yet/i)

    await user.click(screen.getByLabelText(/show archived repositories/i))

    expect(await screen.findByText('platform-backend')).toBeInTheDocument()
    expect(screen.getByText('Archived')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /unarchive/i }))
    await waitFor(() => {
      expect(mockedRepositoriesApi.unarchive).toHaveBeenCalledWith('repo-1')
    })
  })
})
