/**
 * A firing that started a run opens that run's trace from a job's run history. A firing with no
 * run offers none. (The rail's loop firing rows carry no per-row trace button: the conversation's
 * own 'Trace of the latest run' control opens it.)
 */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { JobRun } from '@/api/jobs'
import { RunHistory } from '@/components/jobs/JobDetails'

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
