import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ReachGrantsSetting } from '@/components/agents/AgentSettingsControls'
import { ApiError } from '@/api/client'
import type { AgentSummary } from '@/api/agents'

// F795: the agent page's reach save answered a fixed "Could not save the granted reach." whatever the
// Hub said, while the project's Reach group showed the Hub's sentence for the same refusal.

let saveError: unknown = null

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useUpdateAgentReachGrants: () => ({
      mutate: vi.fn(),
      isPending: false,
      isError: saveError !== null,
      error: saveError,
    }),
  }
})

const agent: AgentSummary = {
  name: 'cla',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  lifecycle: 'open',
  reach_grants: { roots: [], hosts: [] },
}

describe('a refused agent reach save', () => {
  it("shows the Hub's own sentence", () => {
    saveError = new ApiError(
      400,
      JSON.stringify({
        detail:
          "reach_grants.hosts: a granted host is host, host:port, host:* or *.domain, not 'http://bad host'",
      }),
    )
    render(<ReachGrantsSetting agent={agent} />)
    expect(screen.getByText(/reach_grants\.hosts: a granted host is host/)).toBeInTheDocument()
    expect(screen.queryByText('Could not save the granted reach.')).not.toBeInTheDocument()
  })

  it('keeps the fixed sentence when the failure carries none', () => {
    saveError = new TypeError('network down')
    render(<ReachGrantsSetting agent={agent} />)
    expect(screen.getByText('Could not save the granted reach.')).toBeInTheDocument()
  })
})
