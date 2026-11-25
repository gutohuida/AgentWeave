import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Task } from '@/api/tasks'
import { BuildView } from '@/components/builds/BuildView'
import { NO_ADDRESS, type BuildRead, type BuildTaskRead } from '@/components/builds/buildViewModel'
import { TaskCard } from '@/components/tasks/TaskCard'
import type { CheckRunState, CheckState } from '@/lib/checkState'
import { builderAndReviewer, STAGE_LABELS } from '@/lib/taskStage'

afterEach(cleanup)

const STATES: CheckRunState[] = ['waiting', 'running', 'passed', 'failed', 'could_not_run']
const STATE_WORD: Record<CheckRunState, string> = {
  waiting: 'waiting',
  running: 'running',
  passed: 'passed',
  failed: 'failed',
  could_not_run: 'could not run',
}

function card(over: Record<string, unknown>) {
  return {
    id: 'task-1',
    title: 'A card',
    status: 'completed',
    priority: 'medium',
    assignee: 'Developer',
    builder: 'Developer',
    checker: 'QA',
    ...over,
  } as unknown as Task
}

describe('the board card shows the stage and the Hub check state', () => {
  it('a completed task in pre-review checks reads Pre-review checks, never Ready for review', () => {
    const { container } = render(
      <TaskCard
        task={card({ stage: 'pre_review_checks', check_state: { kind: 'pre_review', state: 'running' } })}
        onOpen={() => {}}
      />,
    )
    const stage = screen.getByTestId('task-stage-task-1')
    expect(stage).toHaveTextContent('Pre-review checks')
    expect(stage).toHaveTextContent('Running')
    expect(container.textContent).not.toContain('Ready for review')
    expect(container.textContent).not.toMatch(/\bChecking\b/)
  })

  it('names the builder at pre_review_checks', () => {
    expect(builderAndReviewer({ stage: 'pre_review_checks', builder: 'Developer', assignee: 'Developer' })).toEqual({
      builder: 'Developer',
      reviewer: null,
    })
  })

  it('an approved task in landing checks reads Landing checks', () => {
    render(<TaskCard task={card({ status: 'approved', stage: 'checking' })} onOpen={() => {}} />)
    expect(screen.getByTestId('task-stage-task-1')).toHaveTextContent('Landing checks')
    expect(STAGE_LABELS.checking).not.toMatch(/^Checking/)
  })

  it.each(STATES.filter((s) => s !== 'passed'))('check state %s is told by words and a glyph, beside another stage', (state) => {
    const check: CheckState = { kind: 'pre_review', state }
    const { container } = render(<TaskCard task={card({ stage: 'sent_back', check_state: check })} onOpen={() => {}} />)
    expect(screen.getByTestId('task-stage-task-1')).toHaveTextContent(`Pre-review ${STATE_WORD[state]}`)
    expect(container.querySelector('.aw-tcard-markers svg')).not.toBeNull()
  })

  it('could not run never reads as failed', () => {
    const { container } = render(
      <TaskCard
        task={card({ stage: 'sent_back', check_state: { kind: 'pre_review', state: 'could_not_run' }, failed_checks: 3 })}
        onOpen={() => {}}
      />,
    )
    expect(container.textContent).toContain('could not run')
    expect(container.textContent).not.toMatch(/failed/i)
    // The count marker gives way to the Hub's check state where one is present.
    expect(screen.queryByTestId('task-failed-checks-task-1')).toBeNull()
  })

  it('falls back to the failed count where the Hub sends no check state', () => {
    render(<TaskCard task={card({ stage: 'sent_back', failed_checks: 2 })} onOpen={() => {}} />)
    expect(screen.getByTestId('task-failed-checks-task-1')).toHaveTextContent('2')
  })
})

function bt(id: string, over: Partial<BuildTaskRead>): BuildTaskRead {
  return {
    id,
    ref: id.toUpperCase(),
    title: `Task ${id}`,
    status: 'pending',
    declared: true,
    builder: 'Developer',
    checker: 'QA',
    last_change_at: '2026-11-17T11:00:00Z',
    needs_operator: null,
    requirements: [],
    runs: [],
    send_backs: [],
    ...over,
  }
}

function view(tasks: BuildTaskRead[]) {
  const read: BuildRead = {
    build: { id: 'b', document_id: 'd', document_title: 'A build', document_path: null, state: 'running', level: 'reviewed', created_at: '2026-11-17T08:00:00Z', stopped_at: null, stop_reason: null, needs_operator: null, attention_dismissed: false },
    tasks,
    build_runs: [],
    as_of: '2026-11-17T12:00:00Z',
  }
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <BuildView read={read} status="ready" now={new Date('2026-11-17T12:00:00Z')} address={NO_ADDRESS} onAddressChange={vi.fn()} onRetry={vi.fn()} onOpenDocument={vi.fn()} onOpenConversation={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe('the build view rows show stage and check state, not raw status', () => {
  it('draws each stage word, with its check glyph where it has one', () => {
    const { container } = view([
      bt('a', { status: 'pending', stage: 'not_started' }),
      bt('b', { status: 'completed', stage: 'pre_review_checks', check_state: { kind: 'pre_review', state: 'running' } }),
      bt('c', { status: 'approved', stage: 'landing_held', check_state: { kind: 'landing', state: 'failed' } }),
      bt('d', { status: 'approved', stage: 'did_not_land', check_state: { kind: 'landing', state: 'could_not_run' } }),
    ])
    const words = Array.from(container.querySelectorAll('.aw-bv-stage-word')).map((n) => n.textContent)
    expect(words).toEqual(['Not started', 'Pre-review checks', 'Landing held', 'Did not land'])
    const rows = Array.from(container.querySelectorAll('li.aw-bv-item'))
    expect(rows).toHaveLength(4)
    // A passed run shows nothing; a dense row's marker carries its sentence as its accessible name.
    expect(within(rows[0] as HTMLElement).queryByRole('img')).toBeNull()
    expect(within(rows[1] as HTMLElement).getByLabelText(/Pre-review checks running/)).toBeInTheDocument()
    expect(within(rows[2] as HTMLElement).getByLabelText(/Landing checks failed/)).toBeInTheDocument()
    expect(within(rows[3] as HTMLElement).getByLabelText(/Landing checks could not run/)).toBeInTheDocument()
    expect(container.textContent).not.toContain('could not run, so')
  })
})
