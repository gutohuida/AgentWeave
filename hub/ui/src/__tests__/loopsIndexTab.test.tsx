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
    current_tasks: [],
    open_questions: 0,
    firing_active: false,
    ...over,
  } as LoopSummary
}

function renderIndex(loops: LoopSummary[], opts: { isLoading?: boolean } = {}) {
  return render(
    <LoopsIndexTab
      loops={loops}
      isLoading={opts.isLoading ?? false}
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
      loop({ id: 'l3', ending_state: null, firing_active: true }),
    ])

    const summary = screen.getByTestId('loops-index-summary')
    expect(summary).toHaveTextContent('1 complete')
    expect(summary).toHaveTextContent('1 stopped early')
    expect(summary).toHaveTextContent('1 running')
  })

  it('does not call a loop running just because it has never ended', () => {
    // `ending_state: null` covers two different situations — firing right now, and never having
    // fired at all. A loop whose job is paused reported itself as running, which is the one thing
    // a status badge must not do. `firing_active` is the live fact that separates them.
    renderIndex([
      loop({ id: 'l1', ending_state: null, firing_active: false }),
      loop({ id: 'l2', ending_state: null, firing_active: true }),
    ])

    const summary = screen.getByTestId('loops-index-summary')
    expect(summary).toHaveTextContent('1 running')
    expect(summary).toHaveTextContent('1 idle')
    // Lowercase, per `design/mocks/S3/considered.html` — the badge reads `running`, not `Running`.
    expect(screen.getByText('idle')).toBeInTheDocument()
    expect(screen.getByText('running')).toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // Conformance to `design/mocks/S3/considered.html`, the variant the operator approved.
  // Each of these pins a divergence that was actually shipped and had to be corrected on
  // 2026-08-24, so the panel cannot drift back to it unnoticed.
  // ---------------------------------------------------------------------------

  it("folds open questions into the row's single status badge", () => {
    // The mock gives a row one badge and shows `1 open question` occupying that slot. The build
    // showed the ending state AND a second badge lower down, reading as two statuses for one loop.
    renderIndex([loop({ id: 'l1', ending_state: null, firing_active: false, open_questions: 1 })])

    expect(screen.getByText('1 open question')).toBeInTheDocument()
    expect(screen.queryByText('idle')).not.toBeInTheDocument()
  })

  it('writes the meta line as the mock does: @agent, a separator, then a lowercase queue count', () => {
    renderIndex([loop({ id: 'l1', agent: 'builder', queue: { pending: 2 } })])

    expect(screen.getByTestId('loops-index-agent-l1')).toHaveTextContent('@builder')
    expect(screen.getByText('queue 2')).toBeInTheDocument()
    // The previous build wrote `Queue: 2` as a separate span with no `@` on the agent.
    expect(screen.queryByText('Queue: 2')).not.toBeInTheDocument()
  })

  it('previews the shape of a row while loading, not a stack of blocks', () => {
    // Finding 7: "the point of a skeleton is that it previews the shape of what's coming". The
    // build used three 64px solid blocks; the mock uses four icon-plus-line rows and a toolbar
    // skeleton. Asserted by count and by the icon square's fixed 14px, which a block does not have.
    const { container } = renderIndex([], { isLoading: true })

    const skeletons = container.querySelectorAll('.skeleton')
    expect(skeletons.length).toBe(9) // one toolbar line + four rows of (icon square + line)
    const iconSquares = Array.from(skeletons).filter(
      (el) => (el as HTMLElement).style.width === '14px'
    )
    expect(iconSquares.length).toBe(4)
  })
})
