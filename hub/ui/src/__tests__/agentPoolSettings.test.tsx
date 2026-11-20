import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { ApiError } from '@/api/client'
import type { AgentPoolEntry } from '@/api/agentPool'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const poolMutate = vi.fn()

const RUNNERS = [
  { id: 'r-sonnet', project_id: 'p', name: 'Claude Sonnet', cli: 'claude', model: 'claude-sonnet-5-5', created_at: '', updated_at: '', model_unrecognised: false },
  { id: 'r-opus', project_id: 'p', name: 'Claude Opus', cli: 'claude', model: 'claude-opus-5', created_at: '', updated_at: '', model_unrecognised: false },
]

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: RUNNERS, isLoading: false }),
  useBindAgentModel: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useProviderLaunchability: () => ({ data: undefined }),
  useUpdateAgentWaiting: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  MIN_WAITING_SECONDS: 10,
  MAX_WAITING_SECONDS: 600,
}))

vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
  useBindAgentCharter: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }) }
})

const entry = (id: string, runner: (typeof RUNNERS)[number], isDefault: boolean): AgentPoolEntry => ({
  id,
  runner_id: runner.id,
  runner_name: runner.name,
  cli: 'claude',
  model: runner.model,
  effort: null,
  default: isDefault,
})

let roster: AgentSummary[] = []

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
    useAgentLaunchability: () => ({ data: undefined }),
    useAgents: () => ({ data: roster, isLoading: false }),
    useUpdateAgentPool: () => ({ mutate: poolMutate, isPending: false, isError: false }),
  }
})

function renderRunning() {
  roster = [
    {
      name: 'Developer',
      status: 'idle',
      message_count: 0,
      active_task_count: 0,
      runner: 'claude',
      runner_id: 'r-sonnet',
      pool: [entry('e1', RUNNERS[0]!, true), entry('e2', RUNNERS[1]!, false)],
    },
  ]
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AgentSettingsPage agent="Developer" section="running" onSelectSection={vi.fn()} onBack={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe('the agent pool in settings', () => {
  beforeEach(() => poolMutate.mockReset())

  it('lists the pool and writes the whole list when another entry is made the default', () => {
    renderRunning()
    fireEvent.click(screen.getByRole('button', { name: /^Make .*Opus.* the default$/ }))
    expect(poolMutate).toHaveBeenCalledTimes(1)
    expect(poolMutate.mock.calls[0]![0]).toEqual({
      agent: 'Developer',
      pool: [
        { runner_id: 'r-sonnet', effort: null, default: false },
        { runner_id: 'r-opus', effort: null, default: true },
      ],
    })
  })

  it('removes an entry by writing the list without it', () => {
    renderRunning()
    fireEvent.click(screen.getByRole('button', { name: /^Remove .*Opus/ }))
    expect(poolMutate.mock.calls[0]![0].pool).toEqual([{ runner_id: 'r-sonnet', effort: null, default: true }])
  })

  it('shows the Hub refusal in the editor', async () => {
    renderRunning()
    poolMutate.mockImplementation((...args: unknown[]) => {
      ;(args[1] as { onError: (e: unknown) => void } | undefined)?.onError(new ApiError(409, JSON.stringify({ detail: 'Removing the default needs another entry named default.' })))
    })
    fireEvent.click(screen.getByRole('button', { name: /^Remove .*Opus/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/needs another entry named default/)
  })
})
