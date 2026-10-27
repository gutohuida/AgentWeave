import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ApiError } from '@/api/client'
import type { Question } from '@/api/questions'
import type { Stall } from '@/api/stalls'
import { OverviewScreen } from '@/components/overview/OverviewScreen'

// The Overview reads main notices and next-slice offers (`amendments-main-watch-and-the-next-slice`).
let mainNotices: unknown[] = []
let nextSliceOffers: unknown[] = []
const markSeenMutate = vi.fn()
const takeOfferMutate = vi.fn()
const declineOfferMutate = vi.fn()
vi.mock('@/api/mainNotices', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/mainNotices')>()),
  useOpenMainNotices: () => ({ data: mainNotices, error: null }),
  useMarkMainNoticeSeen: () => ({ mutate: markSeenMutate }),
}))
vi.mock('@/api/nextSlice', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/nextSlice')>()),
  useNextSliceOffers: () => ({ data: nextSliceOffers, error: null }),
  useTakeNextSliceOffer: () => ({ mutate: takeOfferMutate }),
  useDeclineNextSliceOffer: () => ({ mutate: declineOfferMutate }),
}))

/** Every row under "Needs you" carries a control that ends it (slice I, `every-need-can-be-cleared`).
 *
 *  Fed the way the routes feed the Overview, with the shapes read from the operator's own Hub on
 *  2026-10-27: 28 unanswered mender questions whose asking turn had ended, and approved tasks whose
 *  newest integration row is a skip ("already in master") with no open stall. */

let questions: Question[] = []
let openStalls: Stall[] = []
let tasks: Array<Record<string, unknown>> = []
let flakyReport: Record<string, unknown> | null = null
let queueStatuses: Array<Record<string, unknown>> = []

const answerMutate = vi.fn()
const declineMutate = vi.fn()
const declineMutateAsync = vi.fn()
const updateTaskMutate = vi.fn()
const endStallMutate = vi.fn()
const retryMutate = vi.fn()
const handleFlakyMutate = vi.fn()
const toastSpy = vi.fn()

vi.mock('@/lib/toast', () => ({ toast: (input: unknown) => toastSpy(input) }))
vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [{ name: 'builder', status: 'idle', message_count: 0, active_task_count: 0, runner_id: 'r1', charter_id: 'c1' }],
    isLoading: false,
  }),
  useAgentLaunchability: () => ({ data: { agents: { builder: { runnable: true } } }, error: null }),
  useUpdateAgentGrant: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}))
vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: questions, error: null }),
  useAnswerQuestion: () => ({ mutate: answerMutate }),
  useDeclineQuestion: () => ({ mutate: declineMutate, mutateAsync: declineMutateAsync, isPending: false }),
}))
vi.mock('@/api/tasks', () => ({
  useTasks: () => ({ data: { tasks, total: tasks.length, has_more: false }, error: null }),
  useUpdateTask: () => ({ mutate: updateTaskMutate }),
  useRetryIntegration: () => ({ mutate: retryMutate, isPending: false }),
}))
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return { ...actual, useProjectConversations: () => ({ data: { conversations: [] } }) }
})
vi.mock('@/api/ledger', () => ({
  useProjectLedger: () => ({ data: { merges: [], spend: { total_usd: 0, total_tokens: 0, worker_usd: 0, by_day: [], by_agent: [], by_task: [] } } }),
}))
vi.mock('@/api/queue', () => ({
  useQueueStatuses: () => queueStatuses,
  useQueueStatus: () => ({ data: queueStatuses[0], error: null }),
}))
vi.mock('@/api/stalls', () => ({ useOpenStalls: () => ({ data: openStalls }), useEndStall: () => ({ mutate: endStallMutate }) }))
vi.mock('@/api/flakyTests', () => ({
  useFlakyTests: () => ({ data: flakyReport }),
  useHandleFlakyTests: () => ({ mutate: handleFlakyMutate }),
}))
vi.mock('@/api/accounting', () => ({ useAccounting: () => ({ data: { budget: { exhausted: false } } }) }))

function question(overrides: Partial<Question> = {}): Question {
  return {
    id: 'q-1',
    project_id: 'proj-1',
    from_agent: 'builder',
    question: 'Keep the old parser behind a flag?',
    blocking: true,
    options: [{ label: 'Keep it', description: 'Behind a flag for one release.' }],
    answered: false,
    created_at: '2026-10-20T09:55:00Z',
    ...overrides,
  }
}

/** The mender's question about one task, copied 27 times on the operator's Hub: blocking, its
 *  asking turn over, so nobody receives the answer as a result. */
