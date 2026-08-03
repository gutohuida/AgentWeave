import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChartersPage } from '@/components/charters/ChartersPage'
import { AgentInfoTab } from '@/components/agents/AgentInfoTab'

const createMutate = vi.fn()
const bindMutate = vi.fn()

vi.mock('@/api/charters', () => ({
  useCharters: () => ({
    data: [
      {
        id: 'charter-one',
        project_id: 'proj-test',
        name: 'Release Guardian',
        content: 'Verify every release.',
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
      },
      {
        id: 'charter-two',
        project_id: 'proj-test',
        name: 'Incident Commander',
        content: 'Coordinate incidents.',
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
      },
    ],
    isLoading: false,
  }),
  useCreateCharter: () => ({ mutate: createMutate, isPending: false }),
  useUpdateCharter: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteCharter: () => ({ mutate: vi.fn(), isPending: false }),
  useBindAgentCharter: () => ({ mutate: bindMutate, isPending: false, isError: false }),
}))

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [], isLoading: false }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
  }
})

describe('charter management UI', () => {
  beforeEach(() => {
    createMutate.mockReset()
    bindMutate.mockReset()
  })

  it('lists charters and submits custom authored content', async () => {
    const user = userEvent.setup()
    render(<ChartersPage />)

    expect(screen.getByText('Release Guardian')).toBeInTheDocument()
    expect(screen.getByText('Verify every release.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'New Charter' }))
    await user.type(screen.getByLabelText('Charter name'), 'Incident Commander')
    await user.type(screen.getByLabelText('Charter content'), 'Coordinate incident response.')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(createMutate).toHaveBeenCalledWith(
      { name: 'Incident Commander', content: 'Coordinate incident response.' },
      expect.any(Object),
    )
  })

  it('reassigns a charter from the agent detail view', async () => {
    const user = userEvent.setup()
    render(
      <AgentInfoTab
        agent={{
          name: 'claude',
          status: 'idle',
          message_count: 0,
          active_task_count: 0,
          charter_id: 'charter-two',
        }}
      />,
    )

    await user.selectOptions(screen.getByLabelText('Charter for claude'), 'charter-one')
    expect(bindMutate).toHaveBeenCalledWith({ agent: 'claude', charterId: 'charter-one' })
  })
})
