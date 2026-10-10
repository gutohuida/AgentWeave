import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LoopTab } from '@/components/spec/LoopTab'
import { useLoop } from '@/api/loops'
import type { LoopDetail } from '@/api/loops'

vi.mock('@/api/loops', () => ({
  useLoop: vi.fn(),
  useStopLoop: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useArchiveLoop: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useSetLoopControl: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useUpdateLoopSettings: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null, reset: vi.fn() }),
}))
vi.mock('@/api/jobs', () => ({ useJob: () => ({ data: undefined }) }))
vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [] }) }))

afterEach(() => cleanup())

const NOW = new Date().toISOString()

function loopWith(events: LoopDetail['events']): LoopDetail {
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
    events,
  }
}

function show(events: LoopDetail['events']) {
  vi.mocked(useLoop).mockReturnValue({ data: loopWith(events), isLoading: false, isError: false } as never)
  render(<LoopTab loopId="loop-1" onClose={vi.fn()} />)
}

// The route returns newest first, creation last (hub/hub/api/v1/loops.py).
const added = {
  id: 'e2',
  event_type: 'loop_tasks_added',
  agent: 'alice',
  timestamp: NOW,
  data: {
    by: { kind: 'agent', agent: 'alice', run_id: 'run-9' },
    source: 'create_task',
    tasks: [{ id: 'task-1', title: 'Fourth' }],
  },
}
const created = {
  id: 'e1',
  event_type: 'loop_created',
  agent: null,
  timestamp: NOW,
  data: {
    by: { kind: 'operator', agent: null, run_id: null },
    door: 'jobs',
    agent: 'kimi',
    purpose: 'keep the history',
    document: null,
    document_path: null,
  },
}

describe('LoopTab — the History section (a-loops-history-records-its-creation-and-queue-additions)', () => {
  it('lists each event as a sentence, in the order the route returns, naming who and what', () => {
    show([added, created])

    const rows = screen.getAllByTestId('loop-tab-event')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('alice (run run-9) added 1 task to its queue: "Fourth".')
    expect(rows[1]).toHaveTextContent('The operator created this loop from the jobs page, for kimi, to keep the history.')
    expect(screen.queryByTestId('loop-tab-creation-unrecorded')).not.toBeInTheDocument()
  })

  it('says the creation was not recorded when the loop has no creation entry', () => {
    show([added])

    const section = screen.getByTestId('loop-tab-events')
    expect(within(section).getAllByTestId('loop-tab-event')).toHaveLength(1)
    expect(screen.getByTestId('loop-tab-creation-unrecorded')).toHaveTextContent(
      'creation was not recorded',
    )
  })

  it('names the document an approval-door loop was made from', () => {
    show([
      {
        ...created,
        data: { ...created.data, door: 'approval', document: 'spdoc-1', document_path: 'spec/changes/x/spec.json' },
      },
    ])

    expect(screen.getByTestId('loop-tab-event')).toHaveTextContent(
      'by approving a document, for kimi from spec/changes/x/spec.json',
    )
  })
})
