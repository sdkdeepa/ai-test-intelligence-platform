import { Navigate, Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { RepositoryOverviewPage } from './pages/RepositoryOverviewPage'
import { RiskAnalysisPage } from './pages/RiskAnalysisPage'
import { TestSuggestionsPage } from './pages/TestSuggestionsPage'
import { FailureIntelligencePage } from './pages/FailureIntelligencePage'
import { AnalysisRunHistoryPage } from './pages/AnalysisRunHistoryPage'
import { HumanReviewPage } from './pages/HumanReviewPage'

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
        <Route path="*" element={<Navigate to="/repositories" replace />} />
      </Route>
    </Routes>
  )
}

export default App
