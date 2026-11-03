/**
 * A firing that started a run opens that run's trace, from both places firings are listed:
 * a job's run history and a loop's firing group in the rail. A firing with no run offers none.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { JobRun } from '@/api/jobs'
import type { AgentConversation } from '@/api/agentChat'
import { RunHistory } from '@/components/jobs/JobDetails'
import { LoopFiringGroup } from '@/components/layout/LoopFiringGroup'

// Asked about exactly the conversations the group renders. The loop's own detail (last ten firings,
// all agents) is deliberately not mocked: the group must not depend on it.
const askedFor: string[][] = []
vi.mock('@/api/loops', () => ({
  useLoopFiringRuns: (id: string | null, conversationIds: string[]) => {
    if (id) askedFor.push(conversationIds)
    return { data: id ? { c1: 'run-abc' } : undefined }
  },
}))
vi.mock('@/components/traces/TraceDrawer', () => ({
  TraceButton: ({ runId, testId }: { runId?: string; testId?: string }) =>
    runId ? <button data-testid={testId} data-run-id={runId} /> : null,
}))

afterEach(() => cleanup())

const firedAt = '2026-08-19T01:00:00Z'
function run(id: string, overrides: Partial<JobRun> = {}): JobRun {
  return { id, job_id: 'j', fired_at: firedAt, status: 'completed', trigger: 'scheduled', ...overrides }
}

describe('job run history', () => {
  it('opens the trace of the run a firing started, and none for a firing with no run', () => {
    render(<RunHistory now={new Date('2026-08-19T03:00:00Z')} runs={[run('jr-2', { status: 'skipped' }), run('jr-1', { run_id: 'run-abc' })]} />)
    expect(screen.getByTestId('job-run-trace-jr-1')).toHaveAttribute('data-run-id', 'run-abc')
    expect(screen.queryByTestId('job-run-trace-jr-2')).toBeNull()
  })
})

function conv(id: string): AgentConversation {
  return {
    id, agent: 'claude', provider_session_id: null, lifecycle: 'open', title: id, title_set_by_operator: false,
    origin: 'job', loop: { id: 'loop-7', label: 'sweep' }, attention: 'idle', created_at: firedAt, updated_at: firedAt,
  }
}

describe('loop firing group', () => {
  it('opens the trace of the run each firing started, only for firings that have one', () => {
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <LoopFiringGroup
          projectId="proj-a"
          loopId="loop-7"
          label="sweep"
          conversations={[conv('c1'), conv('c2')]}
          activeConversation={null}
          onOpen={vi.fn()}
          rowTestId={(c) => `row-${c.id}`}
          testId="grp"
        />
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByTestId('grp-expander'))
    expect(askedFor[askedFor.length - 1]).toEqual(['c1', 'c2'])
    expect(screen.getByTestId('row-c1-trace')).toHaveAttribute('data-run-id', 'run-abc')
    expect(screen.queryByTestId('row-c2-trace')).toBeNull()
  })
})
