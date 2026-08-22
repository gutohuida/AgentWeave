import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Icon } from './Icon'
import { Button } from '@/components/ui/button'

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
      <div className="flex h-screen items-center justify-center p-8" style={{ background: 'var(--bg)', color: 'var(--text)' }} role="alert">
        <div className="trust-state">
        <div
          className="trust-state-icon is-error"
        >
          <Icon name="error_outline" size={24} />
        </div>
        <h1 className="text-lg font-semibold">Something went wrong</h1>
        <p className="mx-auto mt-2 max-w-md text-sm" style={{ color: 'var(--text-3)' }}>
          The dashboard hit an unexpected error and could not recover automatically.
          The details have been written to the browser console.
        </p>
        {error.message && (
          <pre
            className="mx-auto mt-4 max-w-full whitespace-pre-wrap break-words rounded-[var(--radius-lg)] border p-3 text-left text-xs"
            style={{ background: 'var(--surface-2)', borderColor: 'var(--border)', color: 'var(--red)' }}
          >
            {error.message}
          </pre>
        )}
        <Button className="mt-4" variant="primary" size="md" onClick={this.reset}>
          Try again
        </Button>
        </div>
      </div>
    )
  }
}
