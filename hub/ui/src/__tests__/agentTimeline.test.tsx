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
    const timestamp = document.querySelector('time')
    expect(timestamp).toHaveAttribute('title', expect.stringMatching(/Sun 2 Aug, \d\d:\d\d:00/))
    expect(timestamp).toHaveAttribute('dateTime', '2026-08-02T00:00:00Z')
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

  it('explains a hop-budget-suspended chain and offers to continue it', () => {
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
    // The banner used to promise "They'll be delivered with your next message" — the leak this
    // change closes. It must name what the operator can actually do instead.
    expect(screen.queryByText(/delivered with your next message/)).not.toBeInTheDocument()
    expect(screen.getByText(/restart the count from here/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Continue'))
    expect(onDeliverNow).toHaveBeenCalled()
  })

  it('offers Continue and Discard on a held entry, and calls back with its id', () => {
    const onRelease = vi.fn()
    const onWithdraw = vi.fn()
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'held-1',
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
        onRelease={onRelease}
        onWithdraw={onWithdraw}
      />,
    )
    fireEvent.click(screen.getByText('Continue'))
    expect(onRelease).toHaveBeenCalledWith('held-1')
    // Named, not an X: on a held entry the choice is between two dispositions, and one of them
    // throws the message away permanently.
    fireEvent.click(screen.getByText('Discard'))
    expect(onWithdraw).toHaveBeenCalledWith('held-1')
  })

  it('does not offer Continue on a queued entry the hop budget is not holding', () => {
    const onRelease = vi.fn()
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'waiting-1',
            kind: 'inbound_peer',
            participant: 'codex',
            content: 'within budget, just waiting',
            delivery_state: 'queued',
            hop_budget_exceeded: false,
            run_id: undefined,
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
        onRelease={onRelease}
      />,
    )
    // Releasing it would be refused by the endpoint — it is waiting for something a re-base
    // does not fix — so the button would be an offer to be told no.
    expect(screen.queryByText('Continue')).not.toBeInTheDocument()
    expect(screen.getByText('queued')).toBeInTheDocument()
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

  it('shows the turn\'s measured token count beside "Worked for" (Q7 Gap 5)', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'a-tok', kind: 'agent_output', output_kind: 'text', run_id: 'run-done' })]}
        roster={[agent]}
        timelineEvents={[{ id: 'ev1', event_type: 'run_completed', timestamp: '2026-08-02T00:00:10Z', summary: '', data: { run_id: 'run-done' } }]}
        isRunning={false}
        recentTurns={[{
          id: 'tu-1',
          run_id: 'run-done',
          agent: 'claude',
          status: 'measured',
          runner: 'claude',
          model: 'claude-sonnet-5',
          input_tokens: 1000,
          output_tokens: 234,
          total_tokens: 1234,
          cache_read_tokens: null,
          cache_write_tokens: null,
          reasoning_tokens: null,
          api_equivalent_usd_micros: null,
          allowance: null,
          observed_at: '2026-08-02T00:00:10Z',
        }]}
      />,
    )
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('1,234 tokens')
  })

  it('omits the token stat entirely when the turn has no measured usage yet', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'a-notok', kind: 'agent_output', output_kind: 'text', run_id: 'run-done2' })]}
        roster={[agent]}
        timelineEvents={[
          { id: 'ev0', event_type: 'run_started', timestamp: '2026-08-02T00:00:00Z', summary: '', data: { run_id: 'run-done2' } },
          { id: 'ev1', event_type: 'run_completed', timestamp: '2026-08-02T00:00:10Z', summary: '', data: { run_id: 'run-done2' } },
        ]}
        isRunning={false}
      />,
    )
    const stat = screen.getByTestId('turn-worked-for')
    expect(stat).toHaveTextContent('Worked for')
    expect(stat).not.toHaveTextContent('tokens')
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

  it('renders no end-of-turn text for a normal successful run (operator: no end-of-conversation message)', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({ id: 'text-1', kind: 'agent_output', output_kind: 'text', content: 'here is the answer', run_id: 'run-ok' }),
          entry({
            id: 'status-1',
            kind: 'agent_output',
            output_kind: 'status',
            content: 'Completed',
            payload: { version: 1, phase: 'completed', summary: 'Completed' },
            run_id: 'run-ok',
            timestamp: '2026-08-02T00:00:01Z',
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('here is the answer')).toBeInTheDocument()
    expect(screen.queryByText('Completed')).not.toBeInTheDocument()
    expect(screen.queryByTestId(/result-card-/)).not.toBeInTheDocument()
  })

  it('still surfaces a failed run\'s error text — only the successful-completion sentinel is hidden', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'error-1',
            kind: 'agent_output',
            output_kind: 'error',
            content: 'claude_result_error: max turns reached',
            run_id: 'run-fail',
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('claude_result_error: max turns reached')).toBeInTheDocument()
  })

  it('still renders a non-terminal status entry (e.g. a plan), only the completed sentinel is hidden', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'status-plan',
            kind: 'agent_output',
            output_kind: 'status',
            content: 'Planning the change',
            payload: { version: 1, phase: 'plan', summary: 'Planning the change' },
            run_id: 'run-plan',
          }),
        ]}
        roster={[agent]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('Planning the change')).toBeInTheDocument()
    expect(screen.getByTestId('result-card-run-plan')).toBeInTheDocument()
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
    // Scoped to the diff itself. The collapsed row now also carries a green/red "+N −N" summary,
    // so an unscoped style selector picks that up instead of the first diff line.
    const diff = container.querySelector('[data-testid="tool-edit-diff"]')
    const removedLine = diff?.querySelector('[style*="var(--red)"]')
    const addedLine = diff?.querySelector('[style*="var(--green)"]')
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
    // The fallback is still "show the raw text", but the raw text is now the call's own input
    // rather than its "Called Edit" label — the label is already on the row, so repeating it was
    // the whole reason expanding a call felt empty. Input that will not parse is shown as sent.
    expect(screen.getByText('{not valid json')).toBeInTheDocument()
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
    // Declining the diff still shows the call's input, which names what was attempted.
    expect(screen.getByText(/old_string/)).toBeInTheDocument()
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
    expect(screen.getByText(/old_string/)).toBeInTheDocument()
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
    // MultiEdit's pair lives inside edits[], so the diff declines. The input is shown instead —
    // and `file_path` outranks the raw JSON, because the file a MultiEdit touched is the one
    // thing a reader wants from it. "Called MultiEdit" told them nothing.
    // Twice, legitimately: once in the block's "wrote to" summary chip and once in the expanded
    // call. Both are the file the write targeted, which is the point of showing it at all.
    expect(screen.getAllByText('x').length).toBeGreaterThan(0)
    expect(screen.queryByText('Called MultiEdit')).not.toBeInTheDocument()
  })
})

