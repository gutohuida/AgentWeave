import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskStory } from '@/components/tasks/TaskStory'
import type { TaskStory as Story } from '@/api/tasks'

/**
 * The task story (slice task-story). The payload below is in the order `GET /tasks/{id}/story`
 * returns (`hub/hub/task_story.py`: oldest first, ties cause before effect), so a renderer that
 * re-sorted, reversed or dropped events fails here (CLAUDE.md: a consumer's test uses the route's
 * real order).
 */

const STORY: Story = {
  task: { id: 'task-1', title: 'Watch folders', status: 'approved' },
  summary: {
    runs: 2,
    cost_usd: 2.81,
    tokens: 23000,
    premium_requests: null,
    evidence: { accepted: 1, rejected: 1, awaiting: 0 },
    merged: ['c6aed11aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
    overrides: 1,
  },
  events: [
    { kind: 'created', id: 'task-1', at: '2026-10-16T14:02:00Z', by: 'Architect' },
    {
      kind: 'run', id: 'run-1', at: '2026-10-16T14:05:00Z', agent: 'Builder', status: 'completed',
      ended_at: '2026-10-16T14:16:00Z', duration_seconds: 660, model: 'claude-sonnet-5-5',
      runner: 'claude', cost_usd: 1.84, tokens: 12000, premium_requests: null,
      conversation_id: 'conv-1', error: null,
    },
    {
      kind: 'evidence', id: 'ev-old', at: '2026-10-16T14:15:00Z',
      evidence: {
        id: 'ev-old', summary: 'npm test 29/29', kind: 'test_result', locator: 'npm test',
        actor_kind: 'agent', actor: 'Builder', run_id: 'run-1', task_id: 'task-1',
        review_state: 'rejected', latest_review: null, produced_at: '2026-10-16T14:15:00Z',
        footprint: null, command: null, output: null, covers: null,
        requirement: { identifier: 'FR-5', statement: 'A watched folder can be renamed.' },
        superseded_by: 'ev-new',
      },
      reviews: [
        { decision: 'rejected', actor_kind: 'agent', actor: 'QA2', reason: 'rename fails with EPERM', at: '2026-10-16T14:20:00Z' },
      ],
    },
    {
      kind: 'transition', id: 'ttr-1', at: '2026-10-16T14:30:00Z', from: 'under_review',
      to: 'approved', actor_kind: 'run', actor: 'QA2', origin: 'actor', job: null, run_id: 'run-2',
      override_reason: 'the flaky suite fails on main too',
    },
    {
      kind: 'evidence', id: 'ev-new', at: '2026-10-16T14:31:00Z',
      evidence: {
        id: 'ev-new', summary: 'npm test 34/34', kind: 'test_result', locator: '',
        actor_kind: 'agent', actor: 'Builder', run_id: 'run-3', task_id: 'task-1',
        review_state: 'accepted', latest_review: null, produced_at: '2026-10-16T14:31:00Z',
        footprint: { kind: 'git', branch: 'agentweave/task/task-1', commit_sha: 'c6aed11aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', outside_workspace_writes: null },
        command: 'npm test', output: '34 passed\n', covers: 'partial',
        requirement: { identifier: 'FR-5', statement: 'A watched folder can be renamed.' },
        superseded_by: null,
      },
      reviews: [
        { decision: 'accepted', actor_kind: 'agent', actor: 'QA2', reason: 'checked the rename', at: '2026-10-16T14:32:00Z' },
      ],
    },
    {
      kind: 'integration', id: 'tin-1', at: '2026-10-16T14:33:00Z', outcome: 'merged',
      commit_sha: 'c6aed11aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', source_branch: 'agentweave/task/task-1',
      target_branch: 'master', reason: null, mechanism: 'local', actor_kind: 'agent', actor: 'QA2',
    },
  ],
}

const storyOverride = vi.hoisted(() => ({ current: null as unknown }))

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTaskStory: () => ({ data: storyOverride.current ?? STORY, isLoading: false, isError: false }),
  }
})

const diffFetches: string[] = []
vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useEvidenceDiff: (id: string, enabled: boolean) => {
      if (enabled) diffFetches.push(id)
      return {
        isLoading: false,
        data: enabled
          ? {
              files: [{ path: 'app/watcher.mjs', status: 'M', patch: '@@ -1 +1 @@\n-fs.watch(a)\n+fs.watch(b, { recursive: true })' }],
              base: 'b', commit: 'c', truncated: false, reason: null,
            }
          : undefined,
      }
    },
  }
})

