import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ProjectCheckpoint } from '@/api/checkpoints'
import { CheckpointsPage, type CheckpointsPageProps } from '@/components/checkpoints/CheckpointsPage'
import { NO_FILTERS } from '@/components/checkpoints/checkpointModel'

vi.mock('@/components/traces/TraceDrawer', () => ({
  TraceButton: () => null,
}))

function checkpoint(over: Partial<ProjectCheckpoint> = {}): ProjectCheckpoint {
  return {
    id: 'ckpt-1',
    conversation_id: 'conv-a',
    agent: 'Builder',
    trigger: 'operator',
    status: 'ready',
    lineage_id: 'ckpt-1',
    title: 'The checkpoint',
    body: 'text',
    created_at: '2026-10-17T12:00:00Z',
    covered_runs: [],
    ...over,
  }
}

function page(opened: ProjectCheckpoint, over: Partial<CheckpointsPageProps> = {}) {
  const props: CheckpointsPageProps = {
    checkpoints: [opened],
    lineage: null,
    filters: NO_FILTERS,
    onFilters: vi.fn(),
    agents: ['QA', 'Builder'],
    conversations: [],
    conversationLabel: () => 'A conversation',
    selectedId: opened.id,
    onSelect: vi.fn(),
    onOpenConversation: vi.fn(),
    onStart: vi.fn().mockResolvedValue(undefined),
    now: new Date('2026-10-17T13:00:00Z'),
    ...over,
  }
  render(<CheckpointsPage {...props} />)
  return props
}

describe('starting a conversation from a checkpoint', () => {
  it('offers the checkpoint agent first, then starts the chosen agent with the message', async () => {
    const user = userEvent.setup()
    const props = page(checkpoint())
    await user.click(screen.getByTestId('checkpoint-start-open'))
    const picker = screen.getByTestId('checkpoint-start-agent')
    expect(within(picker).getAllByRole('option').map((o) => o.textContent)).toEqual(['Builder', 'QA'])
    await user.selectOptions(picker, 'QA')
    await user.type(screen.getByTestId('checkpoint-start-message'), 'Take it from here')
    await user.click(screen.getByTestId('checkpoint-start-confirm'))
    await waitFor(() => expect(props.onStart).toHaveBeenCalledWith('ckpt-1', 'QA', 'Take it from here'))
  })

  it('keeps the form open and says why when the start is refused', async () => {
    const user = userEvent.setup()
    page(checkpoint(), { onStart: vi.fn().mockRejectedValue(new Error('Agent is archived')) })
    await user.click(screen.getByTestId('checkpoint-start-open'))
    await user.click(screen.getByTestId('checkpoint-start-confirm'))
    expect(await screen.findByTestId('checkpoint-start-error')).toHaveTextContent('Agent is archived')
  })

  it('does not offer a start on a checkpoint nothing was written for', () => {
    page(checkpoint({ status: 'unwritten' }))
    expect(screen.queryByTestId('checkpoint-start-open')).toBeNull()
  })

  it('offers only the open agents, and the checkpoint agent first only when it is open', async () => {
    const user = userEvent.setup()
    page(checkpoint({ agent: 'Gone' }), { startAgents: ['Builder', 'QA'] })
    await user.click(screen.getByTestId('checkpoint-start-open'))
    const options = within(screen.getByTestId('checkpoint-start-agent')).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['Builder', 'QA'])
  })

  it('lists the carry-over and every started conversation with agent and time', async () => {
    const user = userEvent.setup()
    const props = page(
      checkpoint({
        carried_into: { conversation_id: 'conv-next' },
        started_conversations: [
          { conversation_id: 'conv-s1', agent: 'QA', title: 'First start', created_at: '2026-10-17T12:10:00Z' },
          { conversation_id: 'conv-s2', agent: 'Builder', title: 'Second start', created_at: '2026-10-17T12:20:00Z' },
        ],
      }),
    )
    expect(screen.getByTestId('checkpoint-detail-started')).toBeInTheDocument()
    const lineage = screen.getByTestId('checkpoint-detail-lineage')
    expect(lineage).toHaveTextContent('Carried over into')
    const first = within(screen.getByTestId('checkpoint-started-conv-s1'))
    expect(first.getByText('First start')).toBeInTheDocument()
    expect(screen.getByTestId('checkpoint-started-conv-s1')).toHaveTextContent('QA')
    expect(screen.getByTestId('checkpoint-started-conv-s2')).toHaveTextContent('Builder')
    await user.click(first.getByText('First start'))
    expect(props.onOpenConversation).toHaveBeenCalledWith('QA', 'conv-s1')
  })
})
