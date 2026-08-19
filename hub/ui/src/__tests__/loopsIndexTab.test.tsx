import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LoopsIndexTab } from '@/components/spec/LoopsIndexTab'
import type { LoopSummary } from '@/api/loops'

afterEach(() => cleanup())

function loop(over: Partial<LoopSummary> = {}): LoopSummary {
  return {
    id: 'loop-1',
    label: 'Nightly sweep',
    agent: 'builder',
    purpose: 'keep the queue moving',
    stop_when_queue_empties: true,
    queue: { pending: 2 },
    current_task: null,
    open_questions: 0,
    firing_active: false,
    ...over,
  } as LoopSummary
}

function renderIndex(loops: LoopSummary[]) {
  return render(
    <LoopsIndexTab
      loops={loops}
      isLoading={false}
      includeArchived={false}
      onToggleIncludeArchived={vi.fn()}
      currentLoopId={null}
      onSelect={vi.fn()}
    />,
  )
}

describe('LoopsIndexTab — the governance glance (task B5.1)', () => {
  it('names the agent that owns each loop', () => {
    // The index listed a label and a purpose but never said whose loop it was, so "what is
    // running right now" could not be answered by agent (operator, 2026-08-19).
    renderIndex([loop({ id: 'loop-a', agent: 'builder' }), loop({ id: 'loop-b', agent: 'verifier' })])

    expect(screen.getByTestId('loops-index-agent-loop-a')).toHaveTextContent('builder')
    expect(screen.getByTestId('loops-index-agent-loop-b')).toHaveTextContent('verifier')
  })

  it('renders a loop whose agent is absent or empty rather than a stray icon', () => {
    // The server schema defaults `agent` to an empty string, so "present but empty" is real.
    renderIndex([loop({ id: 'loop-c', agent: '' })])

    expect(screen.getByTestId('loops-index-row-loop-c')).toBeInTheDocument()
    expect(screen.queryByTestId('loops-index-agent-loop-c')).not.toBeInTheDocument()
  })

  it('counts by ending state, never by matching stop_reason text (B5.3)', () => {
    renderIndex([
      loop({ id: 'l1', ending_state: 'completed' }),
      loop({ id: 'l2', ending_state: 'stopped', stop_reason: 'operator stopped it' }),
      loop({ id: 'l3', ending_state: null }),
    ])

    const summary = screen.getByTestId('loops-index-summary')
    expect(summary).toHaveTextContent('1 complete')
    expect(summary).toHaveTextContent('1 stopped early')
    expect(summary).toHaveTextContent('1 running')
  })
})
