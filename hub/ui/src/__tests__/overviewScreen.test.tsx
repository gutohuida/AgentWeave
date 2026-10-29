import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { Question } from '@/api/questions'
import type { Stall } from '@/api/stalls'
import { OverviewScreen } from '@/components/overview/OverviewScreen'
import { useTaskFilterStore } from '@/store/taskFilterStore'

// The Overview reads main notices and next-slice offers (`amendments-main-watch-and-the-next-slice`).
const mainNotices: unknown[] = []
const nextSliceOffers: unknown[] = []
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

/** What the wired Overview lists as needing the operator, running, and finished — each from the
 *  hook that owns it, in the order those routes return. */

let questions: Question[] = []
let questionsError: Error | null = null
let ledgerError: Error | null = null
let accountingData: Record<string, unknown> = { budget: { exhausted: false } }
let queueStatuses: Array<Record<string, unknown>> = []
let openStalls: Stall[] = []
const answerMutate = vi.fn()
const updateTaskMutate = vi.fn()

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'builder', status: 'idle', message_count: 0, active_task_count: 0, runner_id: 'r1' }], isLoading: false }),
}))
vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: questionsError ? undefined : questions, error: questionsError }),
  useAnswerQuestion: () => ({ mutate: answerMutate }),
  useDeclineQuestion: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('@/api/tasks', () => ({
  useTasks: () => ({
    data: {
      tasks: [
        {
          id: 'task-9',
          title: 'Rename the parser',
          status: 'approved',
          latest_integration: { outcome: 'failed', reason: 'the project folder has uncommitted changes', target_branch: 'master', created_at: '2026-10-20T09:00:00Z' },
        },
        // The shape the tasks route returns for a task the operator alone can move on.
        {
          id: 'task-11',
          title: 'Wire the exporter',
          status: 'blocked',
          assignee: 'builder',
          blocked_reason: 'needs the staging credentials',
          updated: '2026-10-20T09:30:00Z',
          latest_integration: null,
        },
      ],
      total: 2,
      has_more: false,
    },
  }),
  useUpdateTask: () => ({ mutate: updateTaskMutate }),
  useRetryIntegration: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return {
    ...actual,
    useProjectConversations: () => ({
      data: {
        conversations: [
          { id: 'conv-1', agent: 'builder', title: 'Port the lexer', attention: 'running', lifecycle: 'open', updated_at: '2026-10-20T09:58:00Z', created_at: '2026-10-20T09:00:00Z' },
        ],
      },
    }),
  }
})
vi.mock('@/api/ledger', () => ({
  useProjectLedger: () => (ledgerError ? { data: undefined, error: ledgerError } : {
    data: {
      merges: [{ id: 'm1', task_id: 'task-2', task_title: 'Add the tokenizer', outcome: 'merged', target_branch: 'master', actor_kind: 'operator', actor: null, at: '2026-10-20T08:00:00Z' }],
      spend: { total_usd: 3.5, total_tokens: 120000, worker_usd: 0, by_day: [], by_agent: [{ agent: 'builder', usd: 3.5, tokens: 120000, turns: 4 }], by_task: [] },
    },
  }),
}))
vi.mock('@/api/queue', () => ({ useQueueStatuses: () => queueStatuses }))
const endStallMutate = vi.fn()
vi.mock('@/api/stalls', () => ({ useOpenStalls: () => ({ data: openStalls }), useEndStall: () => ({ mutate: endStallMutate }) }))
let flakyReport: Record<string, unknown> | null = null
let flakyError: Error | null = null
const flakyRefetch = vi.fn()
const handleFlakyMutate = vi.fn()
vi.mock('@/api/flakyTests', () => ({
  useFlakyTests: () => ({ data: flakyReport, error: flakyError, refetch: flakyRefetch }),
  useHandleFlakyTests: () => ({ mutate: handleFlakyMutate }),
}))
vi.mock('@/api/accounting', () => ({ useAccounting: () => ({ data: accountingData }) }))
vi.mock('@/components/overview/AgentPostureChips', () => ({ AgentPostureChips: () => null }))

function question(overrides: Partial<Question> = {}): Question {
  return {
    id: 'q-1',
    project_id: 'proj-1',
    from_agent: 'builder',
    question: 'Keep the old parser behind a flag?',
    blocking: true,
    options: [
      { label: 'Keep it', description: 'Behind a flag for one release.' },
      { label: 'Remove it', description: 'Delete it now.' },
    ],
    answered: false,
    created_at: '2026-10-20T09:55:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  questions = []
  questionsError = null
  ledgerError = null
  accountingData = { budget: { exhausted: false } }
  queueStatuses = []
  openStalls = []
  flakyReport = null
  flakyError = null
  flakyRefetch.mockClear()
  handleFlakyMutate.mockClear()
  answerMutate.mockClear()
})

describe('the wired Overview', () => {
  it('raises the flaky tests the checks found and hands them to a fix task', () => {
    flakyReport = {
      window_days: 30,
      handled: null,
      flaky: [
        { check: 'hub-tests', test: 'tests/test_a.py::test_x', occurrences: 3, first_seen: '2026-10-20T08:00:00Z', last_seen: '2026-10-20T09:00:00Z', task_ids: ['task-1'], run_ids: [] },
        { check: 'lint', test: null, occurrences: 1, first_seen: '2026-10-20T07:00:00Z', last_seen: '2026-10-20T07:00:00Z', task_ids: ['task-2'], run_ids: [] },
      ],
    }
    render(<OverviewScreen onNavigate={vi.fn()} />)
    const row = screen.getByText('2 flaky tests in the approval checks').closest('li') as HTMLElement
    expect(row).toHaveTextContent('tests/test_a.py::test_x (3×), the lint check (1×).')
    fireEvent.click(within(row).getByRole('button', { name: 'Create a fix task' }))
    expect(handleFlakyMutate.mock.calls[0][0]).toBe(true)
    fireEvent.click(within(row).getByRole('button', { name: 'Dismiss' }))
    expect(handleFlakyMutate.mock.calls[1][0]).toBe(false)
  })

  it('shows no flaky row when none are open', () => {
    flakyReport = { window_days: 30, handled: null, flaky: [] }
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByText(/flaky test/)).not.toBeInTheDocument()
  })

  it('lists an open question and answers it inline with the chosen option', () => {
    questions = [question()]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.getByText('Keep the old parser behind a flag?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove it' }))
    expect(answerMutate.mock.calls[0][0]).toEqual({ id: 'q-1', answer: 'Remove it', labels: ['Remove it'] })
  })

  it('puts the question an agent is blocked on first, and claims a wait only for it (F904)', () => {
    // The route returns oldest first, so the non-blocking record is the older row.
    questions = [
      question({ id: 'q-old', question: 'FYI which licence?', blocking: false, created_at: '2026-10-20T08:00:00Z' }),
      question({ id: 'q-new', question: 'Keep the old parser behind a flag?', blocking: true }),
      question({ id: 'q-gone', question: 'Dead ask?', blocking: true, asker_waiting: false, created_at: '2026-10-20T08:30:00Z' }),
    ]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    const titles = Array.from(document.querySelectorAll('.aw-ov-need-title')).map((el) => el.textContent)
    expect(titles.indexOf('Keep the old parser behind a flag?')).toBeLessThan(titles.indexOf('FYI which licence?'))
    expect(titles.indexOf('Keep the old parser behind a flag?')).toBeLessThan(titles.indexOf('Dead ask?'))
    const who = (text: string) => (screen.getByText(text).closest('li') as HTMLElement).querySelector('.aw-ov-agent')
    expect(who('Keep the old parser behind a flag?')).toHaveTextContent('builder is waiting')
    expect(who('FYI which licence?')).toHaveTextContent('builder is asking')
    expect(who('Dead ask?')).toHaveTextContent('builder is asking')
  })

  it('reads the mender’s note as a note, opening the thread it was asked in', () => {
    // A note: non-blocking, its asking turn over. The Hub delivers its answer as a later message,
    // so nobody-is-waiting would be false. A blocking ask whose turn ended still reads as before.
    questions = [
      question({
        id: 'q-note', from_agent: 'mender', question: 'Touch the operator’s notes.txt?', header: 'Dirty checkout',
        blocking: false, asker_waiting: false, conversation_id: 'conv-stall-1',
      }),
      question({ id: 'q-gone', question: 'Dead ask?', blocking: true, asker_waiting: false }),
    ]
    const onOpenConversation = vi.fn()
    render(<OverviewScreen onNavigate={vi.fn()} onOpenConversation={onOpenConversation} />)

    const note = screen.getByText('Touch the operator’s notes.txt?').closest('li') as HTMLElement
    expect(note).toHaveTextContent('Dirty checkout')
    expect(note).not.toHaveTextContent(/nobody is waiting/)
    fireEvent.click(within(note).getByRole('button', { name: 'Open conversation' }))
    expect(onOpenConversation).toHaveBeenCalledWith('mender', 'conv-stall-1')

    const gone = screen.getByText('Dead ask?').closest('li') as HTMLElement
    expect(gone).toHaveTextContent('nobody is waiting on this answer any more')
  })

  it('does not offer inline options for a multi-select question', () => {
    questions = [question({ multi_select: true })]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Remove it' })).toBeNull()
  })

  it('lists an approved task that did not merge, and opens it on the board', () => {
    // The Hub's own stall says it did not merge (`merge-row-follows-its-stall`): no stall, no row.
    openStalls = [stall({ id: 'stall-9', key: 'integration_failed:task-9', cause: 'integration_failed', task_id: 'task-9', reason: 'the project folder has uncommitted changes' })]
    const onNavigate = vi.fn()
    render(<OverviewScreen onNavigate={onNavigate} />)
    expect(screen.getByText('“Rename the parser” was approved but not merged')).toBeInTheDocument()
    const mergeRow = screen.getByText('“Rename the parser” was approved but not merged').closest('li') as HTMLElement
    fireEvent.click(within(mergeRow).getByRole('button', { name: 'Open task' }))
    expect(useTaskFilterStore.getState().pendingOpenTaskId).toBe('task-9')
    expect(onNavigate).toHaveBeenCalledWith('tasks')
  })

  it('lists a blocked task as waiting on the operator, with its reason and the move that releases it (FR-2)', () => {
    render(<OverviewScreen onNavigate={vi.fn()} />)
    const row = screen.getByText('“Wire the exporter” is waiting on you').closest('li') as HTMLElement
    expect(within(row).getByText(/needs the staging credentials/)).toBeInTheDocument()
    fireEvent.click(within(row).getByRole('button', { name: 'Resume work' }))
    expect(updateTaskMutate).toHaveBeenCalledWith({ id: 'task-11', status: 'in_progress' }, expect.objectContaining({ onError: expect.any(Function) }))
  })

  it('shows a running conversation and opens that conversation', () => {
    const onOpenConversation = vi.fn()
    render(<OverviewScreen onNavigate={vi.fn()} onOpenConversation={onOpenConversation} />)
    const runningNow = screen.getByRole('region', { name: /Running now/ })
    fireEvent.click(within(runningNow).getByRole('button', { name: /Port the lexer/ }))
    expect(onOpenConversation).toHaveBeenCalledWith('builder', 'conv-1')
  })

  it('lists merges from the ledger under Recently finished', () => {
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.getByText('Add the tokenizer')).toBeInTheDocument()
    expect(screen.getByText(/approved by you/)).toBeInTheDocument()
  })
})