function menderQuestion(n: number): Question {
  return question({
    id: `q-mender-${n}`,
    from_agent: 'mender',
    question: 'Task-8618731d065d: merge by hand?',
    options: [],
    blocking: true,
    asker_waiting: false,
    created_at: `2026-10-26T10:${String(n).padStart(2, '0')}:00Z`,
  })
}

function stall(overrides: Partial<Stall> = {}): Stall {
  return {
    id: 'stall-1',
    key: 'stuck_task:none',
    cause: 'stuck_task',
    reason: 'Nothing has moved on it for two hours',
    task_id: null,
    loop_id: null,
    first_seen_at: '2026-10-26T00:35:00Z',
    last_seen_at: '2026-10-26T00:40:00Z',
    seen_count: 1,
    conversation_id: null,
    mender_turns: 0,
    outcome: 'open',
    outcome_detail: '',
    ended_at: null,
    ...overrides,
  }
}

const refused = (detail: string) => new ApiError(409, JSON.stringify({ detail }))

const MERGED_ELSEWHERE = {
  outcome: 'skipped',
  reason: '09617d3b6920 is already in master; there was nothing to merge',
  target_branch: 'master',
  created_at: '2026-10-27T03:39:29Z',
  retryable: false,
}

beforeEach(() => {
  questions = []
  openStalls = []
  flakyReport = null
  queueStatuses = []
  tasks = []
  for (const fn of [answerMutate, declineMutate, declineMutateAsync, updateTaskMutate, endStallMutate, retryMutate, handleFlakyMutate, toastSpy]) fn.mockReset()
  declineMutateAsync.mockResolvedValue({})
  mainNotices = []
  nextSliceOffers = []
  for (const fn of [markSeenMutate, takeOfferMutate, declineOfferMutate]) fn.mockReset()
})

const rowOf = (text: string | RegExp) => screen.getByText(text).closest('li') as HTMLElement

/** `GET /projects/{id}/main-notices` as `main_watch.view` answers it: commits newest first. */
function mainNotice(overrides: Record<string, unknown> = {}) {
  return {
    id: 'mnot-1',
    project_id: 'proj-1',
    branch: 'master',
    old_tip: 'aaaaaaaaaaaa1111',
    new_tip: 'bbbbbbbbbbbb2222',
    rewrite: false,
    commits: [
      { sha: 'bbbbbbbbbbbb', subject: 'Merge slice D', author: 'Operator' },
      { sha: 'cccccccccccc', subject: 'A change made by hand', author: 'Hand Person' },
    ],
    created_at: '2026-10-27T10:00:00+00:00',
    updated_at: '2026-10-27T10:01:00+00:00',
    seen_at: null,
    seen_by: null,
    ...overrides,
  }
}

/** `GET /project/next-slice-offers` as `slice_drafting.offer_for` answers it. */
function offer() {
  return {
    document: 'spec/changes/slice-one/spec.json',
    document_id: 'spdoc-1',
    title: 'Slice one',
    roadmap: 'spec/changes/the-plan/spec.json',
    roadmap_title: 'The plan',
    approved_slice: { key: 's1', title: 'Slice one' },
    next_slice: { key: 's2', title: 'Slice two', intent: 'Second', done: 'S2 built' },
    agent: 'architect',
    conversation_id: 'conv-1',
    requested: false,
    tasks: ['task-1'],
  }
}

describe('main moving outside the Hub, and a next slice offered', () => {
  it('names the commits and the tips, and Seen closes the notice', () => {
    mainNotices = [mainNotice()]
    render(<OverviewScreen onNavigate={vi.fn()} />)

    const row = rowOf('master moved outside the Hub')
    expect(row).toHaveTextContent('from aaaaaaa to bbbbbbb')
    expect(row).toHaveTextContent('ccccccc A change made by hand (Hand Person)')
    fireEvent.click(within(row).getByRole('button', { name: 'Seen' }))
    expect(markSeenMutate).toHaveBeenCalledWith('mnot-1', expect.anything())
  })

  it('says a rewrite is a rewrite', () => {
    mainNotices = [mainNotice({ rewrite: true })]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(rowOf('The history of master was rewritten outside the Hub')).toHaveTextContent('rewriting its history')
  })

  it('offers the next slice with the author preselected, Draft to the chosen agent, and Not now', () => {
    nextSliceOffers = [offer()]
    render(<OverviewScreen onNavigate={vi.fn()} />)

    const row = rowOf('Slice s1 is built: draft Slice two?')
    const picker = within(row).getByLabelText('Agent that drafts the next slice') as HTMLSelectElement
    expect(picker.value).toBe('architect')
    fireEvent.change(picker, { target: { value: 'builder' } })
    fireEvent.click(within(row).getByRole('button', { name: 'Draft' }))
    expect(takeOfferMutate).toHaveBeenCalledWith(
      { path: 'spec/changes/slice-one/spec.json', agent: 'builder' },
      expect.anything(),
    )
    fireEvent.click(within(row).getByRole('button', { name: 'Not now' }))
    expect(declineOfferMutate).toHaveBeenCalledWith({ path: 'spec/changes/slice-one/spec.json' }, expect.anything())
  })
})

