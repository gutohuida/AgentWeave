import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentRunFacts, AgentSummary, RunLifecycleStatus } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { formatElapsedSeconds } from '@/hooks/useElapsedSeconds'

/**
 * The indicator lives in the timeline, not the composer.
 *
 * It was built in the composer first, because that is where `isRunning` already was — a
 * builder's reason, not a reader's. Operator, 2026-08-18: "I think the working should be on the
 * composer screen not the chat box. Right where the agent is supposed to answer. After answering
 * it could just look like worked for Xs and then the response underneath."
 *
 * So there are two distinct things here and they are deliberately sourced differently:
 *   - the LIVE indicator, timed by `useElapsedSeconds` from when this pane saw the run start;
 *   - the SETTLED "Worked for Xs" line, computed from the RUN ROW's own `started_at`/`ended_at`
 *     so a refresh cannot change what a finished turn claims it took. Its four cases — a
 *     measured run, an unended one, a backwards clock, a run that did not succeed — moved to
 *     `timelineRunFacts.test.tsx` with the reducer they used to exercise (task 4.4).
 */

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

/** A run row as the timeline route states one. `started_at` is fixed at the fixture epoch and
 *  `endedAt` is what distinguishes a finished run from one still going. */
function run(status: RunLifecycleStatus, endedAt?: string): AgentRunFacts {
  return { status, started_at: '2026-08-02T00:00:00Z', ended_at: endedAt ?? null }
}

function renderTimeline(overrides: {
  isRunning?: boolean
  entries?: TimelineEntry[]
  runs?: Record<string, AgentRunFacts>
} = {}) {
  const { isRunning = false, entries = [], runs = {} } = overrides
  return render(
    <AgentTimeline
      agent={agent}
      entries={entries.length ? entries : [entry({ id: 'seed', run_id: 'run-seed' })]}
      roster={[]}
      runs={runs}
      isRunning={isRunning}
    />,
  )
}

describe('formatElapsedSeconds', () => {
  it('reads as bare seconds under a minute', () => {
    expect(formatElapsedSeconds(0)).toBe('0s')
    expect(formatElapsedSeconds(59)).toBe('59s')
  })

  it('switches to m:ss at and beyond a minute', () => {
    expect(formatElapsedSeconds(60)).toBe('1:00')
    expect(formatElapsedSeconds(63)).toBe('1:03')
    expect(formatElapsedSeconds(600)).toBe('10:00')
  })
})

describe('the live working indicator', () => {
  // Pinned to the fixture timestamps above, because the counter is now derived from the run's
  // own first entry rather than from when the pane mounted. Without a fixed clock the assertions
  // below would read the real gap between 2026-08-02 and today.
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(Date.parse('2026-08-02T00:00:00Z'))
  })
  afterEach(() => vi.useRealTimers())

  it('is absent while idle', () => {
    renderTimeline({ isRunning: false })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
  })

  it('appears at 0s when a run starts and counts up', () => {
    renderTimeline({ isRunning: true })
    expect(screen.getByTestId('timeline-working-indicator')).toHaveTextContent('Working · 0s')

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByTestId('timeline-working-indicator')).toHaveTextContent('Working · 3s')
  })

  it('reads the age of the run, not the age of the pane', () => {
    // The operator's report: "leaving a conversation and jumping to another agent composer
    // resets the working timer — it goes back to 0". A pane mounting against a run that began
    // 40 seconds ago must open at 40s, because the origin is the run's first entry rather than
    // this component's mount.
    renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', timestamp: '2026-08-01T23:59:20Z' })],
      runs: { 'run-1': { status: 'started', started_at: '2026-08-01T23:59:20Z', ended_at: null } },
    })
    expect(screen.getByTestId('timeline-working-indicator')).toHaveTextContent('Working · 40s')
  })

  it('is announced to assistive tech, since it is the only sign the agent is alive', () => {
    renderTimeline({ isRunning: true })
    expect(screen.getByTestId('timeline-working-indicator')).toHaveAttribute('aria-live', 'polite')
  })

  it('is not in the composer any more', () => {
    renderTimeline({ isRunning: true })
    expect(screen.queryByTestId('composer-working-indicator')).not.toBeInTheDocument()
  })

  /**
   * The regression the operator caught: `isRunning` is `agent.status === 'running'`, a POLLED
   * field, while the answer and the run's terminal event both arrive over SSE. That left the
   * counter running underneath a finished message for a second or two before flipping.
   *
   * Both assertions below matter and they pull in opposite directions — a fix that only hid the
   * indicator whenever an answer appeared would pass the first and fail the second, and would be
   * wrong, because an agent legitimately keeps working after emitting text.
   */
  it('stops the moment the run reports terminal, even while the polled status still says running', () => {
    renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'the answer' })],
      runs: { 'run-1': run('completed', '2026-08-02T00:00:09Z') },
    })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
    // ...and the settled line has taken over in the same render, not seconds later.
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('Worked for 9s')
  })

  it('keeps running while the agent is still working, even though it has already said something', () => {
    renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'thinking out loud' })],
      runs: { 'run-1': run('started') },
    })
    expect(screen.getByTestId('timeline-working-indicator')).toBeInTheDocument()
    expect(screen.queryByTestId('turn-worked-for')).not.toBeInTheDocument()
  })

  /**
   * Stop, then send again. The operator's report: "if I stop the turn and send a new message the
   * working indicator do not show anymore. Until that new message is done."
   *
   * The new run's ROW reaches `runs` before that run's first entry has been
   * grouped into a turn, so for that window the newest turn on screen is still the STOPPED one.
   * Judging by the last turn alone read that as settled and hid the indicator for the whole of
   * the new run.
   */
  it('shows again when a new run starts while the stopped turn is still the newest on screen', () => {
    renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'half an answer' })],
      runs: {
        'run-1': run('stopped', '2026-08-02T00:00:04Z'),
        // The new run has begun; none of its entries have arrived yet.
        'run-2': run('started'),
      },
    })
    expect(screen.getByTestId('timeline-working-indicator')).toBeInTheDocument()
  })

  it('stays hidden after a stop that is not followed by another run', () => {
    // The other half of the same boundary: a stop the operator does not follow up on must leave
    // the indicator down, or every stopped turn would count forever.
    renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'half an answer' })],
      runs: { 'run-1': run('stopped', '2026-08-02T00:00:04Z') },
    })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
  })
})

