import { StrictMode } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'

// Stub the Icon component so WorkRow's per-tool icon (Q7 D2) can be asserted by name
// without depending on the real lucide-react SVG output — same pattern as SidebarItem.test.tsx.
vi.mock('@/components/common/Icon', () => ({
  Icon: ({ name }: { name: string }) => <span data-testid="icon" data-name={name} />,
}))

const agent: AgentSummary = {
  name: 'claude',
  status: 'running',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
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
    expect(screen.getByText('→ codex')).toBeInTheDocument()
    expect(screen.getByText('delegating to codex')).toBeInTheDocument()
  })

  it('renders a queued entry inline, tagged QUEUED, distinct from the delivered ones', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'q1', kind: 'operator_input', content: 'not delivered yet', delivery_state: 'queued', run_id: undefined })]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('queued')).toBeInTheDocument()
    expect(screen.getByText('not delivered yet')).toBeInTheDocument()
  })

  it('explains a hop-budget-suspended chain and offers to deliver now', () => {
    const onDeliverNow = vi.fn()
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
        onDeliverNow={onDeliverNow}
      />,
    )
    expect(screen.getByText('Autonomous continuation paused')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Deliver now'))
    expect(onDeliverNow).toHaveBeenCalled()
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
    expect(screen.getByText(/Turn stopped/)).toBeInTheDocument()
  })

  it('leaves an earlier turn open when a newer turn arrives', () => {
    // The operator's complaint: "I don't want to automatically fold previous conversation upon
    // sending a new message." Foldedness used to be derived from `!isLastTurn`, so the turn
    // being read collapsed the instant a new run appended one.
    const earlier = entry({ id: 'a3', kind: 'agent_output', output_kind: 'text', content: 'earlier turn body', run_id: 'run-old' })
    const { rerender } = render(
      <AgentTimeline agent={agent} entries={[earlier]} roster={[agent]} timelineEvents={[]} isRunning={false} />,
    )
    expect(screen.getByText('earlier turn body')).toBeInTheDocument()

    rerender(
      <AgentTimeline
        agent={agent}
        entries={[
          earlier,
          entry({ id: 'a4', kind: 'agent_output', output_kind: 'text', content: 'latest turn body', run_id: 'run-new', timestamp: '2026-08-02T00:05:00Z' }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('earlier turn body')).toBeInTheDocument()
    expect(screen.getByText('latest turn body')).toBeInTheDocument()
    expect(screen.queryByText(/Turn folded/)).not.toBeInTheDocument()
  })

  it('folds any turn on demand, including the only turn, and keeps it folded', () => {
    const only = entry({ id: 'a3b', kind: 'agent_output', output_kind: 'text', content: 'only turn body', run_id: 'run-only' })
    const { rerender } = render(
      <AgentTimeline agent={agent} entries={[only]} roster={[agent]} timelineEvents={[]} isRunning={false} />,
    )

    // A single-turn conversation is still foldable — the control used to be hidden on the
    // last turn, which with no automatic folding would leave no way to fold at all.
    fireEvent.click(screen.getByTitle('Fold this turn'))
    expect(screen.queryByText('only turn body')).not.toBeInTheDocument()
    expect(screen.getByText(/Turn folded/)).toBeInTheDocument()

    // A manual fold survives a new turn arriving.
    rerender(
      <AgentTimeline
        agent={agent}
        entries={[
          only,
          entry({ id: 'a4b', kind: 'agent_output', output_kind: 'text', content: 'newer turn body', run_id: 'run-newer', timestamp: '2026-08-02T00:05:00Z' }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.queryByText('only turn body')).not.toBeInTheDocument()
    expect(screen.getByText('newer turn body')).toBeInTheDocument()

    fireEvent.click(screen.getByText(/Turn folded/))
    expect(screen.getByText('only turn body')).toBeInTheDocument()
  })

  it('folds every turn on demand via foldAllSignal', () => {
    const { rerender } = render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'a5', kind: 'agent_output', output_kind: 'text', content: 'latest turn body', run_id: 'run-new' })]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
        foldAllSignal={0}
      />,
    )
    expect(screen.getByText('latest turn body')).toBeInTheDocument()

    rerender(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'a5', kind: 'agent_output', output_kind: 'text', content: 'latest turn body', run_id: 'run-new' })]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
        foldAllSignal={1}
      />,
    )
    expect(screen.queryByText('latest turn body')).not.toBeInTheDocument()
    expect(screen.getByText(/Turn folded/)).toBeInTheDocument()
  })

  it('does not fold the newest turn on mount under StrictMode double-invoked effects', () => {
    // The Hub app renders inside <StrictMode>, which double-invokes effects on
    // mount specifically to surface bugs like a "skip the first run" guard
    // that a naive mounted-boolean ref defeats (a real bug this test pins).
    render(
      <StrictMode>
        <AgentTimeline
          agent={agent}
          entries={[entry({ id: 'a6', kind: 'agent_output', output_kind: 'text', content: 'freshly opened turn', run_id: 'run-fresh' })]}
          roster={[agent]}
          timelineEvents={[]}
          isRunning={false}
          foldAllSignal={0}
        />
      </StrictMode>,
    )
    expect(screen.getByText('freshly opened turn')).toBeInTheDocument()
    expect(screen.queryByText(/Turn folded/)).not.toBeInTheDocument()
  })
})

