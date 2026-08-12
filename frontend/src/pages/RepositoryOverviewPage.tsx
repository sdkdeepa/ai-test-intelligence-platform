import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { Button, TextField } from '../components/form'
import { Card } from '../components/Card'
import { useArchiveRepository, useCreateRepository, useRepositories, useUnarchiveRepository } from '../state/useRepositories'
import { ApiError } from '../api-client/client'
import './RepositoryOverviewPage.css'

export function RepositoryOverviewPage() {
  const [includeArchived, setIncludeArchived] = useState(false)
  const { data: repositories, isLoading, isError } = useRepositories(includeArchived)
  const createRepository = useCreateRepository()
  const archiveRepository = useArchiveRepository()
  const unarchiveRepository = useUnarchiveRepository()

  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [defaultBranch, setDefaultBranch] = useState('main')
  const [formError, setFormError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    createRepository.mutate(
      { name, url, default_branch: defaultBranch || 'main' },
      {
        onSuccess: () => {
          setName('')
          setUrl('')
          setDefaultBranch('main')
        },
        onError: (error) => {
          setFormError(error instanceof ApiError ? error.message : 'Failed to register repository.')
        },
      },
    )
  }

  return (
    <div className="repo-overview">
      <h1 className="page-title">Repository Overview</h1>
      <p className="page-subtitle">Registered repositories and their analysis history.</p>

      <div className="repo-overview__grid">
        <Card title="Registered Repositories">
          <label className="repo-overview__archive-toggle">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
            />
            Show archived repositories
          </label>

          {isLoading && <LoadingState label="Loading repositories…" />}
          {isError && <ErrorState message="Failed to load repositories." />}
          {repositories && repositories.length === 0 && (
            <EmptyState message="No repositories registered yet — add one to get started." />
          )}
          {repositories && repositories.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>URL</th>
                  <th>Default Branch</th>
                  <th />
                  <th />
                </tr>
              </thead>
              <tbody>
                {repositories.map((repo) => (
                  <tr key={repo.id} className={repo.is_active ? undefined : 'repo-overview__row--archived'}>
                    <td>
                      {repo.name}
                      {!repo.is_active && <span className="repo-overview__archived-badge">Archived</span>}
                    </td>
                    <td className="data-table__mono">{repo.url}</td>
                    <td>{repo.default_branch}</td>
                    <td>
                      <Link to={`/repositories/${repo.id}/risk`}>Open</Link>
                    </td>
                    <td>
                      {repo.is_active ? (
                        <button
                          type="button"
                          className="repo-overview__archive-button"
                          disabled={archiveRepository.isPending}
                          onClick={() => archiveRepository.mutate(repo.id)}
                        >
                          Archive
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="repo-overview__archive-button"
                          disabled={unarchiveRepository.isPending}
                          onClick={() => unarchiveRepository.mutate(repo.id)}
                        >
                          Unarchive
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Register a Repository">
          <form onSubmit={handleSubmit}>
            <TextField
              label="Name"
              htmlFor="repo-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <TextField
              label="URL"
              htmlFor="repo-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/org/repo"
              required
            />
            <TextField
              label="Default Branch"
              htmlFor="repo-default-branch"
              value={defaultBranch}
              onChange={(e) => setDefaultBranch(e.target.value)}
            />
            {formError && <ErrorState message={formError} />}
            <Button type="submit" disabled={createRepository.isPending}>
              {createRepository.isPending ? 'Registering…' : 'Register Repository'}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  )
}
