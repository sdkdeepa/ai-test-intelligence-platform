import { Component, type ErrorInfo, type ReactNode } from 'react'

import './AsyncState.css'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * Sprint 14 hardening: without this, an uncaught render error anywhere in
 * the tree — a bad API response shape, a bug in a page component — crashes
 * to a blank white screen with nothing but a browser console error. React's
 * error boundaries can only be class components (there's no Hook
 * equivalent as of this writing), which is why this is the one class
 * component in an otherwise all-function-component codebase.
 *
 * Deliberately minimal: no retry-with-backoff, no error reporting service
 * integration (there isn't one configured — see README's Production Gaps).
 * The goal here is "the user sees a message instead of a blank page and can
 * reload", not full crash recovery.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console -- this is the fallback path;
    // there's no structured client-side logging/error-reporting pipeline
    // to send this to instead (see README's Production Gaps).
    console.error('Unhandled error in the dashboard UI:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="async-state async-state--error" role="alert" style={{ padding: '2rem' }}>
          <p>Something went wrong loading this page.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