describe('AgentTimeline — execution-order work blocks (2026-08-04-hub-charcoal-visual-refresh)', () => {
  const interleavedEntries = [
    entry({ id: 'text_a', kind: 'agent_output', output_kind: 'text', content: 'let me check the file', run_id: 'run-x', timestamp: '2026-08-02T00:00:00Z' }),
    entry({ id: 'tool_1', kind: 'agent_output', output_kind: 'tool_use', content: 'Read', payload: { call_id: 'c1' }, run_id: 'run-x', timestamp: '2026-08-02T00:00:01Z' }),
    entry({ id: 'text_b', kind: 'agent_output', output_kind: 'text', content: 'now i will edit', run_id: 'run-x', timestamp: '2026-08-02T00:00:02Z' }),
    entry({ id: 'tool_2', kind: 'agent_output', output_kind: 'tool_use', content: 'Edit', payload: { call_id: 'c2' }, run_id: 'run-x', timestamp: '2026-08-02T00:00:03Z' }),
  ]

  it('renders work in execution order, never hoisted above the text that preceded it', () => {
    const { container } = render(
      <AgentTimeline agent={agent} entries={interleavedEntries} roster={[agent]} timelineEvents={[]} isRunning={false} />,
    )
    const text = container.textContent ?? ''
    const idxA = text.indexOf('let me check the file')
    const idxWork1 = text.indexOf('Work · 1 step')
    const idxB = text.indexOf('now i will edit')
    const idxWork2 = text.lastIndexOf('Work · 1 step')

    expect(idxA).toBeGreaterThanOrEqual(0)
    expect(idxA).toBeLessThan(idxWork1)
    expect(idxWork1).toBeLessThan(idxB)
    expect(idxB).toBeLessThan(idxWork2)
    expect(screen.getAllByText('Work · 1 step')).toHaveLength(2)
  })

  it('collapses a run of consecutive work entries into one block', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({ id: 'thinking', kind: 'agent_output', output_kind: 'thinking', content: 'thinking', run_id: 'run-y', timestamp: '2026-08-02T00:00:00Z' }),
          entry({ id: 'tool_1', kind: 'agent_output', output_kind: 'tool_use', content: 'Read', payload: { call_id: 'c1' }, run_id: 'run-y', timestamp: '2026-08-02T00:00:01Z' }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText(/Work · 2 steps/)).toBeInTheDocument()
  })

  it('tracks each work block\'s disclosure state independently', () => {
    render(
      <AgentTimeline agent={agent} entries={interleavedEntries} roster={[agent]} timelineEvents={[]} isRunning={false} />,
    )
    const [firstBlock, secondBlock] = screen.getAllByText('Work · 1 step')

    fireEvent.click(firstBlock)
    expect(screen.getByText('Read')).toBeInTheDocument()
    expect(screen.queryByText('Edit')).not.toBeInTheDocument()

    fireEvent.click(secondBlock)
    expect(screen.getByText('Edit')).toBeInTheDocument()
  })

  it('does not pair a tool_use with a tool_result across a block boundary', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({ id: 'tool_1', kind: 'agent_output', output_kind: 'tool_use', content: 'Read', payload: { call_id: 'c1' }, run_id: 'run-z', timestamp: '2026-08-02T00:00:00Z' }),
          entry({ id: 'text_between', kind: 'agent_output', output_kind: 'text', content: 'narration in between', run_id: 'run-z', timestamp: '2026-08-02T00:00:01Z' }),
          entry({ id: 'tool_result_1', kind: 'agent_output', output_kind: 'tool_result', content: 'file contents', payload: { call_id: 'c1' }, run_id: 'run-z', timestamp: '2026-08-02T00:00:02Z' }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    // Two separate work blocks (the tool_use, then — after intervening text — the
    // tool_result). Opening the first must show "awaiting result", not "completed",
    // proving the pairing lookup did not reach into the second block.
    fireEvent.click(screen.getAllByText('Work · 1 step')[0])
    expect(screen.getByText('awaiting result')).toBeInTheDocument()
  })
})

