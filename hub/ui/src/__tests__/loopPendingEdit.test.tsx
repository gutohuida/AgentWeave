/**
 * A staged edit, and which loop definition is in force while it waits.
 *
 * The Hub has reported `pending_edit` since task A2.4 and nothing in `hub/ui/src` rendered it, so
 * an operator who staged an edit saw the loop's old values with nothing to say an edit existed —
 * indistinguishable from the edit having been dropped. That gap is what blocked human-only check
 * A6.1, "does 'pending versus live' read clearly enough to trust?".
 */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LoopTab } from '@/components/spec/LoopTab'
import { useLoop } from '@/api/loops'
import type { LoopDetail } from '@/api/loops'

vi.mock('@/api/loops', () => ({ useLoop: vi.fn() }))

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

function renderLoop(overrides: Partial<LoopDetail> = {}) {
  mockedUseLoop.mockReturnValue({
    data: baseLoop(overrides),
    isLoading: false,
    isError: false,
  } as never)
  return render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)
}

describe('LoopTab — a staged edit versus the definition in force', () => {
  it('shows nothing at all when no edit is staged, which is most of the time', () => {
    renderLoop({ pending_edit: null })

    expect(screen.queryByTestId('loop-tab-pending-edit')).not.toBeInTheDocument()
    expect(screen.queryByTestId('loop-tab-pending-badge')).not.toBeInTheDocument()
    expect(screen.queryByTestId('loop-tab-purpose-staged')).not.toBeInTheDocument()
  })

  it('states both values, each labelled by when it applies', () => {
    renderLoop({
      purpose: 'sweep the queue',
      pending_edit: {
        staged_by: 'q2verify',
        staged_at: new Date(Date.now() - 60_000).toISOString(),
        purpose: 'sweep the queue, then report',
      },
    })

    const row = screen.getByTestId('loop-tab-pending-purpose')
    expect(row).toHaveTextContent('In force now: sweep the queue')
    expect(row).toHaveTextContent('From the next firing: sweep the queue, then report')
    // Position and colour are not the distinction — the words are.
    expect(screen.getByTestId('loop-tab-pending-edit')).toHaveTextContent(
      'it applies at the next firing',
    )
    expect(screen.getByTestId('loop-tab-pending-edit-who')).toHaveTextContent('q2verify')
  })

  it('marks the live purpose where it is read, not only in the panel', () => {
    renderLoop({
      pending_edit: { staged_at: new Date().toISOString(), purpose: 'something else' },
    })

    expect(screen.getByTestId('loop-tab-purpose-staged')).toHaveTextContent('in force now')
  })

  it('marks the live stop condition when either stop field is staged', () => {
    renderLoop({
      stop_when_queue_empties: true,
      pending_edit: { staged_at: new Date().toISOString(), stop_when_queue_empties: false },
    })

    const row = screen.getByTestId('loop-tab-pending-stop_when_queue_empties')
    expect(row).toHaveTextContent('In force now: when the queue empties')
    expect(row).toHaveTextContent('From the next firing: not when the queue empties')
    expect(screen.getByTestId('loop-tab-stop-condition-staged')).toBeInTheDocument()
  })

  it('does not invent a change to a field the edit never touched', () => {
    renderLoop({
      purpose: 'sweep the queue',
      pending_edit: { staged_at: new Date().toISOString(), stop_when_queue_empties: false },
    })

    expect(screen.queryByTestId('loop-tab-pending-purpose')).not.toBeInTheDocument()
    expect(screen.queryByTestId('loop-tab-purpose-staged')).not.toBeInTheDocument()
  })

  it('says the running firing keeps the live definition, which is when "next firing" is ambiguous', () => {
    renderLoop({
      firing_active: true,
      pending_edit: { staged_at: new Date().toISOString(), purpose: 'something else' },
    })

    expect(screen.getByTestId('loop-tab-pending-edit-who')).toHaveTextContent(
      'The firing running now keeps the definition below marked “In force now”',
    )
  })

  it('still says an edit exists when it changes no field this panel shows', () => {
    // `pending_edit_at` set with every per-field column NULL is legitimate — the columns mean
    // "not touched by this edit", not "no edit". An empty box would read as a bug.
    renderLoop({ pending_edit: { staged_at: new Date().toISOString() } })

    expect(screen.getByTestId('loop-tab-pending-edit-empty')).toHaveTextContent(
      'It changes no field this panel shows',
    )
    expect(screen.getByTestId('loop-tab-pending-badge')).toHaveTextContent('Edit staged')
  })
})
