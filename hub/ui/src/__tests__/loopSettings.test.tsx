/**
 * The Settings section of a loop's own tab (`a-flow-is-configured-from-its-own-tab`, tasks 3.3 and
 * 3.5 a/b/c/g/h/i): what is sent, and what the tab says is in force versus staged.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LoopTab } from '@/components/spec/LoopTab'
import { useLoop } from '@/api/loops'
import type { LoopDetail } from '@/api/loops'

const save = vi.fn()

vi.mock('@/api/loops', () => ({
  useLoop: vi.fn(),
  useStopLoop: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useArchiveLoop: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useSetLoopControl: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useUpdateLoopSettings: () => ({
    mutate: (...args: unknown[]) => save(...args),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  }),
}))
vi.mock('@/api/jobs', () => ({
  useJob: () => ({
    data: { id: 'job-1', name: 'nightly sweep', agent: 'A', message: 'Work the queue.', cron: '*/5 * * * *' },
  }),
}))
vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [{ name: 'A' }, { name: 'B' }] }) }))

const STOP_AT = '2030-01-02T03:04:00Z'

function baseLoop(overrides: Partial<LoopDetail> = {}): LoopDetail {
  return {
    id: 'loop-1',
    job_id: 'job-1',
    label: 'nightly sweep',
    agent: 'A',
    purpose: 'sweep the queue',
    stop_at: STOP_AT,
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

function show(overrides: Partial<LoopDetail> = {}) {
  vi.mocked(useLoop).mockReturnValue({ data: baseLoop(overrides), isLoading: false, isError: false } as never)
  render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)
}

const edit = () => fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
const saveButton = () => screen.getByRole('button', { name: 'Save' })
const agentSelect = () => screen.getByLabelText('Default agent') as HTMLSelectElement

beforeEach(() => save.mockReset())
afterEach(() => cleanup())

describe('LoopTab settings', () => {
  it('reads the default agent, message and cadence at rest', () => {
    show()
    const read = screen.getByTestId('loop-tab-settings-read')
    expect(read).toHaveTextContent('Default agent: A')
    expect(read).toHaveTextContent('Message: Work the queue.')
  })

  it('(a) sends only the fields that changed', () => {
    show()
    edit()
    fireEvent.change(screen.getByLabelText('Purpose'), { target: { value: 'sweep, then report' } })
    fireEvent.click(saveButton())
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0][0]).toEqual({ purpose: 'sweep, then report' })
  })

  it('(b) puts the live agent back over a staged one by sending it', () => {
    show({
      agent: 'A',
      pending_edit: { staged_by: null, staged_at: new Date().toISOString(), agent: 'B' },
    })
    edit()
    expect(agentSelect().value).toBe('B')
    fireEvent.change(agentSelect(), { target: { value: 'A' } })
    fireEvent.click(saveButton())
    expect(save.mock.calls[0][0]).toEqual({ agent: 'A' })
  })

  it('(c) shows an agent edit as pending, not as in force', () => {
    show({
      agent: 'A',
      pending_edit: { staged_by: null, staged_at: new Date().toISOString(), agent: 'B' },
    })
    const row = screen.getByTestId('loop-tab-pending-agent')
    expect(row).toHaveTextContent('In force now: A')
    expect(row).toHaveTextContent('From the next firing: B')
    expect(screen.getByTestId('loop-tab-settings-read')).toHaveTextContent('Default agent: A')
  })

  it('(g) offers no control that clears the stop time, and never sends a null one', () => {
    show()
    edit()
    expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Stop at'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Purpose'), { target: { value: 'changed' } })
    fireEvent.click(saveButton())
    const body = save.mock.calls[0][0]
    expect(body).toEqual({ purpose: 'changed' })
    expect('stop_at' in body).toBe(false)
  })

  it('(g) sends a moved stop time', () => {
    show()
    edit()
    fireEvent.change(screen.getByLabelText('Stop at'), { target: { value: '2031-05-06T07:08' } })
    fireEvent.click(saveButton())
    expect(save.mock.calls[0][0]).toEqual({ stop_at: new Date('2031-05-06T07:08').toISOString() })
  })

  it('(h) refuses a flow whose next firing would have neither stop', () => {
    show({ spec_document_id: 'doc-1', stop_at: undefined, stop_when_queue_empties: true })
    edit()
    fireEvent.click(screen.getByLabelText('Stop when the queue empties'))
    fireEvent.click(saveButton())
    expect(save).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('A flow needs a stop condition')
  })

  it('(h) counts a staged stop as what the next firing has', () => {
    show({
      spec_document_id: 'doc-1',
      stop_at: undefined,
      stop_when_queue_empties: false,
      pending_edit: { staged_by: null, staged_at: new Date().toISOString(), stop_when_queue_empties: true },
    })
    edit()
    fireEvent.click(screen.getByLabelText('Stop when the queue empties'))
    fireEvent.click(saveButton())
    expect(save).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('A flow needs a stop condition')
  })

  it('(h) sends the same edit on a loop that declares no document', () => {
    show({ spec_document_id: null, stop_at: undefined, stop_when_queue_empties: true })
    edit()
    fireEvent.click(screen.getByLabelText('Stop when the queue empties'))
    fireEvent.click(saveButton())
    expect(save.mock.calls[0][0]).toEqual({ stop_when_queue_empties: false })
  })

  it('(i) warns before Save when a creator-controlled loop changes agent', () => {
    show({ control: 'creator' })
    edit()
    expect(screen.queryByTestId('loop-tab-settings-control-warning')).not.toBeInTheDocument()
    fireEvent.change(agentSelect(), { target: { value: 'B' } })
    expect(screen.getByTestId('loop-tab-settings-control-warning')).toHaveTextContent(
      'gives control back to you when the change applies',
    )
  })

  it('(i) says nothing when the loop is not delegated', () => {
    show({ control: null })
    edit()
    fireEvent.change(agentSelect(), { target: { value: 'B' } })
    expect(screen.queryByTestId('loop-tab-settings-control-warning')).not.toBeInTheDocument()
  })

  it('is read-only once the loop has ended', () => {
    show({ ending_state: 'completed' })
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.getByTestId('loop-tab-settings-read')).toBeInTheDocument()
  })
})
