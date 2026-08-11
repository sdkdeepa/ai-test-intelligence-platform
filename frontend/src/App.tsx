import { Navigate, Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { RepositoryOverviewPage } from './pages/RepositoryOverviewPage'
import { RiskAnalysisPage } from './pages/RiskAnalysisPage'
import { TestSuggestionsPage } from './pages/TestSuggestionsPage'
import { FailureIntelligencePage } from './pages/FailureIntelligencePage'
import { AnalysisRunHistoryPage } from './pages/AnalysisRunHistoryPage'
import { HumanReviewPage } from './pages/HumanReviewPage'
import { ReviewQueuePage } from './pages/ReviewQueuePage'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/repositories" replace />} />
        <Route path="/repositories" element={<RepositoryOverviewPage />} />
        <Route path="/repositories/:repoId/risk" element={<RiskAnalysisPage />} />
        <Route path="/repositories/:repoId/test-suggestions" element={<TestSuggestionsPage />} />
        <Route path="/repositories/:repoId/failure-intelligence" element={<FailureIntelligencePage />} />
        <Route path="/repositories/:repoId/runs" element={<AnalysisRunHistoryPage />} />
        <Route path="/review" element={<HumanReviewPage />} />
        {/* :reviewRequestId is accepted but unused by the page itself today (it
            always lists the full pending queue) — PR comments and commit
            status target_urls (integrations/github/publisher.py) link to a
            specific /review-queue/{id}, and this route exists so those links
            resolve to something rather than 404ing into the catch-all. */}
        <Route path="/review-queue" element={<ReviewQueuePage />} />
        <Route path="/review-queue/:reviewRequestId" element={<ReviewQueuePage />} />
        <Route path="*" element={<Navigate to="/repositories" replace />} />
      </Route>
    </Routes>
  )
}

export default App
