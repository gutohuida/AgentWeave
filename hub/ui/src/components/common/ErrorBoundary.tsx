import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Icon } from './Icon'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: (error: Error, reset: () => void) => ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * Top-level error boundary. Catches render-phase errors anywhere in the
 * descendant tree and shows a user-friendly fallback instead of a blank
 * page. The error is also forwarded to console.error so it shows up in
 * DevTools and the structured event log.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] caught render error', error, info)
  }

  reset = (): void => {
    this.setState({ error: null })
  }

  render() {
    const { error } = this.state
    if (error === null) return this.props.children
    if (this.props.fallback) return this.props.fallback(error, this.reset)

    return (
      <div
        className="flex h-screen flex-col items-center justify-center gap-4 p-8 text-center"
        style={{ background: 'var(--bg)', color: 'var(--text)' }}
        role="alert"
      >
        <div
          className="flex items-center justify-center rounded-full"
          style={{ width: 64, height: 64, background: 'rgba(239,68,68,0.15)' }}
        >
          <Icon name="error_outline" size={32} style={{ color: 'var(--red)' }} />
        </div>
        <h1 className="text-lg font-medium">Something went wrong</h1>
        <p className="max-w-md text-sm" style={{ color: 'var(--text-3)' }}>
          The dashboard hit an unexpected error and could not recover automatically.
          The details have been written to the browser console.
        </p>
        {error.message && (
          <pre
            className="max-w-2xl overflow-auto rounded-lg p-3 text-left text-xs"
            style={{ background: 'var(--surface)', color: 'var(--red)' }}
          >
            {error.message}
          </pre>
        )}
        <button
          type="button"
          onClick={this.reset}
          className="rounded-lg px-4 py-2 text-sm"
          style={{ background: 'var(--blue)', color: '#fff' }}
        >
          Try again
        </button>
      </div>
    )
  }
}
