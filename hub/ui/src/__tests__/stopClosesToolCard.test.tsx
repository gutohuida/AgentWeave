import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentSummary, AgentRunFacts } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'

// F666 (`stop-closes-the-tool-card-it-interrupted`): a card reads by the result paired with it
// anywhere in its turn, and by its run's facts when it has none. Entries are fed in the order the
// chat routes return them (ascending), and each test asserts something that order decides.

vi.mock('@/components/common/Icon', () => ({
  Icon: ({ name }: { name: string }) => <span data-testid="icon" data-name={name} />,
}))

const agent: AgentSummary = {
  name: 'cop-1',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'copilot',
}

const RUN = 'run-e183cc3e1acd'
const CALL = 'toolu_01Ky1xyEL7aTrBkrR3fyKsZX'

let clock = 0
function row(kind: string, content: string, payload: Record<string, unknown> = {}, runId = RUN): TimelineEntry {
  clock += 1
  return {
    id: `${runId}-${clock}`,
    kind: 'agent_output',
    output_kind: kind,
    content,
    payload: { version: 1, ...payload },
    run_id: runId,
    timestamp: `2026-10-12T09:02:${String(clock).padStart(2, '0')}Z`,
    delivery_state: 'delivered',
  } as TimelineEntry
}

const shellUse = (call = CALL, runId = RUN) =>
  row('tool_use', 'Sleep 240 seconds then print done', { call_id: call, tool: 'shell', category: 'command', input: '{"command": "Start-Sleep -Seconds 240; echo done"}' }, runId)
const closing = (call = CALL) =>
  row('tool_result', 'shell interrupted', { call_id: call, tool: 'shell', output: '', summary: 'shell interrupted', is_error: false, status: 'interrupted' })
const stoppedLine = () => row('status', 'Run stopped (exit 1).', { phase: 'completed', exit_code: 1 })

function facts(status: AgentRunFacts['status']): AgentRunFacts {
  return { status, started_at: '2026-10-12T09:02:14Z', ended_at: '2026-10-12T09:02:41Z' }
}

function show(entries: TimelineEntry[], runs: Record<string, AgentRunFacts>) {
  render(<AgentTimeline agent={agent} entries={entries} roster={[agent]} runs={runs} isRunning={false} />)
}

function openAllWork() {
  for (const summary of screen.getAllByText(/^Work · /)) fireEvent.click(summary)
}

describe('a tool card after its run ended (F666)', () => {
  it('reads interrupted for an unanswered call in a stopped run (the work-PC rows)', () => {
    show([row('thinking', 'planning'), shellUse(), stoppedLine()], { [RUN]: facts('stopped') })
    openAllWork()
    expect(screen.getByText('interrupted')).toBeInTheDocument()
    expect(screen.queryByText('awaiting result')).toBeNull()
  })

  it('reads a closing row as interrupted, not as a failure', () => {
    show([row('thinking', 'planning'), shellUse(), closing(), stoppedLine()], { [RUN]: facts('stopped') })
    expect(screen.queryByText(/failed$/)).toBeNull()
    openAllWork()
    expect(screen.getByText('interrupted')).toBeInTheDocument()
    expect(screen.queryByText('completed')).toBeNull()
  })

  it('reads no result for an unanswered call in a completed run', () => {
    show([shellUse(), row('text', 'done')], { [RUN]: facts('completed') })
    openAllWork()
    expect(screen.getByText('no result')).toBeInTheDocument()
  })

  it('still awaits when there are no run facts (control)', () => {
    show([shellUse()], {})
    openAllWork()
    expect(screen.getByText('awaiting result')).toBeInTheDocument()
  })

  it('pairs a result recorded after a notice with its call (run-08d33fa23f8e)', () => {
    const edit = 'toolu_01MBqBcf45VUUwbngy4NitsX'
    show(
      [
        row('thinking', 'writing the file'),
        row('tool_use', 'Creating hello.txt', { call_id: edit, tool: 'edit', category: 'edit' }),
        row('diagnostic', 'Created file hello.txt', { stream: 'copilot', severity: 'info', summary: 'Created file hello.txt' }),
        row('tool_result', 'Created file hello.txt with 5 characters', { call_id: edit, tool: 'edit', is_error: false }),
        row('text', 'Done.'),
        row('status', 'Run completed (exit 0).', { phase: 'completed', exit_code: 0 }),
      ],
      { [RUN]: facts('completed') },
    )
    // One work block, not two: the result's own block is drawn at its call.
    expect(screen.getAllByText(/^Work · /)).toHaveLength(1)
    openAllWork()
    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(screen.queryByText('awaiting result')).toBeNull()
    expect(screen.queryByText('no result')).toBeNull()
  })

  it('keeps a closing row that lands after a notice on its card', () => {
    show(
      [
        shellUse(),
        row('diagnostic', 'Session notice', { stream: 'copilot', severity: 'info', summary: 'Session notice' }),
        closing(),
        stoppedLine(),
      ],
      { [RUN]: facts('stopped') },
    )
    expect(screen.getAllByText(/^Work · /)).toHaveLength(1)
    expect(screen.queryByText(/failed$/)).toBeNull()
    openAllWork()
    expect(screen.getAllByText('interrupted')).toHaveLength(1)
  })

  it('still renders a result whose call is not in the turn (control)', () => {
    show([row('tool_result', 'orphan output', { call_id: 'c-gone', is_error: false })], { [RUN]: facts('completed') })
    openAllWork()
    expect(screen.getByText('orphan output')).toBeInTheDocument()
  })

  it('renders a second result for one call on its own (control)', () => {
    show(
      [
        shellUse('c1'),
        row('tool_result', 'first result', { call_id: 'c1', tool: 'shell', is_error: false }),
        row('tool_result', 'second result', { call_id: 'c1', is_error: true }),
      ],
      { [RUN]: facts('completed') },
    )
    openAllWork()
    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(screen.getByText('second result')).toBeInTheDocument()
  })

  it('does not pair across runs', () => {
    const other = 'run-later'
    show(
      [shellUse('c1'), row('tool_result', 'first run result', { call_id: 'c1', tool: 'shell', is_error: false }), shellUse('c1', other)],
      { [RUN]: facts('completed'), [other]: facts('started') },
    )
    openAllWork()
    expect(screen.getAllByText('completed')).toHaveLength(1)
    expect(screen.getByText('awaiting result')).toBeInTheDocument()
  })
})
