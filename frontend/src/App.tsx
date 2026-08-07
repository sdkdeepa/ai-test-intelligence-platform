import './App.css'

const PLACEHOLDER_SECTIONS = [
  {
    title: 'Risk Findings',
    description: 'Coverage and risk scoring for changed code will appear here.',
  },
  {
    title: 'Test Suggestions',
    description: 'AI-generated test suggestions for undertested code will appear here.',
  },
  {
    title: 'Flaky Tests',
    description: 'CI failure triage and flaky-test clustering will appear here.',
  },
]

function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>AI Test Intelligence Platform</h1>
        <p>Repository scaffold — no analysis data is wired up yet.</p>
      </header>

      <main className="dashboard-grid">
        {PLACEHOLDER_SECTIONS.map((section) => (
          <section key={section.title} className="dashboard-card">
            <h2>{section.title}</h2>
            <p>{section.description}</p>
          </section>
        ))}
      </main>
    </div>
  )
}

export default App