function stall(overrides: Partial<Stall> = {}): Stall {
  return {
    id: 'stall-1',
    key: 'delivery_refused:task-4',
    cause: 'delivery_refused',
    reason: 'Developer holds task-4, and delivering its turn to them was refused. No firing will retry it',
    task_id: 'task-4',
    loop_id: 'loop-1',
    first_seen_at: '2026-10-23T00:35:00Z',
    last_seen_at: '2026-10-23T00:40:00Z',
    seen_count: 2,
    conversation_id: null,
    mender_turns: 0,
    outcome: 'open',
    outcome_detail: '',
    ended_at: null,
    ...overrides,
  }
}

describe('a stalled project under Needs you', () => {
  it('lists a stall nobody is mending, and opens its task', () => {
    openStalls = [stall()]
    const onNavigate = vi.fn()
    render(<OverviewScreen onNavigate={onNavigate} />)
    const row = screen.getByText('An agent’s turn was refused').closest('li') as HTMLElement
    expect(row).toHaveTextContent('No firing will retry it.')
    fireEvent.click(within(row).getByRole('button', { name: 'Open task' }))
    expect(useTaskFilterStore.getState().pendingOpenTaskId).toBe('task-4')
    fireEvent.click(within(row).getByRole('button', { name: 'Dismiss' }))
    expect(endStallMutate).toHaveBeenCalledWith('stall-1', expect.objectContaining({ onError: expect.any(Function) }))
  })

  it('says the mender is on a stall it holds, and opens its thread', () => {
    openStalls = [stall({ conversation_id: 'conv-m' })]
    const onOpenConversation = vi.fn()
    render(<OverviewScreen onNavigate={vi.fn()} onOpenConversation={onOpenConversation} />)
    const row = screen.getByText('An agent’s turn was refused').closest('li') as HTMLElement
    expect(row).toHaveTextContent('The mender is on it.')
    fireEvent.click(within(row).getByRole('button', { name: 'Open the mender’s thread' }))
    expect(onOpenConversation).toHaveBeenCalledWith('mender', 'conv-m')
  })

  it('folds a merge stall into the merge row rather than listing it twice', () => {
    openStalls = [stall({ id: 'stall-2', key: 'integration_failed:task-9', cause: 'integration_failed', task_id: 'task-9', conversation_id: 'conv-m' })]
    const onOpenConversation = vi.fn()
    render(<OverviewScreen onNavigate={vi.fn()} onOpenConversation={onOpenConversation} />)
    expect(screen.queryByText('Approved work failed to merge')).toBeNull()
    const row = screen.getByText('“Rename the parser” was approved but not merged').closest('li') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: 'The mender is on it' }))
    expect(onOpenConversation).toHaveBeenCalledWith('mender', 'conv-m')
  })
})