describe('the task story', () => {
  it('renders every event in the order the route returns', () => {
    render(<TaskStory taskId="task-1" />)
    const list = screen.getByTestId('task-story-events-task-1')
    const ids = within(list)
      .getAllByRole('listitem')
      .map((item) => item.getAttribute('data-testid'))
      .filter((id): id is string => !!id && id.startsWith('story-event-'))
    expect(ids).toEqual(STORY.events.map((event) => `story-event-${event.id}`))
  })

  it('answers the summary first: state, cost, runs, evidence counts and what merged', () => {
    render(<TaskStory taskId="task-1" />)
    const summary = screen.getByTestId('task-story-summary-task-1')
    expect(summary.textContent).toContain('approved')
    expect(summary.textContent).toContain('$2.81')
    expect(summary.textContent).toContain('c6aed11a')
  })

  it('shows the run with its agent, model and cost', () => {
    render(<TaskStory taskId="task-1" />)
    const run = screen.getByTestId('story-event-run-1')
    expect(run.textContent).toContain('Builder')
    expect(run.textContent).toContain('claude-sonnet-5-5')
    expect(run.textContent).toContain('$1.84')
    expect(run.textContent).toContain('11m 0s')
  })

  it('calls out an approval over failing checks, with its reason', () => {
    render(<TaskStory taskId="task-1" />)
    expect(screen.getByTestId('story-override-ttr-1').textContent).toContain(
      'the flaky suite fails on main too',
    )
  })

  it('marks a replaced piece and shows each review with its reason', () => {
    render(<TaskStory taskId="task-1" />)
    const old = screen.getByTestId('story-event-ev-old')
    expect(old.textContent).toContain('replaced by a later piece')
    expect(old.textContent).toContain('Rejected by QA2')
    expect(old.textContent).toContain('rename fails with EPERM')
  })

  it('opens the proof: the requirement beside the command, its output and the diff', async () => {
    render(<TaskStory taskId="task-1" />)
    expect(diffFetches).not.toContain('ev-new')
    const toggle = screen.getByTestId('evidence-proof-toggle-ev-new')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    await userEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    const proof = screen.getByTestId('evidence-proof-ev-new')
    expect(proof.textContent).toContain('A watched folder can be renamed.')
    expect(proof.textContent).toContain('npm test')
    expect(screen.getByTestId('evidence-output-ev-new').textContent).toContain('34 passed')
    expect(proof.textContent).toContain('covers part of it')
    expect(diffFetches).toContain('ev-new')
    expect(screen.getByTestId('evidence-diff-ev-new').textContent).toContain('app/watcher.mjs')
  })
})


describe('slice remaining-hidden-data — transitions and runs open their conversation', () => {
  it('links a run, and a transition its run made, to that conversation; a run outside the story gets no link', async () => {
    const { useConfigStore } = await import('@/store/configStore')
    useConfigStore.setState({ selectedProjectId: 'proj-1' })
    const transition = STORY.events.find((e) => e.kind === 'transition')!
    storyOverride.current = {
      ...STORY,
      events: [
        ...STORY.events,
        { ...transition, id: 'ttr-own', run_id: 'run-1' },
      ],
    }
    try {
      render(<TaskStory taskId="task-1" />)
      expect(screen.getByTestId('story-run-conversation-run-1')).toBeInTheDocument()
      expect(screen.queryByTestId('story-transition-run-ttr-1')).toBeNull()
      await userEvent.click(screen.getByTestId('story-transition-run-ttr-own'))
      const params = new URLSearchParams(window.location.search)
      expect(params.get('agent')).toBe('Builder')
      expect(params.get('conversation')).toBe('conv-1')
    } finally {
      storyOverride.current = null
    }
  })
})

describe('F731 — a flow is named a flow, as the Details history names it', () => {
  it('reads "Flow <job>" for a move a flow made', () => {
    const transition = STORY.events.find((e) => e.kind === 'transition')!
    storyOverride.current = {
      ...STORY,
      events: [{ ...transition, id: 'ttr-flow', origin: 'job', job: 'build', job_kind: 'flow' }],
    }
    try {
      render(<TaskStory taskId="task-1" />)
      expect(screen.getByTestId('story-event-ttr-flow').textContent).toContain('Flow build')
    } finally {
      storyOverride.current = null
    }
  })
})

describe('F711 — a jammed task tells its jam', () => {
  it('shows a refused turn with its refusal and a failed checkout release with its reason', () => {
    storyOverride.current = {
      ...STORY,
      events: [
        ...STORY.events,
        {
          kind: 'turn', id: 'entry-1', at: '2026-10-16T14:40:00Z', agent: 'beta', review: false,
          state: 'queued', refusal: 'Could not prepare the checkout for task task-1: refusing path',
          ended_reason: null, attempts: 2, run_id: null,
        },
        {
          kind: 'workspace', id: 'ev-ws', at: '2026-10-16T14:41:00Z', outcome: 'release_failed',
          reason: 'Permission denied',
        },
      ],
    }
    try {
      render(<TaskStory taskId="task-1" />)
      const turn = screen.getByTestId('story-event-entry-1')
      expect(turn.textContent).toContain('beta')
      expect(turn.textContent).toContain('Could not prepare the checkout')
      expect(turn.textContent).toContain('2 attempts')
      expect(screen.getByTestId('story-event-ev-ws').textContent).toContain('Permission denied')
    } finally {
      storyOverride.current = null
    }
  })
})
