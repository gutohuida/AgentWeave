import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LoopTab } from '@/components/spec/LoopTab'
import { ApiError } from '@/api/client'
import { useLoop, useStopLoop, useArchiveLoop, useSetLoopControl } from '@/api/loops'
import { useAgents } from '@/api/agents'
import type { LoopDetail } from '@/api/loops'

vi.mock('@/api/loops', () => ({
  useLoop: vi.fn(),
  useStopLoop: vi.fn(),
  useArchiveLoop: vi.fn(),
  useSetLoopControl: vi.fn(),
}))
vi.mock('@/api/agents', () => ({ useAgents: vi.fn() }))

const stop = vi.fn()
const archive = vi.fn()
const setControl = vi.fn()

function idle(fn: typeof stop, extra: Record<string, unknown> = {}) {
  return { mutate: fn, isPending: false, isError: false, error: null, ...extra } as never
}

function baseLoop(overrides: Partial<LoopDetail> = {}): LoopDetail {
  return {
    id: 'loop-1',
    job_id: 'job-1',
    label: 'nightly sweep',
    purpose: 'sweep the queue',
    stop_when_queue_empties: true,
    ending_state: null,
    archived_at: null,
    control: null,
    agent: 'worker',
    queue: { pending: 2 },
    current_tasks: [],
    open_questions: 0,
    firing_active: false,
    history: [],
    events: [],
    ...overrides,
  }
}

function show(loop: LoopDetail) {
  vi.mocked(useLoop).mockReturnValue({ data: loop, isLoading: false, isError: false } as never)
  render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)
}

beforeEach(() => {
  stop.mockReset()
  archive.mockReset()
  setControl.mockReset()
  vi.mocked(useStopLoop).mockReturnValue(idle(stop))
  vi.mocked(useArchiveLoop).mockReturnValue(idle(archive))
  vi.mocked(useSetLoopControl).mockReturnValue(idle(setControl))
  vi.mocked(useAgents).mockReturnValue({ data: [] } as never)
})
afterEach(() => cleanup())

describe('LoopTab — its own actions (task 1.5-1.10a)', () => {
  it('a running loop offers Stop and delegation, not Archive', () => {
    show(baseLoop())
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
    expect(screen.getByTestId('loop-tab-controller')).toHaveTextContent('decided by you')

    fireEvent.click(screen.getByRole('button', { name: 'Let worker decide' }))
    expect(setControl).toHaveBeenCalledWith({ loopId: 'loop-1', control: 'creator' })
  })

  it('Stop asks first, sends the default reason, and says a running firing finishes', () => {
    show(baseLoop({ firing_active: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(screen.getByTestId('loop-tab-stop-confirm')).toHaveTextContent('The firing running now finishes')
    expect(stop).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Stop loop' }))
    expect(stop).toHaveBeenCalledWith({ jobId: 'job-1', reason: 'Stopped by the operator' })
  })

  it('Stop sends the typed reason trimmed, and a blank one falls back to the default', () => {
    show(baseLoop())
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    const field = screen.getByLabelText('Reason')
    fireEvent.change(field, { target: { value: '  enough  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Stop loop' }))
    expect(stop).toHaveBeenLastCalledWith({ jobId: 'job-1', reason: 'enough' })

    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Stop loop' }))
    expect(stop).toHaveBeenLastCalledWith({ jobId: 'job-1', reason: 'Stopped by the operator' })
  })

  it('an idle-firing loop says no firing starts after the stop', () => {
    show(baseLoop({ firing_active: false }))
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(screen.getByTestId('loop-tab-stop-confirm')).toHaveTextContent('No firing starts after this.')
  })

  it('an ended loop offers Archive only; an archived one offers nothing', () => {
    cleanup()
    show(baseLoop({ ending_state: 'stopped' }))
    expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
    expect(screen.queryByTestId('loop-tab-controller')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Archive' }))
    fireEvent.click(screen.getByRole('button', { name: 'Archive loop' }))
    expect(archive).toHaveBeenCalledWith({ loopId: 'loop-1' })

    cleanup()
    show(baseLoop({ ending_state: 'stopped', archived_at: '2026-09-27T00:00:00Z' }))
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
  })

  it('a delegated loop names the agent and offers to take control back', () => {
    show(baseLoop({ control: 'creator' }))
    expect(screen.getByTestId('loop-tab-controller')).toHaveTextContent('decided by worker')
    fireEvent.click(screen.getByRole('button', { name: 'Decide them yourself' }))
    expect(setControl).toHaveBeenCalledWith({ loopId: 'loop-1', control: 'operator' })
  })

  it('shows the Hub’s own sentence when an action fails, including a structured detail', () => {
    const detail = { code: 'loop_already_ended', message: 'this loop already ended (enough)' }
    vi.mocked(useStopLoop).mockReturnValue(
      idle(stop, { isError: true, error: new ApiError(409, JSON.stringify({ detail })) }),
    )
    show(baseLoop())
    expect(screen.getByRole('alert')).toHaveTextContent('this loop already ended (enough)')
  })

  it('falls back to a fixed sentence when the failure carries no detail', () => {
    vi.mocked(useSetLoopControl).mockReturnValue(idle(setControl, { isError: true, error: new Error('x') }))
    show(baseLoop())
    expect(screen.getByRole('alert')).toHaveTextContent('Could not change who decides this loop’s queue.')
  })

  it('hides the delegation toggle for a loop with no agent', () => {
    show(baseLoop({ agent: '' }))
    expect(screen.queryByRole('button', { name: /Let .* decide/ })).not.toBeInTheDocument()
    expect(screen.getByTestId('loop-tab-controller')).toBeInTheDocument()
  })

  it('hides the toggle when the agent is archived, and shows it otherwise', () => {
    vi.mocked(useAgents).mockReturnValue({ data: [{ name: 'worker', lifecycle: 'archived' }] } as never)
    show(baseLoop())
    expect(screen.queryByRole('button', { name: 'Let worker decide' })).not.toBeInTheDocument()
    expect(screen.getByTestId('loop-tab-controller')).toBeInTheDocument()

    cleanup()
    vi.mocked(useAgents).mockReturnValue({ data: [{ name: 'other', lifecycle: 'archived' }] } as never)
    show(baseLoop())
    expect(screen.getByRole('button', { name: 'Let worker decide' })).toBeInTheDocument()

    cleanup()
    vi.mocked(useAgents).mockReturnValue({ data: undefined } as never)
    show(baseLoop())
    expect(screen.getByRole('button', { name: 'Let worker decide' })).toBeInTheDocument()
  })
})
