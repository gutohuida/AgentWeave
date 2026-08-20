import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary, AgentTimelineEvent } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { formatElapsedSeconds } from '@/hooks/useElapsedSeconds'
import { runDurationsByRunId } from '@/lib/agentTimelineModel'

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
 *   - the SETTLED "Worked for Xs" line, computed from the persisted lifecycle-event timestamps
 *     so a refresh cannot change what a finished turn claims it took.
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

function lifecycle(
  eventType: string,
  runId: string,
  timestamp: string,
): AgentTimelineEvent {
  return { id: `${eventType}-${runId}`, event_type: eventType, timestamp, summary: '', data: { run_id: runId } }
}

function renderTimeline(overrides: {
  isRunning?: boolean
  entries?: TimelineEntry[]
  timelineEvents?: AgentTimelineEvent[]
} = {}) {
  const { isRunning = false, entries = [], timelineEvents = [] } = overrides
  return render(
    <AgentTimeline
      agent={agent}
      entries={entries.length ? entries : [entry({ id: 'seed', run_id: 'run-seed' })]}
      roster={[]}
      timelineEvents={timelineEvents}
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

describe('runDurationsByRunId', () => {
  it('measures a run from its own start and terminal event', () => {
    const durations = runDurationsByRunId([
      lifecycle('run_started', 'run-1', '2026-08-02T00:00:00Z'),
      lifecycle('run_completed', 'run-1', '2026-08-02T00:00:12Z'),
    ])
    expect(durations['run-1']).toBe(12)
  })

  it('measures a failed run too — duration is not a success signal', () => {
    const durations = runDurationsByRunId([
      lifecycle('run_started', 'run-2', '2026-08-02T00:00:00Z'),
      lifecycle('run_failed', 'run-2', '2026-08-02T00:00:05Z'),
    ])
    expect(durations['run-2']).toBe(5)
  })

  it('omits a run that has not ended, rather than reporting 0', () => {
    const durations = runDurationsByRunId([lifecycle('run_started', 'run-3', '2026-08-02T00:00:00Z')])
    expect(durations['run-3']).toBeUndefined()
  })

  it('omits a run whose clock went backwards rather than showing a negative duration', () => {
    const durations = runDurationsByRunId([
      lifecycle('run_started', 'run-4', '2026-08-02T00:00:10Z'),
      lifecycle('run_completed', 'run-4', '2026-08-02T00:00:03Z'),
    ])
    expect(durations['run-4']).toBeUndefined()
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
      timelineEvents: [lifecycle('run_started', 'run-1', '2026-08-01T23:59:20Z')],
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
      timelineEvents: [
        lifecycle('run_started', 'run-1', '2026-08-02T00:00:00Z'),
        lifecycle('run_completed', 'run-1', '2026-08-02T00:00:09Z'),
      ],
    })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
    // ...and the settled line has taken over in the same render, not seconds later.
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('Worked for 9s')
  })

  it('keeps running while the agent is still working, even though it has already said something', () => {
    renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'thinking out loud' })],
      timelineEvents: [lifecycle('run_started', 'run-1', '2026-08-02T00:00:00Z')],
    })
    expect(screen.getByTestId('timeline-working-indicator')).toBeInTheDocument()
    expect(screen.queryByTestId('turn-worked-for')).not.toBeInTheDocument()
  })

  /**
   * Stop, then send again. The operator's report: "if I stop the turn and send a new message the
   * working indicator do not show anymore. Until that new message is done."
   *
   * `run_started` for the new run reaches `timelineEvents` before that run's first entry has been
   * grouped into a turn, so for that window the newest turn on screen is still the STOPPED one.
   * Judging by the last turn alone read that as settled and hid the indicator for the whole of
   * the new run.
   */
  it('shows again when a new run starts while the stopped turn is still the newest on screen', () => {
    renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'half an answer' })],
      timelineEvents: [
        lifecycle('run_started', 'run-1', '2026-08-02T00:00:00Z'),
        lifecycle('run_stopped', 'run-1', '2026-08-02T00:00:04Z'),
        // The new run has begun; none of its entries have arrived yet.
        lifecycle('run_started', 'run-2', '2026-08-02T00:00:06Z'),
      ],
    })
    expect(screen.getByTestId('timeline-working-indicator')).toBeInTheDocument()
  })

  it('stays hidden after a stop that is not followed by another run', () => {
    // The other half of the same boundary: a stop the operator does not follow up on must leave
    // the indicator down, or every stopped turn would count forever.
    renderTimeline({
      isRunning: true,
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'half an answer' })],
      timelineEvents: [
        lifecycle('run_started', 'run-1', '2026-08-02T00:00:00Z'),
        lifecycle('run_stopped', 'run-1', '2026-08-02T00:00:04Z'),
      ],
    })
    expect(screen.queryByTestId('timeline-working-indicator')).not.toBeInTheDocument()
  })
})

describe('the settled "Worked for Xs" line', () => {
  it('renders above the response once the run has finished', () => {
    renderTimeline({
      entries: [entry({ id: 'a1', run_id: 'run-1', content: 'the answer' })],
      timelineEvents: [
        lifecycle('run_started', 'run-1', '2026-08-02T00:00:00Z'),
        lifecycle('run_completed', 'run-1', '2026-08-02T00:00:12Z'),
      ],
    })
    expect(screen.getByTestId('turn-worked-for')).toHaveTextContent('Worked for 12s')
  })

  it('is absent for a turn whose run never reported an end', () => {
    renderTimeline({
      entries: [entry({ id: 'a1', run_id: 'run-1' })],
      timelineEvents: [lifecycle('run_started', 'run-1', '2026-08-02T00:00:00Z')],
    })
    expect(screen.queryByTestId('turn-worked-for')).not.toBeInTheDocument()
  })

  it('appears once per turn, not once per block', () => {
    renderTimeline({
      entries: [
        entry({ id: 'w1', run_id: 'run-1', output_kind: 'thinking', content: 'hmm' }),
        entry({ id: 'a1', run_id: 'run-1', content: 'the answer' }),
      ],
      timelineEvents: [
        lifecycle('run_started', 'run-1', '2026-08-02T00:00:00Z'),
        lifecycle('run_completed', 'run-1', '2026-08-02T00:00:07Z'),
      ],
    })
    expect(screen.getAllByTestId('turn-worked-for')).toHaveLength(1)
  })
})
