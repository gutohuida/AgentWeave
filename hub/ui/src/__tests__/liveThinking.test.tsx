import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentRunFacts, AgentSummary } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { ConversationControls } from '@/components/agents/ConversationControls'

/**
 * live-thinking-opens-then-collapses and diagnostics-can-be-hidden (F572).
 *
 * `WorkBlockDisclosure` used to start every block closed, live or not, so a thinking event never
 * showed while the agent was reasoning; and every `diagnostic` card was drawn with no way to
 * hide it. Both are asserted at the component the operator sees, not at the helper behind it.
 */

vi.mock('@/components/common/Icon', () => ({
  Icon: ({ name }: { name: string }) => <span data-testid="icon" data-name={name} />,
}))

const PREFERENCE_KEY = 'aw.conversation.diagnostics.v1'

const agent: AgentSummary = {
  name: 'alice',
  status: 'running',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

let seq = 0
function entry(overrides: Partial<TimelineEntry>): TimelineEntry {
  seq += 1
  return {
    id: `e${seq}`,
    kind: 'agent_output',
    content: 'x',
    timestamp: '2026-08-02T00:00:00Z',
    delivery_state: 'delivered',
    run_id: 'run-1',
    ...overrides,
  }
}

const operatorInput = () => entry({ kind: 'operator_input', content: 'go' })
const thinking = (content = 'weighing the options') => entry({ output_kind: 'thinking', content })
const toolUse = () =>
  entry({ output_kind: 'tool_use', content: 'Bash', payload: { tool: 'Bash', input: '{"command":"ls"}', id: 't1' } })
const text = (content = 'the answer') => entry({ output_kind: 'text', content })
const completed = () =>
  entry({ output_kind: 'status', content: 'Completed', payload: { phase: 'completed' } })

function run(status: AgentRunFacts['status'], endedAt?: string): AgentRunFacts {
  return { status, started_at: '2026-08-02T00:00:00Z', ended_at: endedAt ?? null }
}

const ENDED = { 'run-1': run('completed', '2026-08-02T00:00:09Z') }

function renderTimeline(
  entries: TimelineEntry[],
  opts: { isRunning?: boolean; runs?: Record<string, AgentRunFacts> } = {},
) {
  const { isRunning = true, runs = { 'run-1': run('started') } } = opts
  const ui = (list: TimelineEntry[], running: boolean, runFacts: Record<string, AgentRunFacts>) => (
    <AgentTimeline agent={agent} entries={list} roster={[]} runs={runFacts} isRunning={running} />
  )
  const view = render(ui(entries, isRunning, runs))
  return {
    ...view,
    rerenderWith: (
      list: TimelineEntry[],
      running = isRunning,
      runFacts: Record<string, AgentRunFacts> = runs,
    ) => view.rerender(ui(list, running, runFacts)),
  }
}

function workBlock(): HTMLDetailsElement {
  const block = document.querySelector('details.work-disclosure')
  if (!block) throw new Error('no work block rendered')
  return block as HTMLDetailsElement
}

describe('live thinking opens, then collapses', () => {
  beforeEach(() => localStorage.clear())

  it('is open while the work block holding thinking is the last block of the live turn', () => {
    renderTimeline([operatorInput(), toolUse(), thinking()])
    expect(workBlock().open).toBe(true)
    expect(screen.getByText('weighing the options')).toBeVisible()
  })

  it('closes once a text entry follows it', () => {
    const early = [operatorInput(), toolUse(), thinking()]
    const view = renderTimeline(early)
    expect(workBlock().open).toBe(true)
    view.rerenderWith([...early, text()])
    expect(workBlock().open).toBe(false)
    expect(screen.queryByText('weighing the options')).not.toBeInTheDocument()
  })

  it('closes once the completed status follows it instead', () => {
    const early = [operatorInput(), thinking()]
    const view = renderTimeline(early)
    expect(workBlock().open).toBe(true)
    view.rerenderWith([...early, completed()], false, ENDED)
    expect(workBlock().open).toBe(false)
  })

  it('renders a history turn of an ended run closed', () => {
    renderTimeline([operatorInput(), thinking()], { isRunning: false, runs: ENDED })
    expect(workBlock().open).toBe(false)
  })

  it('does not open a live block that holds no thinking', () => {
    renderTimeline([operatorInput(), toolUse()])
    expect(workBlock().open).toBe(false)
  })

  it("keeps the operator's own toggle over the automatic rule, each time", () => {
    const early = [operatorInput(), toolUse(), thinking()]
    const more = thinking('more thought')
    const view = renderTimeline(early)
    const summary = () => workBlock().querySelector('summary') as HTMLElement

    // closed by the operator before text arrives: the next render must not reopen it
    fireEvent.click(summary())
    expect(workBlock().open).toBe(false)
    view.rerenderWith([...early, more])
    expect(workBlock().open).toBe(false)

    // opened by the operator after text arrived: the rule would have closed it, and the run's
    // end must not close it either
    const answer = text()
    view.rerenderWith([...early, more, answer])
    fireEvent.click(summary())
    expect(workBlock().open).toBe(true)
    view.rerenderWith([...early, more, answer, completed()], false, ENDED)
    expect(workBlock().open).toBe(true)
  })
})

describe('diagnostics can be hidden', () => {
  beforeEach(() => localStorage.clear())

  const diagnosticTurn = () => [
    operatorInput(),
    entry({ output_kind: 'diagnostic', content: 'runner stderr noise' }),
    entry({ output_kind: 'error', content: 'the run blew up' }),
    entry({ output_kind: 'tool_use', content: 'Bash', payload: { tool: 'Bash', input: '{}', id: 'f1' } }),
    entry({ output_kind: 'tool_result', content: 'boom', payload: { tool_use_id: 'f1', is_error: true } }),
  ]
  const settled = { isRunning: false, runs: { 'run-1': run('failed', '2026-08-02T00:00:09Z') } }

  function renderControls() {
    return render(
      <ConversationControls
        contextUsage={null}
        isRunning={false}
        isStopping={false}
        onStop={() => {}}
        currentConversationId="c1"
        handoffState="idle"
        handoffUnavailable={false}
        interactionLocked={false}
        onHandoff={() => {}}
        onFoldAll={() => {}}
      />,
    )
  }

  it('shows diagnostics by default', () => {
    renderTimeline(diagnosticTurn(), settled)
    expect(screen.getByText('runner stderr noise')).toBeInTheDocument()
  })

  it('removes only the diagnostic card, and the preference survives a remount', () => {
    const controls = renderControls()
    fireEvent.click(screen.getByRole('button', { name: 'Hide diagnostics' }))
    expect(localStorage.getItem(PREFERENCE_KEY)).toBe('hidden')
    expect(screen.getByRole('button', { name: 'Show diagnostics' })).toBeInTheDocument()

    const first = renderTimeline(diagnosticTurn(), settled)
    expect(screen.queryByText('runner stderr noise')).not.toBeInTheDocument()
    expect(screen.getByText('the run blew up')).toBeInTheDocument()
    expect(screen.getByText(/1 failed/)).toBeInTheDocument()

    first.unmount()
    controls.unmount()
    renderControls()
    expect(screen.getByRole('button', { name: 'Show diagnostics' })).toBeInTheDocument()
    renderTimeline(diagnosticTurn(), settled)
    expect(screen.queryByText('runner stderr noise')).not.toBeInTheDocument()
  })

  it('hides a card already on screen when the button is clicked, and brings it back', () => {
    renderControls()
    renderTimeline(diagnosticTurn(), settled)
    expect(screen.getByText('runner stderr noise')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Hide diagnostics' }))
    expect(screen.queryByText('runner stderr noise')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show diagnostics' }))
    expect(screen.getByText('runner stderr noise')).toBeInTheDocument()
  })

  it('treats an unreadable stored value as shown', () => {
    localStorage.setItem(PREFERENCE_KEY, '{not json')
    renderControls()
    expect(screen.getByRole('button', { name: 'Hide diagnostics' })).toBeInTheDocument()
    renderTimeline(diagnosticTurn(), settled)
    expect(screen.getByText('runner stderr noise')).toBeInTheDocument()
  })
})
