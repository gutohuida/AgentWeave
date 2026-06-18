import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'

function ThrowingChild(_props: { message: string }): ReactElement {
  throw new Error(_props.message)
}

function GoodChild() {
  return <div>good child</div>
}

describe('ErrorBoundary — catches render-phase errors in children', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    // React logs caught errors to console.error; silence for clean output.
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    errorSpy.mockRestore()
  })

  it('renders children when no error is thrown', () => {
    render(
      <ErrorBoundary>
        <GoodChild />
      </ErrorBoundary>
    )
    expect(screen.getByText('good child')).toBeInTheDocument()
  })

  it('renders the fallback UI when a child throws and logs the error', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild message="boom" />
      </ErrorBoundary>
    )
    // Fallback should be visible (not the original child).
    expect(screen.queryByText('good child')).not.toBeInTheDocument()
    // The fallback should contain some user-facing error text. We don't
    // hard-code the exact wording to keep the test resilient to copy
    // changes, but it must include a "try again" / "reload" affordance.
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(0)
    expect(errorSpy).toHaveBeenCalled()
  })
})
