import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'

const agent: AgentSummary = {
  name: 'claude',
  status: 'running',
  message_count: 0,
  active_task_count: 0,
}

const peer: AgentSummary = {
  name: 'codex',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  color_index: 1,
}

function entry(overrides: Partial<TimelineEntry>): TimelineEntry {
  return {
    id: 'e1',
    kind: 'agent_output',
    content: 'hello',
    timestamp: '2026-08-02T00:00:00Z',
    delivery_state: 'delivered',
    ...overrides,
  }
}

describe('AgentTimeline', () => {
  it('shows an empty state when there is nothing to show', () => {
    render(
      <AgentTimeline agent={agent} entries={[]} roster={[]} timelineEvents={[]} isRunning={false} />,
    )
    expect(screen.getByText('No conversation yet')).toBeInTheDocument()
  })

  it('labels an inbound peer message with the sender name (colour never carries identity alone)', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'in-1',
            kind: 'inbound_peer',
            participant: 'codex',
            content: 'hi from codex',
            run_id: 'run-1',
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('codex')).toBeInTheDocument()
    expect(screen.getByText('hi from codex')).toBeInTheDocument()
  })

  it('labels an outbound peer message with the recipient name, on the subject agent\'s side', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'out-1',
            kind: 'outbound_peer',
            participant: 'codex',
            content: 'delegating to codex',
            run_id: 'run-1',
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('codex')).toBeInTheDocument()
    expect(screen.getByText('delegating to codex')).toBeInTheDocument()
  })

  it('renders a queued entry as undelivered, distinct from the delivered ones', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'q1', kind: 'operator_input', content: 'not delivered yet', delivery_state: 'queued', run_id: undefined })]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('Waiting to be delivered')).toBeInTheDocument()
    expect(screen.getByText('not delivered yet')).toBeInTheDocument()
  })

  it('explains a hop-budget-suspended chain', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'susp-1',
            kind: 'inbound_peer',
            participant: 'codex',
            content: 'over budget',
            delivery_state: 'queued',
            hop_budget_exceeded: true,
            run_id: undefined,
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(
      screen.getByText('Autonomous continuation is paused — operator input will resume it.'),
    ).toBeInTheDocument()
  })

  it('offers to withdraw an undelivered entry and calls back with its id', () => {
    const onWithdraw = vi.fn()
    render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'q2', kind: 'operator_input', delivery_state: 'queued', run_id: undefined })]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
        onWithdraw={onWithdraw}
      />,
    )
    fireEvent.click(screen.getByTitle("Withdraw before it's delivered"))
    expect(onWithdraw).toHaveBeenCalledWith('q2')
  })

  it('shows a stop control on the running turn', () => {
    const onStop = vi.fn()
    render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'a1', kind: 'agent_output', output_kind: 'text', run_id: 'run-live' })]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning
        onStop={onStop}
      />,
    )
    fireEvent.click(screen.getByText('Stop'))
    expect(onStop).toHaveBeenCalled()
  })

  it('renders a stopped turn as deliberately stopped, not an error', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'a2', kind: 'agent_output', output_kind: 'text', run_id: 'run-done' })]}
        roster={[agent]}
        timelineEvents={[{ id: 'ev1', event_type: 'run_stopped', timestamp: '2026-08-02T00:00:00Z', summary: '', data: { run_id: 'run-done' } }]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('Stopped')).toBeInTheDocument()
  })

  it('folds a completed turn by default and unfolds it on click', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({ id: 'a3', kind: 'agent_output', output_kind: 'text', content: 'earlier turn body', run_id: 'run-old' }),
          entry({ id: 'a4', kind: 'agent_output', output_kind: 'text', content: 'latest turn body', run_id: 'run-new', timestamp: '2026-08-02T00:05:00Z' }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    // The earlier turn starts folded — its body is not in the document.
    expect(screen.queryByText('earlier turn body')).not.toBeInTheDocument()
    expect(screen.getByText('latest turn body')).toBeInTheDocument()

    fireEvent.click(screen.getAllByText('Turn')[0])
    expect(screen.getByText('earlier turn body')).toBeInTheDocument()
  })
})
