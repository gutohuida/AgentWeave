import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectLedger } from '@/components/activity/ProjectLedger'
import type { ProjectLedger as Ledger } from '@/api/ledger'

/**
 * The ledger (slice project-ledger). `LEDGER` is in the order `GET /ledger` returns: merges newest
 * first, spend by day oldest first. The view renders each lane in that order, so a renderer that
 * re-sorted a lane fails here (CLAUDE.md: a consumer's test uses the route's real order).
 */

const LEDGER: Ledger = {
  merges: [
    { id: 'tin-new', task_id: 'task-b', task_title: 'Tags', outcome: 'skipped', commit_sha: null, source_branch: null,
      target_branch: null, reason: 'already integrated', actor_kind: 'operator', actor: 'operator', at: '2026-10-16T09:00:00Z' },
    { id: 'tin-old', task_id: 'task-a', task_title: 'Watch', outcome: 'merged', commit_sha: 'c6aed11aaaa', source_branch: 'agentweave/task/task-a',
      target_branch: 'master', reason: null, actor_kind: 'agent', actor: 'QA2', at: '2026-10-15T09:00:00Z' },
  ],
  spend: {
    total_usd: 2.6, total_tokens: 1550, worker_usd: 0.1,
    by_day: [
      { day: '2026-10-15', usd: 2.1, worker_usd: 0.1, tokens: 1050 },
      { day: '2026-10-16', usd: 0.5, worker_usd: 0, tokens: 500 },
    ],
    by_agent: [
      { agent: 'builder', usd: 2.0, tokens: 1000, turns: 1 },
      { agent: 'tester', usd: 0.5, tokens: 500, turns: 1 },
    ],
    by_task: [{ task_id: 'task-a', task_title: 'Watch', usd: 2.0, tokens: 1000, turns: 1 }],
  },
  divergences: [
    { id: 'rdv-1', run_id: 'run-a', agent: 'builder', task_id: 'task-a', task_title: 'Watch', task_status_at_end: 'in_progress',
      run_exit_status: 'completed', policy_applied: 'surface', outcome: 'surfaced', at: '2026-10-15T09:00:00Z', resolved_at: null },
  ],
  messages: [],
  origins: { spec: 1, loop: 0, agent: 1, operator: 0 },
  notices: [{ kind: 'context_warning', count: 589, first_at: null, last_at: '2026-10-16T09:00:00Z',
    by_agent: [{ agent: 'Builder', count: 400 }, { agent: 'Architect', count: 189 }] }],
  totals: { merged: 1, integrations: 2, divergences: 1, open_divergences: 1, tasks: 2 },
}

vi.mock('@/api/ledger', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/ledger')>()
  return { ...actual, useProjectLedger: () => ({ data: LEDGER, isLoading: false, isError: false }) }
})

describe('ProjectLedger', () => {
  it('shows the route’s totals', () => {
    render(<ProjectLedger onOpenTask={vi.fn()} />)
    expect(screen.getByTestId('ledger-total-spend').textContent).toBe('$2.60')
    expect(screen.getByTestId('ledger-total-merged').textContent).toBe('1')
    expect(screen.getByTestId('ledger-totals').textContent).toContain('1 skipped')
    expect(screen.getByTestId('ledger-totals').textContent).toContain('1 open')
    expect(screen.getByTestId('ledger-totals').textContent).toContain('1 from specs · 1 by agents')
  })

  it('renders merges in the route’s order and opens a task', async () => {
    const onOpenTask = vi.fn()
    render(<ProjectLedger onOpenTask={onOpenTask} />)
    const ids = within(screen.getByTestId('ledger-merges'))
      .getAllByTestId(/^ledger-merge-/)
      .map((row) => row.getAttribute('data-testid'))
    expect(ids).toEqual(['ledger-merge-tin-new', 'ledger-merge-tin-old'])
    await userEvent.click(within(screen.getByTestId('ledger-merge-tin-old')).getByText('Watch'))
    expect(onOpenTask).toHaveBeenCalledWith('task-a')
  })

  it('draws spend by day left to right, one bar a day', () => {
    render(<ProjectLedger onOpenTask={vi.fn()} />)
    const bars = within(screen.getByTestId('ledger-spend-by-day')).getAllByRole('button')
    expect(bars.map((b) => b.getAttribute('aria-label'))).toEqual([
      expect.stringContaining('$2.10'),
      expect.stringContaining('$0.50'),
    ])
  })

  it('folds a repeated notice into one counted row', () => {
    render(<ProjectLedger onOpenTask={vi.fn()} />)
    const row = screen.getByTestId('ledger-notice-context_warning')
    expect(row.textContent).toContain('589')
    expect(row.textContent).toContain('Builder 400')
  })
})
