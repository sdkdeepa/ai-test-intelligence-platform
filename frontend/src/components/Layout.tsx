import { NavLink, Outlet, useParams } from 'react-router-dom'

import { useRepository } from '../state/useRepositories'
import './Layout.css'

const REPO_TABS = [
  { to: 'risk', label: 'Risk Analysis' },
  { to: 'test-suggestions', label: 'Test Suggestions' },
  { to: 'failure-intelligence', label: 'Failure Intelligence' },
  { to: 'runs', label: 'Run History' },
]

export function Layout() {
  const { repoId } = useParams<{ repoId?: string }>()
  const { data: repository } = useRepository(repoId)

  return (
    <div className="app-shell">
      <header className="top-nav">
        <span className="top-nav__brand">AI Test Intelligence Platform</span>
        <nav className="top-nav__links">
          <NavLink to="/repositories" className="top-nav__link">
            Repositories
          </NavLink>
          <NavLink to="/review" className="top-nav__link">
            Human Review
          </NavLink>
        </nav>
      </header>

      {repoId && (
        <div className="repo-nav">
          <span className="repo-nav__name">{repository?.name ?? repoId}</span>
          <nav className="repo-nav__tabs">
            {REPO_TABS.map((tab) => (
              <NavLink key={tab.to} to={`/repositories/${repoId}/${tab.to}`} className="repo-nav__tab">
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </div>
      )}

      <main className="app-content">
        <Outlet />
      </main>
    </div>
  )
}
