import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentRunFacts, AgentSummary, RunLifecycleStatus } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'

/**
 * How a turn ended is read from the RUN'S OWN ROW, not reduced out of the event stream.
 *
 * Every test here renders with `runs` and nothing else — no lifecycle events reach this
 * component at all any more (task 4.6a deleted the prop). That IS the reload case: a page
 * opened long after the run ended, holding persisted state and nothing else, which is the
 * scenario F190 was filed for. The conversation simply stopped, with no label, because the
 * only thing that could have said otherwise was a lifecycle event the client had to reduce
 * its way to through a list the route truncates.
 */

vi.mock('@/components/common/Icon', () => ({
  Icon: ({ name }: { name: string }) => <span data-testid="icon" data-name={name} />,
}))

const agent: AgentSummary = {
  name: 'claude',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
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

function facts(status: RunLifecycleStatus, overrides: Partial<AgentRunFacts> = {}): AgentRunFacts {
  return { status, started_at: '2026-08-02T00:00:00Z', ...overrides }
}

/** One turn, one run, and no live stream — the reload. */
function renderRun(runs: Record<string, AgentRunFacts>, isRunning = false) {
  return render(
    <AgentTimeline
      agent={agent}
      entries={[entry({ id: 'a1', run_id: 'run-1', content: 'half an answer' })]}
      roster={[]}
      runs={runs}
      isRunning={isRunning}
    />,
  )
}

describe("a run's terminal outcome, read from the run row", () => {
  it('labels a stopped run from persisted state alone, with no lifecycle events at all', () => {
    renderRun({ 'run-1': facts('stopped', { ended_at: '2026-08-02T00:00:04Z', exit_code: null }) })
    expect(screen.getByText(/Turn stopped/)).toBeInTheDocument()
  })

  it('labels an interrupted run — the Hub restarted under it, and the turn must say so', () => {
    renderRun({ 'run-1': facts('interrupted', { ended_at: '2026-08-02T00:00:04Z' }) })
    expect(screen.getByText(/Turn interrupted/)).toBeInTheDocument()
  })

  it('presents no terminal label while the run is still going', () => {
    // `started` is what a row whose `Run.status` is `running` looks like on the wire — the
    // route renames it at the boundary (design D5, agents.py). There is nothing to conclude
    // about a run that has not ended, so the turn carries no banner.
    renderRun({ 'run-1': facts('started') })
    expect(screen.queryByText(/Turn /)).not.toBeInTheDocument()
  })

  it('presents a failed run and a silently completed run as different terminal states', () => {
    const failed = render(
      <AgentTimeline
        agent={agent}
        entries={[entry({ id: 'a1', run_id: 'run-1', content: 'half an answer' })]}
        roster={[]}
        runs={{ 'run-1': facts('failed', { ended_at: '2026-08-02T00:00:04Z', exit_code: 1 }) }}
        isRunning={false}
      />,
    )
    expect(screen.getByText(/Turn failed/)).toBeInTheDocument()
    failed.unmount()

    // A clean turn ends without a banner, deliberately — operator, 2026-08-18: "We don't want
    // any end-of-conversation message." The two outcomes are distinguishable precisely because
    // only one of them says anything.
    renderRun({ 'run-1': facts('completed', { ended_at: '2026-08-02T00:00:04Z', exit_code: 0 }) })
    expect(screen.queryByText(/Turn /)).not.toBeInTheDocument()
  })
})

describe("a turn's duration, measured from the run row", () => {
  it('measures the whole run, spawn included, from started_at to ended_at', () => {
    // RE-BASELINED, not reconciled (design D4, task 4.5): `Run.started_at` is stamped when the
    // row is constructed (`agent_trigger.py:1073`) and the `run_started` event only once the pty
    // exists (`:1857-1864`), so this figure now includes the spawn and reads LONGER than the
    // event-derived one it replaces. That is the correct number, not a regression.
    renderRun({ 'run-1': facts('completed', { ended_at: '2026-08-02T00:00:14Z' }) })
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('Worked for 14s')
  })

  it('says nothing about a run that has not ended, rather than claiming 0s', () => {
    renderRun({ 'run-1': facts('started') })
    expect(screen.queryByTestId('turn-worked-for')).not.toBeInTheDocument()
  })

  it('renders no duration when the clock went backwards, rather than "Worked for -7s"', () => {
    // Carried across from `runDurationsByRunId`'s own guard, which this read replaces
    // (design D4). A clock that went backwards between two writes reads as a bug in the
    // product rather than in the clock.
    renderRun({ 'run-1': facts('completed', { ended_at: '2026-08-01T23:59:53Z' }) })
    expect(screen.queryByTestId('turn-worked-for')).not.toBeInTheDocument()
  })

  it('hands a stopped run a duration too — a turn that was cut short still cost something', () => {
    renderRun({ 'run-1': facts('stopped', { ended_at: '2026-08-02T00:00:06Z' }) })
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('Worked for 6s')
  })
})

/**
 * F269 (task 4.5a). The stat line is rendered *inside* the first agent block's fragment, and a
 * `status` entry is its own block (`RESULT_OUTPUT_KINDS` holds `status`). So when the turn's only
 * agent output is the terminal status row phase 2 now persists, the block that owns the stat line
 * is the one `isSuccessCompletionEntry` returns `null` for — and the cost of the turn goes with
 * the card it hung on.
 *
 * MEASURED SCOPE, iteration 5: a `failed` status row does *not* satisfy
 * `isSuccessCompletionEntry`, renders its own `ResultCard`, and carries the stat line along with
 * it. So a spawn failure is not an instance of F269 and a test written around one passes
 * vacuously. The case that must be made to pass is a status row whose `payload.phase` is
 * `completed` — a run that ended *successfully* having produced nothing else.
 */
describe('a turn that produced nothing still reports what it cost', () => {
  /** The F269 shape: the operator's message, the terminal status row, and nothing between. */
  function silentlyCompletedTurn(extra: TimelineEntry[] = []) {
    return render(
      <AgentTimeline
        agent={agent}
        entries={[
          entry({
            id: 'op-1',
            kind: 'operator_input',
            content: 'do the thing',
            run_id: 'run-1',
          }),
          ...extra,
          entry({
            id: 'status-finalize',
            kind: 'agent_output',
            output_kind: 'status',
            content: 'Run completed (exit 0).',
            payload: { phase: 'completed', exit_code: 0 },
            run_id: 'run-1',
            timestamp: '2026-08-02T00:00:05Z',
          }),
        ]}
        roster={[agent]}
        runs={{ 'run-1': facts('completed', { ended_at: '2026-08-02T00:00:05Z', exit_code: 0 }) }}
        isRunning={false}
      />,
    )
  }

  it('presents the stat line when the terminal status row is the turn\'s only agent output', () => {
    silentlyCompletedTurn()
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('Worked for 5s')
  })

  it('still draws no card for the status row itself — the fix is placement, not visibility', () => {
    // The operator does not want an end-of-turn message (2026-08-18). Making the row visible
    // would "fix" F269 by reintroducing the thing this component deliberately hides.
    silentlyCompletedTurn()
    expect(screen.queryByText('Run completed (exit 0).')).not.toBeInTheDocument()
    expect(screen.queryByTestId(/result-card-/)).not.toBeInTheDocument()
  })

  it('emits exactly one stat line when a text row precedes the status row', () => {
    // The stat line belongs to `firstAgentBlockId` alone. With a text row present that slot is
    // the text row's, so returning a fragment from the completion branch must not add a second.
    silentlyCompletedTurn([
      entry({
        id: 'text-1',
        kind: 'agent_output',
        output_kind: 'text',
        content: 'the answer',
        run_id: 'run-1',
        timestamp: '2026-08-02T00:00:03Z',
      }),
    ])
    expect(screen.getAllByTestId('turn-worked-for')).toHaveLength(1)
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('Worked for 5s')
  })
})

/**
 * Task 5.1 — the replacement for `agentTimelineModel.test.ts:223-235`, and the client half of
 * *Payload-shaped model functions are tested against real route ordering*.
 *
 * THE SHAPE HAS MOVED, and forcing the old wording would misdescribe it. The fixture being
 * replaced fed ASCENDING lifecycle events to `runStatusByRunId`, a last-write-wins reducer, and
 * asserted `run-1` ended `completed` — green, against a route that returns events NEWEST FIRST,
 * where the same reducer keeps `run_started` and reports a finished run as still going. That is
 * F190. Phase 4 deleted the reducer, so there is no longer a model function to feed events to.
 *
 * What replaced it is a keyed map the route builds by looking run ids up, read here as
 * `runs[turn.runId]`. Its ordering guarantee is therefore about the COMPONENT'S READ, and it is
 * exactly the requirement's *shuffled input* scenario: a consumer intended to be independent of
 * its input's ordering proves it by returning the same result for a shuffled input.
 *
 * The route's own half — that it still returns newest-first, and that the truncation is what makes
 * that load-bearing — is task 5.2, in `hub/tests/test_a_turn_says_how_it_ended.py`.
 *
 * Order-independence ALONE would be satisfied by a read that is uniformly wrong, so the second and
 * third tests assert the answers are right in each order rather than only that they agree.
 */
describe("the read of a run's facts does not depend on the map's ordering", () => {
  const OLD = facts('failed', { ended_at: '2026-08-02T00:00:06Z', exit_code: 1 })
  const NEW = facts('stopped', { ended_at: '2026-08-02T00:00:14Z', exit_code: null })

  /** Two turns in arrival order — the older run first, as `groupIntoTurns` receives them. */
  const twoTurns = [
    entry({ id: 'a1', run_id: 'run-old', content: 'the first answer' }),
    entry({ id: 'a2', run_id: 'run-new', content: 'the second answer' }),
  ]

  function renderBoth(runs: Record<string, AgentRunFacts>) {
    return render(
      <AgentTimeline agent={agent} entries={twoTurns} roster={[]} runs={runs} isRunning={false} />,
    )
  }

  it('renders identically when the map is shuffled — the same result for a shuffled input', () => {
    const newestFirst = renderBoth({ 'run-new': NEW, 'run-old': OLD })
    const a = newestFirst.container.textContent
    newestFirst.unmount()

    const newestLast = renderBoth({ 'run-old': OLD, 'run-new': NEW })
    expect(newestLast.container.textContent).toBe(a)
  })

  it("gives each turn its own run's outcome when the newest turn's row is FIRST in the map", () => {
    renderBoth({ 'run-new': NEW, 'run-old': OLD })
    expect(screen.getAllByText(/Turn stopped/)).toHaveLength(1)
    expect(screen.getAllByText(/Turn failed/)).toHaveLength(1)
    expect(screen.getByText('Worked for 14s')).toBeInTheDocument()
    expect(screen.getByText('Worked for 6s')).toBeInTheDocument()
  })

  it("gives each turn its own run's outcome when the newest turn's row is LAST in the map", () => {
    // This is the deleted reducer's own failure mode, restated against the shape that replaced
    // it: last-write-wins over an ordered input. It cannot happen to a keyed lookup, and that is
    // the claim being pinned down rather than assumed.
    renderBoth({ 'run-old': OLD, 'run-new': NEW })
    expect(screen.getAllByText(/Turn stopped/)).toHaveLength(1)
    expect(screen.getAllByText(/Turn failed/)).toHaveLength(1)
    expect(screen.getByText('Worked for 14s')).toBeInTheDocument()
    expect(screen.getByText('Worked for 6s')).toBeInTheDocument()
  })
})