describe('a question on the Overview can be declined', () => {
  it('declines one question by its id, and the row goes once the questions come back without it', () => {
    questions = [question({ id: 'q-waited' }), menderQuestion(1)]
    const { rerender } = render(<OverviewScreen onNavigate={vi.fn()} />)
    const row = rowOf('Task-8618731d065d: merge by hand?')
    fireEvent.click(within(row).getByRole('button', { name: 'Decline' }))
    expect(declineMutate.mock.calls[0][0]).toEqual({ id: 'q-mender-1' })

    questions = [question({ id: 'q-waited' })]
    rerender(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByText('Task-8618731d065d: merge by hand?')).toBeNull()
  })

  it('declines every question nobody waits on after a confirmation that names how many, and never the one an asker waits on', async () => {
    questions = [question({ id: 'q-waited' }), ...Array.from({ length: 28 }, (_, i) => menderQuestion(i))]
    render(<OverviewScreen onNavigate={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /Decline 28 /i }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('28')
    expect(declineMutateAsync).not.toHaveBeenCalled()

    fireEvent.click(within(dialog).getByTestId('delete-confirm'))
    await waitFor(() => expect(declineMutateAsync).toHaveBeenCalledTimes(28))
    const declined = declineMutateAsync.mock.calls.map((call) => (call[0] as { id: string }).id)
    expect(new Set(declined).size).toBe(28)
    expect(declined).not.toContain('q-waited')
  })

  it('offers no decline-all while fewer than two questions lack a waiter', () => {
    questions = [question({ id: 'q-waited' }), menderQuestion(1)]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Decline \d+ /i })).toBeNull()
  })

  it('says why a decline was refused and keeps the row', () => {
    questions = [menderQuestion(1)]
    declineMutate.mockImplementation((_vars: unknown, options?: { onError?: (e: unknown) => void }) => options?.onError?.(refused('That question is already closed.')))
    render(<OverviewScreen onNavigate={vi.fn()} />)
    fireEvent.click(within(rowOf('Task-8618731d065d: merge by hand?')).getByRole('button', { name: 'Decline' }))
    expect(toastSpy).toHaveBeenCalledWith(expect.objectContaining({ tone: 'error', description: expect.stringContaining('already closed') }))
    expect(screen.getByText('Task-8618731d065d: merge by hand?')).toBeInTheDocument()
  })
})

describe('the approved-but-not-merged row follows the Hub’s stall', () => {
  const approved = (id: string, title: string, latest_integration: Record<string, unknown>) => ({ id, title, status: 'approved', latest_integration })

  it('lists no task whose work is already in master, nor one whose stall has ended', () => {
    tasks = [
      approved('task-a', 'Already merged work', MERGED_ELSEWHERE),
      approved('task-b', 'Ended stall work', { ...MERGED_ELSEWHERE, reason: 'no accepted evidence names a commit' }),
    ]
    openStalls = []
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByText(/approved but not merged/)).toBeNull()
  })

  it('offers Try again for a retryable failure and Dismiss for the stall; both go to the Hub, and the row leaves when the stall ends', () => {
    tasks = [approved('task-c', 'Rename the parser', { outcome: 'failed', reason: 'the project folder has uncommitted changes', target_branch: 'master', created_at: '2026-10-27T04:00:00Z', retryable: true })]
    openStalls = [stall({ id: 'stall-c', key: 'integration_failed:task-c', cause: 'integration_failed', task_id: 'task-c', reason: 'the project folder has uncommitted changes' })]
    const { rerender } = render(<OverviewScreen onNavigate={vi.fn()} />)
    const row = rowOf('“Rename the parser” was approved but not merged')
    expect(row).toHaveTextContent('uncommitted changes')

    fireEvent.click(within(row).getByRole('button', { name: 'Try again' }))
    expect(retryMutate.mock.calls[0][0]).toBe('task-c')
    fireEvent.click(within(row).getByRole('button', { name: 'Dismiss' }))
    expect(endStallMutate.mock.calls[0][0]).toBe('stall-c')

    openStalls = []
    rerender(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByText('“Rename the parser” was approved but not merged')).toBeNull()
  })

  it('offers no Try again when the Hub says a repeat could not change the outcome', () => {
    tasks = [approved('task-d', 'No branch work', { ...MERGED_ELSEWHERE, reason: 'no main branch is configured' })]
    openStalls = [stall({ id: 'stall-d', key: 'integration_skipped:task-d', cause: 'integration_skipped', task_id: 'task-d', reason: 'no main branch is configured' })]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    const row = rowOf('“No branch work” was approved but not merged')
    expect(within(row).queryByRole('button', { name: 'Try again' })).toBeNull()
    expect(within(row).getByRole('button', { name: 'Dismiss' })).toBeInTheDocument()
  })
})

