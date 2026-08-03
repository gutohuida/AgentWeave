import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentInfoTab } from '@/components/agents/AgentInfoTab'
import { RunnersPage } from '@/components/runners/RunnersPage'

const createMutate = vi.fn()
const bindMutate = vi.fn()

vi.mock('@/api/runners', () => ({
  useRunners: () => ({
    data: [
      {
        id: 'runner-default',
        project_id: 'proj-test',
        name: 'Claude Default',
        cli: 'claude',
        model: null,
        flags: null,
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
      },
      {
        id: 'runner-opus',
        project_id: 'proj-test',
        name: 'Claude Opus',
        cli: 'claude',
        model: 'claude-opus-5',
        flags: null,
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
      },
    ],
    isLoading: false,
  }),
  useCreateRunner: () => ({ mutate: createMutate, isPending: false }),
  useUpdateRunner: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteRunner: () => ({ mutate: vi.fn(), isPending: false }),
  useBindAgentRunner: () => ({ mutate: bindMutate, isPending: false, isError: false }),
}))

vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
  useBindAgentCharter: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }) }
})

describe('runner management UI', () => {
  beforeEach(() => {
    createMutate.mockReset()
    bindMutate.mockReset()
  })

  it('creates a custom runner variant without replacing the existing runner', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    expect(screen.getByText('Claude Default')).toBeInTheDocument()
    expect(screen.getByText('Claude Opus')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    await user.type(screen.getByPlaceholderText('e.g. Claude Opus'), 'Claude Sonnet')
    await user.type(screen.getByPlaceholderText('e.g. claude-sonnet-5'), 'claude-sonnet-5')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(createMutate).toHaveBeenCalledWith(
      { name: 'Claude Sonnet', cli: 'claude', model: 'claude-sonnet-5' },
      expect.any(Object),
    )
  })

  it('rebinds an agent to a different runner', async () => {
    const user = userEvent.setup()
    render(
      <AgentInfoTab
        agent={{
          name: 'claude',
          status: 'idle',
          message_count: 0,
          active_task_count: 0,
          runner_id: 'runner-default',
        }}
      />,
    )

    await user.selectOptions(screen.getByLabelText('Runner for claude'), 'runner-opus')
    expect(bindMutate).toHaveBeenCalledWith({ agent: 'claude', runnerId: 'runner-opus' })
  })
})
