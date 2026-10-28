import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TaskChecks } from '@/api/tasks'
import { LandWait } from '@/components/tasks/LandingRefusal'

/**
 * `approved-work-merges-in-batches`: the wait beside Land never states an age it has not read.
 * Before `useElapsedSeconds` has its first reading it returns null; the label once rendered that as
 * "running 1 minute", which CI caught on a slow runner (run 40606840326). Here the clock is held
 * at null, so the first render is the one asserted, every time.
 */

const checks: TaskChecks = {
  configured: true,
  running: true,
  runs: [
    {
      id: 'run-2',
      state: 'running',
      main_sha: 'a',
      target_shas: [],
      merged_sha: null,
      results: [],
      error: '',
      started_at: '2026-10-26T12:00:00Z',
      ended_at: null,
    },
    {
      id: 'run-1',
      state: 'passed',
      main_sha: 'a',
      target_shas: [],
      merged_sha: null,
      results: [],
      error: '',
      started_at: '2026-10-26T11:30:00Z',
      ended_at: '2026-10-26T11:44:00Z',
    },
  ],
}

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return { ...actual, useTaskChecks: () => ({ data: checks, error: null }) }
})

vi.mock('@/hooks/useElapsedSeconds', () => ({ useElapsedSeconds: () => null }))

afterEach(cleanup)

describe('the wait beside Land before the clock has read', () => {
  it('says it waits, with no age', () => {
    render(<LandWait taskId="task-1" />)
    expect(screen.getByTestId('task-land-wait-task-1').textContent).toBe('Waiting for checks')
  })
})