describe('the settled "Worked for Xs" line', () => {
  it('renders above the response once the run has finished', () => {
    renderTimeline({
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'the answer' })],
      runs: { 'run-1': run('completed', '2026-08-02T00:00:12Z') },
    })
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('Worked for 12s')
  })

  it('is absent for a turn whose run never reported an end', () => {
    renderTimeline({
      entries: [entry({ id: 'a1', run_id: 'run-1' })],
      runs: { 'run-1': run('started') },
    })
    expect(screen.queryByTestId('turn-worked-for')).not.toBeInTheDocument()
  })

  it('appears once per turn, not once per block', () => {
    renderTimeline({
      entries: [
        entry({ id: 'w1', run_id: 'run-1', output_kind: 'thinking', content: 'hmm' }),
        entry({ id: 'a1', run_id: 'run-1', content: 'the answer' }),
      ],
      runs: { 'run-1': run('completed', '2026-08-02T00:00:07Z') },
    })
    expect(screen.getAllByTestId('turn-worked-for')).toHaveLength(1)
  })
})

/**
 * F190's THIRD consequence (task 4.7), and the one round 1 missed. `anotherRunIsUnderway` is OR'd
 * into `runVisiblyActive`, so it defeats the live path as well as the reloaded one — a check that
 * only reloaded a page would have passed while the live regression stood.
 *
 * The defect: that signal used to be reduced out of the route's lifecycle events, which the
 * route truncates — a prop this component no longer even receives (task 4.6a).
 * An older run whose terminal event fell off the end read as *still going* forever, so any agent
 * with enough history kept an indicator burning under a finished conversation. It now reads the
 * `runs` map, which carries a row for every run the returned events name and cannot be truncated
 * away from a run it mentions.
 *
 * "Live" and "reloaded" differ in what has landed, not in which prop is populated: live, the
 * newest run's `status` row has streamed in over SSE but its run ROW is still whatever the last
 * HTTP fetch said (`started`); reloaded, everything is persisted and every row is terminal.
 */
