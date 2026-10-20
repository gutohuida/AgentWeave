import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { Question } from '@/api/questions'
import { OverviewScreen } from '@/components/overview/OverviewScreen'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/** What the wired Overview lists as needing the operator, running, and finished — each from the
 *  hook that owns it, in the order those routes return. */

let questions: Question[] = []
let questionsError: Error | null = null
let ledgerError: Error | null = null
const answerMutate = vi.fn()

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'builder', status: 'idle', message_count: 0, active_task_count: 0, runner_id: 'r1' }], isLoading: false }),
}))
vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: questionsError ? undefined : questions, error: questionsError }),
  useAnswerQuestion: () => ({ mutate: answerMutate }),
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
      ],
      total: 1,
      has_more: false,
    },
  }),
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
vi.mock('@/api/accounting', () => ({ useAccounting: () => ({ data: { budget: { exhausted: false } } }) }))
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
  answerMutate.mockClear()
})

describe('the wired Overview', () => {
  it('lists an open question and answers it inline with the chosen option', () => {
    questions = [question()]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.getByText('Keep the old parser behind a flag?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove it' }))
    expect(answerMutate.mock.calls[0][0]).toEqual({ id: 'q-1', answer: 'Remove it', labels: ['Remove it'] })
  })

  it('does not offer inline options for a multi-select question', () => {
    questions = [question({ multi_select: true })]
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Remove it' })).toBeNull()
  })

  it('lists an approved task that did not merge, and opens it on the board', () => {
    const onNavigate = vi.fn()
    render(<OverviewScreen onNavigate={onNavigate} />)
    expect(screen.getByText('“Rename the parser” was approved but not merged')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open task' }))
    expect(useTaskFilterStore.getState().pendingOpenTaskId).toBe('task-9')
    expect(onNavigate).toHaveBeenCalledWith('tasks')
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

describe('a query the Hub did not answer', () => {
  it('names the parts it could not read rather than showing their defaults as fact', () => {
    questionsError = new Error('500')
    ledgerError = new Error('500')
    render(<OverviewScreen onNavigate={vi.fn()} />)
    const notice = screen.getByTestId('query-error-notice')
    expect(notice).toHaveAttribute('role', 'alert')
    expect(notice).toHaveTextContent('Couldn’t read the questions and the ledger from the Hub')
  })

  it('says nothing while every query has answered', () => {
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(screen.queryByTestId('query-error-notice')).toBeNull()
  })
})
