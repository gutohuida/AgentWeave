import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import { ApiError } from '@/api/client'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

// F795: the agent page's reach save answered a fixed "Could not save the granted reach." whatever the
// Hub said, while the project's Reach group showed the Hub's sentence for the same refusal.

let saveError: unknown = null
let roster: AgentSummary[] = []

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [], isLoading: false }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
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

vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return { ...actual, useAgentWorkspace: () => ({ data: undefined, isLoading: true, error: null }) }
})

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
    useAgentLaunchability: () => ({ data: undefined }),
    useAgents: () => ({ data: roster, isLoading: false }),
    useArchiveAgent: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    useUpdateAgentDescription: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentReachGrants: () => ({
      mutate: (_vars: unknown, callbacks?: { onError?: (error: unknown) => void }) => callbacks?.onError?.(saveError),
      isPending: false,
      isError: false,
    }),
  }
})

const agent: AgentSummary = {
  name: 'cla',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  lifecycle: 'open',
  reach_grants: null,
}

function saveOwnReach() {
  roster = [agent]
  render(<AgentSettingsPage agent="cla" section="execution" onSelectSection={vi.fn()} onBack={vi.fn()} />)
  fireEvent.click(screen.getByRole('switch', { name: 'Own granted reach for cla' }))
}

describe('a refused agent reach save', () => {
  it("shows the Hub's own sentence", async () => {
    saveError = new ApiError(
      400,
      JSON.stringify({
        detail:
          "reach_grants.hosts: a granted host is host, host:port, host:* or *.domain, not 'http://bad host'",
      }),
    )
    saveOwnReach()
    expect((await screen.findAllByText(/reach_grants\.hosts: a granted host is host/)).length).toBeGreaterThan(0)
    expect(screen.queryByText('Could not save the granted reach.')).not.toBeInTheDocument()
  })

  it('says the Hub gave no reason when the failure carries none', async () => {
    saveError = new TypeError('network down')
    saveOwnReach()
    expect((await screen.findAllByText(/did not return a reason|network down/)).length).toBeGreaterThan(0)
  })
})
