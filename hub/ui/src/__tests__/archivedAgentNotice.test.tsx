import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ArchivedAgentNotice } from '@/components/agents/ArchivedAgentNotice'

// F193: opening a conversation whose agent was archived showed "Agent unavailable." and nothing
// else. The reason is knowable and the remedy is one request.

const unarchive = vi.fn()
let roster: unknown[] | undefined = []
let rosterError: unknown = null

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgents: () => ({ data: roster, error: rosterError, isLoading: false }),
    useArchiveAgent: () => ({ mutate: unarchive, isPending: false, error: null }),
  }
})

beforeEach(() => {
  unarchive.mockReset()
  rosterError = null
  roster = [{ name: 'ghost', status: 'idle', message_count: 0, active_task_count: 0, lifecycle: 'archived' }]
})

describe('the notice for a conversation whose agent is archived (F193)', () => {
  it('names the agent, says it is archived, and unarchives it', () => {
    render(<ArchivedAgentNotice agentName="ghost" />)

    expect(screen.getByTestId('archived-agent-notice')).toHaveTextContent('ghost is archived.')
    fireEvent.click(screen.getByTestId('archived-agent-unarchive'))
    expect(unarchive).toHaveBeenCalledWith({ agent: 'ghost', archived: false })
  })

  it('says so plainly when the agent is on no roster at all', () => {
    roster = []
    render(<ArchivedAgentNotice agentName="nobody" />)
    expect(screen.getByTestId('archived-agent-notice')).toHaveTextContent("nobody is not on this project's roster.")
    expect(screen.queryByTestId('archived-agent-unarchive')).toBeNull()
  })

  it('does not guess when the roster could not be read', () => {
    roster = undefined
    rosterError = new Error('502')
    render(<ArchivedAgentNotice agentName="ghost" />)
    expect(screen.getByTestId('archived-agent-notice')).toHaveTextContent('Could not read the roster')
  })
})