describe('a query the Hub did not answer', () => {
  it('names the parts it could not read rather than showing their defaults as fact', () => {
    questionsError = new Error('500')
    ledgerError = new Error('500')
    render(<OverviewScreen onNavigate={vi.fn()} />)
    const notice = screen.getByTestId('query-error-notice')
    expect(notice).toHaveAttribute('role', 'alert')
    expect(notice).toHaveTextContent('Couldn’t read the questions and the ledger from the Hub')
  })

  it('offers Retry, which asks the failed read again, and the line goes once it answers', () => {
    flakyError = new Error('500')
    const { rerender } = render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.getByTestId('query-error-notice')).toHaveTextContent('Couldn’t read the flaky tests from the Hub')
    fireEvent.click(within(screen.getByTestId('query-error-notice')).getByRole('button', { name: 'Retry' }))
    expect(flakyRefetch).toHaveBeenCalledTimes(1)

    flakyError = null
    rerender(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByTestId('query-error-notice')).toBeNull()
  })

  it('says nothing while every query has answered', () => {
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByTestId('query-error-notice')).toBeNull()
  })

  describe('the spend line says what the Budgets page says (F952)', () => {
    const usage = (over: Record<string, unknown> = {}) => ({
      input_tokens: 1, output_tokens: 1, total_tokens: 120000, measured_turns: 4, unavailable_turns: 0,
      api_equivalent_usd_micros: 3_500_000, unpriced_turns: 0, ...over,
    })

    it('says how many turns could not be priced', () => {
      accountingData = {
        budget: { exhausted: false },
        project: usage({ unpriced_turns: 1 }),
        agents: [{ agent: 'builder', ...usage({ unpriced_turns: 1 }) }],
        preferred_display: { kind: 'api_equivalent', label: 'API-equivalent estimate', usd_micros: 3_500_000, unpriced_turns: 1 },
      }
      render(<OverviewScreen onNavigate={vi.fn()} />)
      const line = screen.getByRole('button', { name: /so far/ })
      expect(line).toHaveTextContent('$3.50 API-equivalent')
      expect(line).toHaveTextContent('1 turn unpriced')
    })

    it('shows the credits the project reported, not "$0.00", when only credits were reported', () => {
      accountingData = {
        budget: { exhausted: false },
        project: usage({ api_equivalent_usd_micros: null, unpriced_turns: 2, ai_nano_aiu: 280_000_000 }),
        agents: [{ agent: 'builder', ...usage({ api_equivalent_usd_micros: null, unpriced_turns: 2, ai_nano_aiu: 280_000_000 }) }],
        preferred_display: { kind: 'credits', label: 'AI credits', runner: 'copilot', ai_nano_aiu: 280_000_000, premium_requests: null },
      }
      render(<OverviewScreen onNavigate={vi.fn()} />)
      const line = screen.getByRole('button', { name: /so far/ })
      expect(line).toHaveTextContent('0.28 AI credits')
      expect(line).not.toHaveTextContent('$0.00')
    })

    it('names the allowance a subscription project is measured by', () => {
      accountingData = {
        budget: { exhausted: false },
        project: usage(),
        agents: [{ agent: 'builder', ...usage() }],
        preferred_display: { kind: 'allowance', label: 'Rate-limit allowance', allowance: { status: 'allowed', rateLimitType: 'seven_day' }, runner: 'claude' },
      }
      render(<OverviewScreen onNavigate={vi.fn()} />)
      expect(screen.getByRole('button', { name: /so far/ })).toHaveTextContent('Weekly allowance available')
    })

    it('reads an agent with no priced turn as a dash, not $0.00', () => {
      accountingData = {
        budget: { exhausted: false },
        project: usage(),
        agents: [{ agent: 'builder', ...usage({ api_equivalent_usd_micros: null, unpriced_turns: 1 }) }],
        preferred_display: { kind: 'api_equivalent', label: 'API-equivalent estimate', usd_micros: 3_500_000, unpriced_turns: 1 },
      }
      render(<OverviewScreen onNavigate={vi.fn()} />)
      const row = screen.getByRole('button', { name: /Open builder/ })
      expect(row).toHaveTextContent('—')
      expect(row).not.toHaveTextContent('$')
    })
  })

  it('names the limit, the use and what is held when the token budget is spent, and links to Budgets (F953)', () => {
    accountingData = { budget: { exhausted: true, limit_tokens: 100_000, used_tokens: 265_821, remaining_tokens: 0 } }
    queueStatuses = [
      { agent: 'builder', waiting_count: 1, running: false, waiting_reason: 'token budget exhausted' },
      { agent: 'other', waiting_count: 2, running: false, waiting_reason: 'agent is busy' },
    ]
    const onNavigate = vi.fn()
    render(<OverviewScreen onNavigate={onNavigate} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Token limit reached: 265.8K of 100K')
    expect(alert).toHaveTextContent('1 turn waiting')
    fireEvent.click(within(alert).getByRole('button', { name: /Budgets/ }))
    expect(onNavigate).toHaveBeenCalledWith('budgets')
    // A turn held for the budget is something the operator must act on: the summary says so.
    expect(screen.getByText('1 turn held by the budget')).toBeInTheDocument()
  })

  it('does not count a turn held for another reason as held by the budget (F953)', () => {
    accountingData = { budget: { exhausted: true, limit_tokens: 100_000, used_tokens: 120_000, remaining_tokens: 0 } }
    queueStatuses = [{ agent: 'builder', waiting_count: 3, running: false, waiting_reason: 'agent is busy' }]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.getByRole('alert')).not.toHaveTextContent('waiting')
    expect(screen.queryByText(/held by the budget/)).toBeNull()
  })
})
