import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { ApiError } from '@/api/client'

const archiveMutate = vi.fn()
let archiveError: unknown = null
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

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
    useAgents: () => ({ data: roster, isLoading: false }),
    useArchiveAgent: () => ({ mutate: archiveMutate, isPending: false, error: archiveError }),
    useUpdateAgentDescription: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  }
})

function agent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'codex-1',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    lifecycle: 'open',
    ...overrides,
  }
}

function renderIdentity(summary: AgentSummary) {
  roster = [summary]
  return render(<AgentSettingsPage agent={summary.name} section="identity" />)
}

describe('an agent is archived, never deleted', () => {
  beforeEach(() => {
    archiveMutate.mockClear()
    archiveError = null
  })

  it('offers archiving, and no way at all to delete', async () => {
    const user = userEvent.setup()
    renderIdentity(agent())

    const toggle = screen.getByTestId('agent-archive-toggle')
    expect(toggle).toHaveTextContent('Archive agent')
    // The absence is the requirement: there is no delete, and the copy says why.
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
    expect(screen.getByText(/no way to delete an agent, by design/i)).toBeInTheDocument()

    await user.click(toggle)
    expect(archiveMutate).toHaveBeenCalledWith({ agent: 'codex-1', archived: true })
  })

  it('offers the way back once archived', async () => {
    const user = userEvent.setup()
    renderIdentity(agent({ lifecycle: 'archived' }))

    const toggle = screen.getByTestId('agent-archive-toggle')
    expect(toggle).toHaveTextContent('Unarchive agent')

    await user.click(toggle)
    expect(archiveMutate).toHaveBeenCalledWith({ agent: 'codex-1', archived: false })
  })

  it('shows a refusal as the reason it was refused, not as a generic failure', async () => {
    // Archiving is refused rather than resolved while a run is in progress, so the message the
    // server sends is the operator's next instruction and has to survive to the screen.
    archiveError = new ApiError(409, 'codex-1 has a run in progress. Wait for it to finish, or stop it first.')
    renderIdentity(agent())

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/run in progress/i),
    )
  })
})
