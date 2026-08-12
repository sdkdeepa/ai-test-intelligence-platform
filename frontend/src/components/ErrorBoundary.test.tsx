import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import { ErrorBoundary } from './ErrorBoundary'

function Boom(): never {
  throw new Error('simulated render crash')
}

describe('ErrorBoundary', () => {
  it('renders children normally when nothing throws', () => {
    render(
      <ErrorBoundary>
        <p>all fine</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('all fine')).toBeInTheDocument()
  })

  it('renders a fallback message instead of crashing when a child throws', () => {
    // React logs the error to the console by default even when caught by a
    // boundary — suppress that expected noise for this test only.
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()

    consoleErrorSpy.mockRestore()
  })
})
