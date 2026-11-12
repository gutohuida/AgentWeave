import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useConfigStore } from '@/store/configStore'
import { TaskStory } from '@/components/tasks/TaskStory'
import { TaskDetailsView, TaskWorkView } from '@/components/tasks/TaskViews'
import type { StoryEvent, Task, TaskCheckRun, TaskStory as Story } from '@/api/tasks'

/**
 * The opened task's Story, Work and Details (`task-card-and-story-redesign`, FR-6, FR-10, FR-11).
 * The story is in the order `GET /tasks/{id}/story` returns (oldest first); coverage is the
 * `requirement_id -> state` map the drawer reads from the document's coverage route.
 */

const run = (n: number): StoryEvent => ({
  kind: 'run', id: `run-${n}`, at: `2026-10-16T14:0${n}:00Z`, agent: 'Builder', status: 'completed',
  ended_at: `2026-10-16T14:0${n}:30Z`, duration_seconds: 30, model: 'claude-sonnet-5-5', runner: 'claude',
  cost_usd: 0.1, tokens: 1000, premium_requests: null, ai_nano_aiu: null, conversation_id: `conv-${n}`, error: null,
})

const STORY: Story = {
  task: { id: 'task-1', title: 'Watch folders', status: 'approved' },
  summary: { runs: 6, cost_usd: 0.6, tokens: 6000, premium_requests: null, ai_nano_aiu: null, evidence: { accepted: 0, rejected: 0, awaiting: 0 }, merged: ['c6aed11aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'], overrides: 0 },
  events: [
    { kind: 'created', id: 'task-1', at: '2026-10-16T14:00:00Z', by: 'Architect' },
    run(1), run(2), run(3), run(4), run(5), run(6),
    {
      kind: 'question', id: 'q-1', at: '2026-10-16T14:20:00Z', agent: 'Builder', question: 'Which folder?',
      answered: true, answer: 'The watched one', declined: false,
    } as unknown as StoryEvent,
    {
      kind: 'integration', id: 'tin-1', at: '2026-10-16T14:33:00Z', outcome: 'merged',
      commit_sha: 'c6aed11aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', source_branch: 'agentweave/task/task-1',
      target_branch: 'master', reason: null, mechanism: 'local', actor_kind: 'agent', actor: 'QA2',
    },
  ],
}

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return { ...actual, useTaskStory: () => ({ data: STORY, isLoading: false, isError: false }) }
})

beforeEach(() => useConfigStore.setState({ selectedProjectId: 'proj' }))
afterEach(cleanup)

const wordCount = (text: string) => text.trim().split(/\s+/).length

describe('the Story folds routine runs and keeps what must be seen', () => {
  it('folds six runs into one entry, leaves the answered question and the landing out, keeps every link', () => {
    render(<TaskStory taskId="task-1" />)
    const list = screen.getByTestId('task-story-events-task-1')
    const ids = within(list).getAllByRole('listitem').map((li) => li.getAttribute('data-testid')).filter((id): id is string => !!id && /^story-(event|fold)-/.test(id) && !id.startsWith('story-fold-open'))
    expect(ids).toEqual(['story-event-task-1', 'story-fold-fold-run-run-1', 'story-event-q-1', 'story-event-tin-1'])

    const fold = screen.getByTestId('story-fold-fold-run-run-1')
    expect(fold.textContent).toContain('6 routine steps')
    expect(screen.getByTestId('story-event-q-1').textContent).toContain('The watched one')
    for (let n = 1; n <= 6; n++) {
      expect(within(fold).getByTestId(`story-run-trace-run-${n}`)).toBeTruthy()
      expect(within(fold).getByTestId(`story-run-conversation-run-${n}`)).toBeTruthy()
    }
    // Every label stays within six words.
    const labels = [screen.getByTestId('story-fold-open-fold-run-run-1').textContent ?? '']
    for (const id of ['story-event-task-1', 'story-event-q-1', 'story-event-tin-1']) {
      const head = screen.getByTestId(id).querySelector('.aw-tl-head, [class*="head"]')
      if (head) labels.push(head.textContent ?? '')
    }
    for (const label of labels) expect(wordCount(label)).toBeLessThanOrEqual(6)
  })

  it('opens the fold into the six runs', async () => {
    render(<TaskStory taskId="task-1" />)
    await userEvent.click(screen.getByTestId('story-fold-open-fold-run-run-1'))
    for (let n = 1; n <= 6; n++) expect(screen.getByTestId(`story-event-run-${n}`)).toBeTruthy()
    expect(screen.queryByTestId('story-fold-fold-run-run-1')).toBeNull()
  })
})

const TASK: Task = {
  id: 'task-1', project_id: 'proj', title: 'Ship', status: 'completed', priority: 'medium',
  created_at: '2026-08-10T10:00:00Z', updated: '2026-08-10T10:00:00Z', divergence_policy: 'surface', has_open_divergence: false,
  notes: 'Mind the rename.', description: 'Do it.',
  requirement_links: [
    { identifier: 'FR-1', requirement_id: 'req-1', document_id: 'doc', state: 'active', statement: 'First.' },
    { identifier: 'FR-2', requirement_id: 'req-2', document_id: 'doc', state: 'active', statement: 'Second.' },
  ],
  acceptance_criteria: ['ac-one: given a, then b'],
  prerequisites: [{ id: 'task-0', readable_id: 'T-0', title: 'Before', status: 'approved' }],
}

const checkRun = (id: string, state: TaskCheckRun['state'], exit: number): TaskCheckRun => ({
  id, state, main_sha: 'm', target_shas: [], merged_sha: null, error: '', started_at: null, ended_at: '2026-08-10T10:00:00Z',
  results: [{ name: `check-${id}`, exit_code: exit, timed_out: false, duration_seconds: 3, output_tail: 'boom' }],
})

describe('the Work view', () => {
  it('shows each requirement with its evidence state, the criteria and checks, and reveals earlier runs', async () => {
    render(
      <TaskWorkView
        task={TASK}
        checks={checkRun('latest', 'passed', 0)}
        earlierChecks={[checkRun('older', 'failed', 1)]}
        coverage={new Map([['req-1', 'verified']])}
      />,
    )
    const serves = screen.getByTestId('task-serves-task-1')
    const items = within(serves).getAllByRole('listitem')
    expect(items[0].textContent).toContain('Accepted')
    expect(items[1].textContent).toContain('No evidence yet')
    expect(screen.getByText('ac-one: given a, then b')).toBeTruthy()
    expect(screen.getByText('check-latest')).toBeTruthy()
    expect(screen.queryByText('check-older')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: /Earlier runs/ }))
    expect(screen.getByText('check-older')).toBeTruthy()
  })

  it('offers no Earlier runs control when there are none', () => {
    render(<TaskWorkView task={TASK} checks={checkRun('latest', 'passed', 0)} earlierChecks={[]} />)
    expect(screen.queryByRole('button', { name: /Earlier runs/ })).toBeNull()
  })
})

describe('the Details view', () => {
  it('shows the notes and the dependency', () => {
    render(<TaskDetailsView task={TASK} />)
    expect(screen.getByText('Mind the rename.')).toBeTruthy()
    expect(screen.getByText('Before')).toBeTruthy()
  })
})
