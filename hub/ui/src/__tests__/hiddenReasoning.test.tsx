import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentRunFacts, AgentSummary } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'

/**
 * vis-D10 (F578): Claude 5.x reasons without sharing the text. The Hub records a `thinking` row
 * with `payload.hidden` and no content; the conversation says the agent reasoned, in a muted line,
 * instead of an empty "Thinking" row that opens onto nothing.
 */

vi.mock('@/components/common/Icon', () => ({
  Icon: ({ name }: { name: string }) => <span data-testid="icon" data-name={name} />,
}))

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
    id: `h${seq}`,
    kind: 'agent_output',
    content: 'x',
    timestamp: '2026-10-17T00:00:00Z',
    delivery_state: 'delivered',
    run_id: 'run-1',
    ...overrides,
  }
}

const hidden = () =>
  entry({ output_kind: 'thinking', content: '', payload: { version: 1, text: '', hidden: true } })
const toolUse = () =>
  entry({ output_kind: 'tool_use', content: 'Bash', payload: { tool: 'Bash', input: '{"command":"ls"}', id: 't1' } })
const text = () => entry({ output_kind: 'text', content: 'the answer' })

const ENDED: Record<string, AgentRunFacts> = {
  'run-1': { status: 'completed', started_at: '2026-10-17T00:00:00Z', ended_at: '2026-10-17T00:00:05Z' },
}

function renderTimeline(entries: TimelineEntry[]) {
  return render(
    <AgentTimeline agent={agent} entries={entries} roster={[]} runs={ENDED} isRunning={false} />,
  )
}

describe('hidden reasoning (vis-D10)', () => {
  it('a turn whose only work is hidden reasoning shows one muted "Reasoned" line, not a work block', () => {
    renderTimeline([entry({ kind: 'operator_input', content: 'go' }), hidden(), text()])
    const line = screen.getByTestId('hidden-reasoning')
    expect(line.textContent).toContain('Reasoned')
    expect(line.getAttribute('title')).toMatch(/does not share/i)
    expect(document.querySelector('details.work-disclosure')).toBeNull()
    expect(screen.queryByText('Thinking')).toBeNull()
  })

  it('beside tool calls it is a "Reasoned" row that does not open onto nothing', () => {
    renderTimeline([entry({ kind: 'operator_input', content: 'go' }), hidden(), toolUse(), text()])
    const block = document.querySelector('details.work-disclosure') as HTMLDetailsElement
    fireEvent.click(block.querySelector('summary')!)
    const row = screen.getByTestId('hidden-reasoning-row')
    expect(row.textContent).toContain('Reasoned')
    expect(row.querySelector('button')).toBeNull()
    expect(screen.queryByText('Thinking')).toBeNull()
  })

  it('a thought with text is still a Thinking row', () => {
    renderTimeline([
      entry({ kind: 'operator_input', content: 'go' }),
      entry({ output_kind: 'thinking', content: 'weighing it' }),
      toolUse(),
      text(),
    ])
    const block = document.querySelector('details.work-disclosure') as HTMLDetailsElement
    fireEvent.click(block.querySelector('summary')!)
    expect(screen.getByText('Thinking')).toBeTruthy()
    expect(screen.queryByTestId('hidden-reasoning-row')).toBeNull()
  })
})
