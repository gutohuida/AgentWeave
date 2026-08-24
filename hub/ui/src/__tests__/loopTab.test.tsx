import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LoopTab } from '@/components/spec/LoopTab'
import { useLoop } from '@/api/loops'
import type { LoopDetail } from '@/api/loops'

vi.mock('@/api/loops', () => ({
  useLoop: vi.fn(),
}))

const mockedUseLoop = vi.mocked(useLoop)

afterEach(() => cleanup())

function baseLoop(overrides: Partial<LoopDetail> = {}): LoopDetail {
  return {
    id: 'loop-1',
    job_id: 'job-1',
    label: 'nightly sweep',
    purpose: 'sweep the queue',
    stop_when_queue_empties: true,
    ending_state: null,
    archived_at: null,
    queue: { pending: 2 },
    current_tasks: [],
    open_questions: 0,
    firing_active: false,
    history: [],
    events: [],
    ...overrides,
  }
}

describe('LoopTab — the active-now indicator (task B6.2/B6.3, 2026-08-18-a-loop-writes-its-own-queue)', () => {
  it('shows no "Running now" indicator when firing_active is false', () => {
    mockedUseLoop.mockReturnValue({
      data: baseLoop({ firing_active: false }),
      isLoading: false,
      isError: false,
    } as never)
    render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)

    expect(screen.queryByTestId('loop-tab-firing-active')).not.toBeInTheDocument()
  })

  it('shows the "Running now" indicator, with its motion on a CSS animate-pulse dot, when firing_active is true', () => {
    mockedUseLoop.mockReturnValue({
      data: baseLoop({ firing_active: true }),
      isLoading: false,
      isError: false,
    } as never)
    render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)

    const indicator = screen.getByTestId('loop-tab-firing-active')
    expect(indicator).toHaveTextContent('Running now')
    // B6.3: motion lives on a CSS class (Tailwind's animate-pulse), not a component-level
    // matchMedia check — index.css's blanket prefers-reduced-motion rule handles the rest.
    expect(indicator.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('lets the live pill carry "running" rather than claiming it as an ending state too', () => {
    // `ending_state: null` is the *absence* of an ending, not an ending called "running". The
    // header used to render a "Running" badge for it, which both duplicated the animated pill
    // beside it and — the actual defect — labelled a loop that had never fired as running.
    mockedUseLoop.mockReturnValue({
      data: baseLoop({ firing_active: true, ending_state: null }),
      isLoading: false,
      isError: false,
    } as never)
    render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)

    expect(screen.getByTestId('loop-tab-firing-active')).toBeInTheDocument()
    expect(screen.queryByText('Idle')).not.toBeInTheDocument()
  })

  it('reads Idle for a loop that has neither ended nor started firing', () => {
    // The case the operator hit: a paused job whose loop had never fired once, reported as
    // running on both the index and this tab.
    mockedUseLoop.mockReturnValue({
      data: baseLoop({ firing_active: false, ending_state: null }),
      isLoading: false,
      isError: false,
    } as never)
    render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)

    expect(screen.getByText('Idle')).toBeInTheDocument()
    expect(screen.queryByTestId('loop-tab-firing-active')).not.toBeInTheDocument()
  })
})
