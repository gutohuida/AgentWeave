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
    current_task: null,
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

  it('shows the indicator alongside an ending-state badge — firing_active and history are independent facts', () => {
    mockedUseLoop.mockReturnValue({
      data: baseLoop({ firing_active: true, ending_state: null }),
      isLoading: false,
      isError: false,
    } as never)
    render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)

    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByTestId('loop-tab-firing-active')).toBeInTheDocument()
  })
})
