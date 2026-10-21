import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this test.
import { readFileSync } from 'node:fs'

import type { Task } from '@/api/tasks'
import { TaskCardHost } from './testUtils/TaskCardHost'

/**
 * task-dependencies task 8.15/8.16, design D12: a card whose task has a run executing *right now*
 * carries a live cue — a different fact than the column (`in_progress` can be true with nothing
 * actually running; `has_open_divergence` exists for exactly that disagreement). The compact card
 * states it on its status line, in words, with a pulsing dot; reduced motion stops the pulse and
 * keeps the dot, so the cue degrades rather than disappearing, and it is never the sole carrier.
 */

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
  }
})

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }] }),
}))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Ship the thing',
    status: 'in_progress',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

function renderCard(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCardHost task={task} />
    </QueryClientProvider>,
  )
}

const status = () => screen.queryByTestId('task-card-status-task-1')

afterEach(cleanup)

describe('the liveness cue (task 8.15, design D12)', () => {
  it('shows nothing when no run is executing, even with an assignee', () => {
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'idle' }))
    expect(status()).toBeNull()
  })

  it('shows nothing for a stalled heartbeat — that is the divergence line’s fact, not this one', () => {
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'stalled' }))
    expect(status()).toBeNull()
  })

  it('marks the card when a run is executing right now', () => {
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'running' }))
    expect(status()).toHaveAttribute('data-reason', 'working')
  })

  it('is not the only carrier of the fact — the status line says it in words too', () => {
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'running' }))
    expect(status()).toHaveTextContent('worker is working on it')
  })
})

describe('the cue is gated on prefers-reduced-motion (task 8.16, design D12)', () => {
  it('animates when motion is allowed', () => {
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'running' }))
    expect(status()!.querySelector('.aw-live-dot')).toHaveClass('aw-pulse')
  })

  it('degrades to a static dot, not to nothing, when motion is reduced', () => {
    // jsdom applies no stylesheet, so this reads the rule that does the degrading: under reduced
    // motion the pulse's animation stops, and nothing hides the dot itself.
    const css = readFileSync('src/styles/primitives.css', 'utf8') as string
    const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(reduced).toMatch(/\.aw-pulse\s*\{\s*animation:\s*none;\s*\}/)
    expect(reduced).not.toMatch(/\.aw-live-dot[^{]*\{[^}]*(display:\s*none|opacity:\s*0)/)
  })
})