describe('AgentTimeline — the outbound message folds (conversations-continue phase 6)', () => {
  it('renders an outbound entry folded — the subject shows, the body does not, until expanded', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'fold-1',
            kind: 'outbound_peer',
            participant: 'codex',
            subject: 'Investigate the flaky test',
            content: 'Here is the full body of the delegation, much longer than the subject line.',
            run_id: 'run-1',
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('Investigate the flaky test')).toBeInTheDocument()
    expect(
      screen.queryByText('Here is the full body of the delegation, much longer than the subject line.'),
    ).not.toBeInTheDocument()
  })

  it('folds two messages to the same recipient to different lines when their subjects differ', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'fold-2a',
            kind: 'outbound_peer',
            participant: 'codex',
            subject: 'First delegation',
            content: 'body one',
            run_id: 'run-1',
          }),
          entry({
            id: 'fold-2b',
            kind: 'outbound_peer',
            participant: 'codex',
            subject: 'Second delegation',
            content: 'body two',
            run_id: 'run-2',
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('First delegation')).toBeInTheDocument()
    expect(screen.getByText('Second delegation')).toBeInTheDocument()
  })

  it('expands a folded outbound entry to show its content on click', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'fold-3',
            kind: 'outbound_peer',
            participant: 'codex',
            subject: 'Investigate the flaky test',
            content: 'the full body appears only once expanded',
            run_id: 'run-1',
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.queryByText('the full body appears only once expanded')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Investigate the flaky test'))
    expect(screen.getByText('the full body appears only once expanded')).toBeInTheDocument()
  })

  it('keeps a folded outbound entry expanded as later entries are appended', () => {
    const first = entry({
      id: 'fold-4',
      kind: 'outbound_peer',
      participant: 'codex',
      subject: 'Investigate the flaky test',
      content: 'stays visible after append',
      run_id: 'run-1',
    })
    const { rerender } = render(
      <AgentTimeline
        agent={agent}
        entries={[first]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    fireEvent.click(screen.getByText('Investigate the flaky test'))
    expect(screen.getByText('stays visible after append')).toBeInTheDocument()

    rerender(
      <AgentTimeline
        agent={agent}
        entries={[
          first,
          entry({
            id: 'fold-4-later',
            kind: 'agent_output',
            content: 'a later turn',
            run_id: 'run-2',
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('stays visible after append')).toBeInTheDocument()
  })

  it('leaves an inbound peer message unaffected — never folded, regardless of length', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'fold-5',
            kind: 'inbound_peer',
            participant: 'codex',
            content: 'a long inbound message that must render in full, not folded behind a subject line',
            run_id: 'run-1',
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(
      screen.getByText('a long inbound message that must render in full, not folded behind a subject line'),
    ).toBeInTheDocument()
  })

  it('folds an outbound entry with no subject to a readable line from its content', () => {
    render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'fold-6',
            kind: 'outbound_peer',
            participant: 'codex',
            content: 'first line of an older row\nsecond line stays hidden until expanded',
            run_id: 'run-1',
          }),
        ]}
        roster={[agent, peer]}
        timelineEvents={[]}
        isRunning={false}
      />,
    )
    expect(screen.getByText('first line of an older row')).toBeInTheDocument()
    expect(screen.queryByText('second line stays hidden until expanded')).not.toBeInTheDocument()
  })
})