describe("F190's third consequence — an older ended run no longer keeps the indicator alive", () => {
  const older = entry({ id: 'a1', run_id: 'run-1', content: 'an older answer' })
  const newest = entry({ id: 'a2', run_id: 'run-2', content: 'the newest answer' })
  /** What task 2.2 persists at the end of every run, whatever its outcome. */
  const newestSettled = entry({
    id: 'status-2',
    output_kind: 'status',
    content: 'Run completed (exit 0).',
    payload: { phase: 'completed', exit_code: 0 },
    run_id: 'run-2',
    timestamp: '2026-08-02T00:00:09Z',
  })

  it('LIVE: is gone once the newest run has settled, though the roster still says running', () => {
    // The live shape precisely: the status row has streamed in, the newest run's ROW has not been
    // refetched yet and still reads `started`, and the older run ended long ago.
    renderTimeline({
      isRunning: true,
      entries: [older, newest, newestSettled],
      runs: {
        'run-1': run('completed', '2026-08-02T00:00:04Z'),
        'run-2': run('started'),
      },
    })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
  })

  it('RELOADED: the same conversation opened fresh, with no live stream at all', () => {
    renderTimeline({
      isRunning: true,
      entries: [older, newest, newestSettled],
      runs: {
        'run-1': run('completed', '2026-08-02T00:00:04Z'),
        'run-2': run('completed', '2026-08-02T00:00:09Z'),
      },
    })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
  })

  it('STILL UNDERWAY: a genuinely open run behind the newest turn does keep it alive', () => {
    // The 2026-08-20 fix, asserted against a history deep enough to have exercised the defect.
    // It passed vacuously while the indicator showed for everything; it has to still pass now
    // that hiding is the default.
    renderTimeline({
      isRunning: true,
      entries: [older, newest, newestSettled],
      runs: {
        'run-1': run('completed', '2026-08-02T00:00:04Z'),
        'run-2': run('completed', '2026-08-02T00:00:09Z'),
        // Sent while the newest turn was still the one on screen — no entries of its own yet.
        'run-3': run('started'),
      },
    })
    expect(screen.getByTestId('timeline-working-indicator')).toBeInTheDocument()
  })
})

/**
 * Task 4.7's per-runner guards. These three cases are not one claim: phase 0 WATCHED the Claude
 * one work (task 0.3, which falsified round 3b), and the other two have never worked, so asserting
 * them together would assert the wrong thing about one of them.
 */
describe('a single-run conversation, once the run has ended', () => {
  const answer = entry({ id: 'a1', run_id: 'run-1', content: 'the answer' })
  /** The stream parser's sentinel — Claude emits one, Codex has never emitted anything. */
  const parserCompleted = entry({
    id: 'status-parser',
    output_kind: 'status',
    content: 'Completed',
    payload: { version: 1, phase: 'completed', summary: 'Completed' },
    run_id: 'run-1',
    timestamp: '2026-08-02T00:00:08Z',
  })
  /** Task 2.2's finalize row, written for either runner and every outcome. */
  function finalized(text: string, exitCode: number) {
    return entry({
      id: 'status-finalize',
      output_kind: 'status',
      content: text,
      payload: { phase: 'completed', exit_code: exitCode },
      run_id: 'run-1',
      timestamp: '2026-08-02T00:00:09Z',
    })
  }

  it('CLAUDE, completed: UNCHANGED — it already released on the answer, and still does', () => {
    // A regression guard, not a repair. Phase 0 measured this working on 2026-09-01; round 3b's
    // claim that it was broken was falsified there. The run row is deliberately still `started`:
    // that is what makes this an assertion about signal 1 rather than about the refetch.
    renderTimeline({
      isRunning: true,
      entries: [answer, parserCompleted, finalized('Run completed (exit 0).', 0)],
      runs: { 'run-1': run('started') },
    })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
  })

  it('CODEX, completed: CHANGED — it had no sentinel of its own and now has a persisted one', () => {
    // F270. Codex emits no completion sentinel, so signal 1 has never fired for it and the
    // indicator lingered for one `useAgentTimeline` round trip after every clean turn.
    const codex: AgentSummary = { ...agent, runner: 'codex' }
    const withoutTheRow = render(
      <AgentTimeline
        agent={codex}
        entries={[answer]}
        roster={[]}
        runs={{ 'run-1': run('started') }}
        isRunning
      />,
    )
    expect(screen.getByTestId('timeline-working-indicator')).toBeInTheDocument()
    withoutTheRow.unmount()

    render(
      <AgentTimeline
        agent={codex}
        entries={[answer, finalized('Run completed (exit 0).', 0)]}
        roster={[]}
        runs={{ 'run-1': run('started') }}
        isRunning
      />,
    )
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
  })

  it('STOPPED: CHANGED — the case no parser sentinel has ever covered, on either runner', () => {
    // Bound to a stopped run specifically, as task 4.7 requires: no `result` line is emitted for
    // a stop, so no parser row is ever written, and the completed-run version of this assertion
    // would pass today and prove nothing. `phase` is still "completed" on the persisted row — it
    // means "the run has ended", not "it succeeded".
    const withoutTheRow = renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'half an answer' })],
      runs: { 'run-1': run('started') },
    })
    expect(screen.getByTestId('timeline-working-indicator')).toBeInTheDocument()
    withoutTheRow.unmount()

    renderTimeline({
      isRunning: true,
      entries: [
        entry({ id: 'a1', run_id: 'run-1', content: 'half an answer' }),
        finalized('Run stopped (exit 15).', 15),
      ],
      runs: { 'run-1': run('started') },
    })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
  })
})