describe('every row has a clearing control', () => {
  it('gives each kind of row a button whose click calls a mutation', () => {
    questions = [question({ id: 'q-waited' }), menderQuestion(1)]
    tasks = [
      { id: 'task-11', title: 'Wire the exporter', status: 'blocked', assignee: 'builder', blocked_reason: 'needs credentials', updated: '2026-10-20T09:30:00Z', latest_integration: null },
      { id: 'task-c', title: 'Rename the parser', status: 'approved', latest_integration: { ...MERGED_ELSEWHERE, outcome: 'failed', reason: 'dirty', retryable: true } },
    ]
    openStalls = [
      stall({ id: 'stall-c', key: 'integration_failed:task-c', cause: 'integration_failed', task_id: 'task-c' }),
      stall({ id: 'stall-x' }),
    ]
    flakyReport = { window_days: 30, handled: null, flaky: [{ check: 'lint', test: null, occurrences: 1, first_seen: '2026-10-20T07:00:00Z', last_seen: '2026-10-20T07:00:00Z', task_ids: [], run_ids: [] }] }
    render(<OverviewScreen onNavigate={vi.fn()} />)

    const items = Array.from(document.querySelectorAll('.aw-ov-need')) as HTMLElement[]
    expect(items).toHaveLength(6)
    const clearing = /^(Decline|Resume work|Try again|Dismiss|Create a fix task|Answer)$/
    for (const item of items) {
      const labels = within(item).getAllByRole('button').map((b) => b.textContent ?? '')
      expect(labels.some((label) => clearing.test(label)), `a row offered only ${labels.join(', ')}`).toBe(true)
    }
  })

  it('toasts the Hub’s reason and keeps the row when a stall dismissal, a resume or a flaky dismissal is refused', () => {
    tasks = [{ id: 'task-11', title: 'Wire the exporter', status: 'blocked', assignee: 'builder', blocked_reason: 'needs credentials', updated: '2026-10-20T09:30:00Z', latest_integration: null }]
    openStalls = [stall({ id: 'stall-x' })]
    flakyReport = { window_days: 30, handled: null, flaky: [{ check: 'lint', test: null, occurrences: 1, first_seen: '2026-10-20T07:00:00Z', last_seen: '2026-10-20T07:00:00Z', task_ids: [], run_ids: [] }] }
    const fail = (detail: string) => (_vars: unknown, options?: { onError?: (e: unknown) => void }) => options?.onError?.(refused(detail))
    endStallMutate.mockImplementation(fail('Stall already ended elsewhere.'))
    updateTaskMutate.mockImplementation(fail('A review is open on that task.'))
    handleFlakyMutate.mockImplementation(fail('The flaky list is locked.'))
    render(<OverviewScreen onNavigate={vi.fn()} />)

    fireEvent.click(within(rowOf('A task is stuck in progress')).getByRole('button', { name: 'Dismiss' }))
    fireEvent.click(within(rowOf('“Wire the exporter” is waiting on you')).getByRole('button', { name: 'Resume work' }))
    fireEvent.click(within(rowOf('1 flaky test in the approval checks')).getByRole('button', { name: 'Dismiss' }))

    for (const detail of ['Stall already ended elsewhere.', 'A review is open on that task.', 'The flaky list is locked.']) {
      expect(toastSpy).toHaveBeenCalledWith(expect.objectContaining({ tone: 'error', description: expect.stringContaining(detail) }))
    }
    expect(screen.getByText('A task is stuck in progress')).toBeInTheDocument()
    expect(screen.getByText('“Wire the exporter” is waiting on you')).toBeInTheDocument()
    expect(screen.getByText('1 flaky test in the approval checks')).toBeInTheDocument()
  })
})

describe('the other notices', () => {
  it('opens Project settings > General from the held-by-hop-budget chip', () => {
    queueStatuses = [{ agent: 'builder', waiting_reason: 'hop budget exhausted', waiting_count: 2 }]
    const onNavigate = vi.fn()
    render(<OverviewScreen onNavigate={onNavigate} />)
    fireEvent.click(screen.getByRole('button', { name: 'held by hop budget' }))
    expect(onNavigate).toHaveBeenCalledWith('settings')
  })
})
