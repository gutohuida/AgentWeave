/**
 * The trace drawer must give TraceView a bounded height, or its two overflow-auto panes grow to
 * their content and the Drawer's overflow-hidden clips them (nothing scrolls). jsdom has no layout,
 * so this asserts the structure that bounds it: a flex column filling the drawer body, a shrink-0
 * header, and a flex-1 min-h-0 trace-detail wrapper — for both the panel and the Trace button.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { TraceButton, TraceDrawerPanel } from '@/components/traces/TraceDrawer'

vi.mock('@/api/traces', () => ({
  useRunTrace: () => ({ data: undefined, isLoading: true, error: null }),
  useTrace: () => ({ data: undefined, isLoading: true, error: null }),
}))

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

afterEach(cleanup)

function expectBounded(detail: HTMLElement) {
  expect(detail.className).toContain('flex-1')
  expect(detail.className).toContain('min-h-0')
  const column = detail.parentElement!
  expect(column.className).toContain('flex-col')
  expect(column.className).toContain('h-full')
  expect(column.className).toContain('min-h-0')
}

describe('trace drawer scroll bounds', () => {
  it('panel: header is shrink-0 above a flex-1 trace-detail in one column', () => {
    render(
      <TraceDrawerPanel runId="run-1" open onOpenChange={vi.fn()} header={<span>Run header</span>} />,
      { wrapper },
    )
    const detail = screen.getByTestId('trace-detail')
    expectBounded(detail)
    const header = screen.getByText('Run header').parentElement!
    expect(header.className).toContain('shrink-0')
    expect(header.parentElement).toBe(detail.parentElement)
  })

  it('Trace button drawer: trace-detail is bounded the same way', () => {
    render(<TraceButton runId="run-1" testId="tb" />, { wrapper })
    fireEvent.click(screen.getByTestId('tb'))
    expectBounded(screen.getByTestId('trace-detail'))
  })
})
