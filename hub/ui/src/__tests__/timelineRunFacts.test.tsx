import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentRunFacts, AgentSummary, RunLifecycleStatus } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'

/**
 * How a turn ended is read from the RUN'S OWN ROW, not reduced out of the event stream.
 *
 * Every test here passes `timelineEvents={[]}` on purpose. That is the reload case — a page
 * opened long after the run ended, holding persisted state and nothing else — and it is the
 * scenario F190 was filed for: the conversation simply stopped, with no label, because the
 * only thing that could have said otherwise was a lifecycle event the client had to reduce
 * its way to.
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
      timelineEvents={[]}
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
        timelineEvents={[]}
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
