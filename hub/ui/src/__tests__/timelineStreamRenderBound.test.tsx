import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import { insertStreamedOutput, type ChatHistoryResponse, type TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'

// Perf slice 4, R4: a streamed line re-renders its own row, not the conversation. Every markdown
// body is counted as it renders; a 1,000-row conversation used to parse all of them again for each
// line (about 660 ms of main-thread work per line on a CPU slowed six times).
const rendered: string[] = []
vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => {
    rendered.push(children)
    return <p>{children}</p>
  },
}))

const agent: AgentSummary = {
  name: 'claude',
  status: 'running',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}
const roster = [agent]

const RUNS = 40
const PER_RUN = 25

/** 1,000 rows in the order the chat route returns them: ascending time, a run's rows together. */
function history(): ChatHistoryResponse {
  const entries: TimelineEntry[] = []
  for (let r = 0; r < RUNS; r += 1) {
    for (let i = 0; i < PER_RUN; i += 1) {
      const n = r * PER_RUN + i
      entries.push({
        id: `out-${n}`,
        kind: i === 0 ? 'operator_input' : 'agent_output',
        output_kind: i === 0 ? undefined : 'text',
        content: `row ${n} of run ${r}`,
        timestamp: new Date(Date.UTC(2026, 9, 25, 10, 0, n)).toISOString(),
        delivery_state: 'delivered',
        run_id: `run-${r}`,
      })
    }
  }
  return { conversation_id: 'conv-1', session_id: null, agent: 'claude', entries, runs: {} }
}

function timeline(h: ChatHistoryResponse) {
  return <AgentTimeline agent={agent} entries={h.entries} roster={roster} runs={h.runs} isRunning />
}

describe('a streamed line in a long conversation', () => {
  it('renders the new line, and no markdown already on screen again', () => {
    const before = history()
    const { rerender } = render(timeline(before))
    expect(rendered.length).toBe(RUNS * PER_RUN)

    rendered.length = 0
    const line: TimelineEntry = {
      id: 'out-new',
      kind: 'agent_output',
      output_kind: 'text',
      content: 'the streamed line',
      timestamp: new Date(Date.UTC(2026, 9, 25, 11, 0, 0)).toISOString(),
      delivery_state: 'delivered',
      run_id: `run-${RUNS - 1}`,
    }
    const after = insertStreamedOutput(before, line)
    rerender(timeline(after))

    expect(screen.getByText('the streamed line')).toBeInTheDocument()
    expect(rendered).toEqual(['the streamed line'])
  })

  it('a line that starts a new turn renders only that turn', () => {
    const before = history()
    const { rerender } = render(timeline(before))
    rendered.length = 0
    const after = insertStreamedOutput(before, {
      id: 'out-next-run',
      kind: 'agent_output',
      output_kind: 'text',
      content: 'a new run speaks',
      timestamp: new Date(Date.UTC(2026, 9, 25, 12, 0, 0)).toISOString(),
      delivery_state: 'delivered',
      run_id: 'run-next',
    })
    rerender(timeline(after))
    expect(rendered).toEqual(['a new run speaks'])
    expect(document.querySelectorAll('[data-turn-boundary]').length).toBe(RUNS + 1)
  })
})