describe('AgentTimeline — WorkRow tool icon and label (Q7 D2)', () => {
  it('renders a mapped tool\'s icon and clean label, not the raw content text', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'tool_bash',
            kind: 'agent_output',
            output_kind: 'tool_use',
            content: 'Called Bash',
            payload: { call_id: 'c1', tool: 'Bash' },
            run_id: 'run-bash',
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    fireEvent.click(screen.getByText('Work · 1 step'))
    expect(screen.getByText('Bash')).toBeInTheDocument()
    expect(screen.queryByText('Called Bash')).not.toBeInTheDocument()
    const iconNames = screen.getAllByTestId('icon').map((el) => el.getAttribute('data-name'))
    expect(iconNames).toContain('terminal')
  })

  it('falls back to the Wrench icon and the existing generic label for an unmapped tool name', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'tool_future',
            kind: 'agent_output',
            output_kind: 'tool_use',
            content: 'Called SomeFutureTool',
            payload: { call_id: 'c1', tool: 'SomeFutureTool' },
            run_id: 'run-future',
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    fireEvent.click(screen.getByText('Work · 1 step'))
    expect(screen.getByText('Called SomeFutureTool')).toBeInTheDocument()
    const fallbackIconNames = screen.getAllByTestId('icon').map((el) => el.getAttribute('data-name'))
    expect(fallbackIconNames).toContain('build')
  })

  it('falls back to the Wrench icon without throwing for an entry with no payload at all', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'thinking_no_payload',
            kind: 'agent_output',
            output_kind: 'thinking',
            content: 'thinking',
            payload: undefined,
            run_id: 'run-think',
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    fireEvent.click(screen.getByText('Work · 1 step'))
    expect(screen.getByText('Thinking')).toBeInTheDocument()
    const fallbackIconNames = screen.getAllByTestId('icon').map((el) => el.getAttribute('data-name'))
    expect(fallbackIconNames).toContain('build')
  })
})

describe('AgentTimeline — WorkRow edit diff view (Q7 D2 section 3)', () => {
  function editEntry(overrides: Partial<TimelineEntry> & { payload: Record<string, unknown> }) {
    return entry({
      id: 'tool_edit',
      kind: 'agent_output',
      output_kind: 'tool_use',
      content: 'Called Edit',
      run_id: 'run-edit',
      ...overrides,
    })
  }

  function expandTheOnlyWorkRow() {
    fireEvent.click(screen.getByText('Work · 1 step'))
    fireEvent.click(screen.getByText('Edit'))
  }

  it('renders added/removed lines for a well-formed edit payload, not the raw text', () => {
    const { container } = render(
      <AgentTimeline
        agent={agent}
        entries={[
          editEntry({
            payload: { call_id: 'c1', tool: 'Edit', input: JSON.stringify({ old_string: 'foo', new_string: 'bar' }) },
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expandTheOnlyWorkRow()
    const removedLine = container.querySelector('[style*="var(--red)"]')
    const addedLine = container.querySelector('[style*="var(--green)"]')
    expect(removedLine?.textContent).toBe('- foo')
    expect(addedLine?.textContent).toBe('+ bar')
    expect(screen.queryByText('Called Edit')).not.toBeInTheDocument()
  })

  it('falls back to the raw text for input that is not valid JSON', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[editEntry({ payload: { call_id: 'c1', tool: 'Edit', input: '{not valid json' } })]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expandTheOnlyWorkRow()
    expect(screen.getByText('Called Edit')).toBeInTheDocument()
  })

  it('falls back to the raw text when payload.truncated is true, even with a well-formed pair', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          editEntry({
            payload: {
              call_id: 'c1',
              tool: 'Edit',
              input: JSON.stringify({ old_string: 'foo', new_string: 'bar' }),
              truncated: true,
            },
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expandTheOnlyWorkRow()
    expect(screen.getByText('Called Edit')).toBeInTheDocument()
  })

  it('falls back to the raw text when new_string is missing (a synthetic fixture, not a real tool shape)', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[editEntry({ payload: { call_id: 'c1', tool: 'Edit', input: JSON.stringify({ old_string: 'foo' }) } })]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expandTheOnlyWorkRow()
    expect(screen.getByText('Called Edit')).toBeInTheDocument()
  })

  it('falls back to the raw text for a real MultiEdit-shaped payload, since its pair lives inside edits[]', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          editEntry({
            content: 'Called MultiEdit',
            payload: {
              call_id: 'c1',
              tool: 'MultiEdit',
              input: '{"file_path":"x","edits":[{"old_string":"foo","new_string":"bar"}]}',
            },
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expandTheOnlyWorkRow()
    expect(screen.getByText('Called MultiEdit')).toBeInTheDocument()
  })
})
