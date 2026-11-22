// mock state for the dashboard Overview ("overview-next"). Everything here is hand-written: the
// recorded fixtures of a fresh checkout are stubs, and the three states (busy, quiet, trouble) are
// not in any recording. Times are minutes before the mock clock.
import type { DashActivity, DashBuild, DashNeed } from '@/components/overview/OverviewDashboard'
import type { FinishedTally, MainHealth, SpendFigures } from '@/components/overview/overviewDashboardModel'

export type OverviewNextState = 'busy' | 'quiet' | 'trouble'
export const OVERVIEW_NEXT_STATES: OverviewNextState[] = ['busy', 'quiet', 'trouble']

/** `ago` is minutes before the mock clock; `to` names, for the toast, where a click would go. */
interface NeedSpec extends Omit<DashNeed, 'at' | 'onOpen'> {
  ago: number
  to: string
}
interface ActSpec extends Omit<DashActivity, 'at' | 'onOpen'> {
  ago: number
  to: string
}
interface BuildSpec extends Omit<DashBuild, 'onOpen'> {
  to: string
}

export interface NextFixture {
  needs: NeedSpec[]
  running: ActSpec[]
  finished: ActSpec[]
  finishedToday: FinishedTally | null
  spend: SpendFigures
  main: MainHealth
  builds: BuildSpec[]
}

const day = (back: number) => new Date(Date.parse('2026-10-17T12:10:00Z') - back * 86_400_000).toISOString().slice(0, 10)
const trend = (values: (number | null)[]) => values.map((usd, i) => ({ day: day(values.length - 1 - i), usd }))

export const NEXT_FIXTURES: Record<OverviewNextState, NextFixture> = {
  busy: {
    needs: [
      { id: 'n1', kind: 'question', agent: 'QA1', colorIndex: 2, title: 'Allow a 30-second cache on search results?', action: 'Answer', ago: 6, to: 'QA1 asks' },
      { id: 'n2', kind: 'review', agent: 'Builder', colorIndex: 0, title: 'Jobs list shows the next run', action: 'Review', ago: 48, to: 'the task' },
      { id: 'n3', kind: 'permission', agent: 'Builder', colorIndex: 0, title: 'Install the chart package in the web folder', action: 'Decide', ago: 95, to: 'the request' },
    ],
    running: [
      { id: 'r1', agent: 'Builder', colorIndex: 0, what: 'Wire the checkpoints tab to its route', outcome: 'running', ago: 4, to: 'the thread' },
      { id: 'r2', agent: 'Architect', colorIndex: 1, what: 'Draft the budgets change', outcome: 'running', ago: 17, to: 'the thread' },
    ],
    finished: [
      { id: 'f1', agent: 'Builder', colorIndex: 0, what: 'Checkpoints list keeps its filters', outcome: 'landed', ago: 38, usd: 1.84, to: 'the task' },
      { id: 'f2', agent: 'QA1', colorIndex: 2, what: 'Trace export keeps its headers', outcome: 'sent_back', ago: 71, usd: 0.62, to: 'the task' },
      { id: 'f3', agent: 'Builder', colorIndex: 0, what: 'Jobs list shows the next run', outcome: 'landed', ago: 140, usd: 2.31, to: 'the task' },
      { id: 'f4', agent: 'Architect', colorIndex: 1, what: 'Spec: leaner navigation', outcome: 'landed', ago: 210, usd: null, to: 'the task' },
      { id: 'f5', agent: 'QA1', colorIndex: 2, what: 'Nightly drift scan', outcome: 'failed', ago: 330, usd: 0.4, to: 'the run' },
    ],
    finishedToday: { landed: 3, sentBack: 1, failed: 1 },
    spend: {
      todayUsd: 14.02,
      periodUsd: 38.42,
      periodLabel: 'this week',
      budgetUsd: 60,
      trend: trend([6.2, 9.8, null, 14.6, 11.3, 12.9, 14.02]),
      unpricedTurns: 3,
    },
    main: { state: 'green', branch: 'master', heldLandings: 0, knownFailing: 2, detail: 'master passes its checks' },
    builds: [
      { id: 'b1', title: 'Leaner navigation', done: 4, total: 9, stage: 'Building task 5', needsYou: false, to: 'the build' },
      { id: 'b2', title: 'Profile pool editor', done: 7, total: 8, stage: 'Checking task 8', needsYou: false, to: 'the build' },
      { id: 'b3', title: 'Search results cache', done: 2, total: 5, stage: 'Waiting for your answer', needsYou: true, to: 'the build' },
    ],
  },
  quiet: {
    needs: [],
    running: [],
    finished: [
      { id: 'f1', agent: 'Builder', colorIndex: 0, what: 'Checkpoints tab wired to the route', outcome: 'landed', ago: 95, usd: 1.84, to: 'the task' },
      { id: 'f2', agent: 'Architect', colorIndex: 1, what: 'Spec: leaner navigation', outcome: 'landed', ago: 420, usd: 0.9, to: 'the task' },
    ],
    finishedToday: { landed: 2, sentBack: 0, failed: 0 },
    spend: { todayUsd: 3.1, periodUsd: 21.8, periodLabel: 'this week', budgetUsd: null, trend: trend([4.2, 3.8, 5.1, 2.4, 2.9, 3.4, 3.1]), unpricedTurns: 0 },
    main: { state: 'green', branch: 'master', heldLandings: 0, knownFailing: null, detail: 'master passes its checks' },
    builds: [],
  },
  trouble: {
    needs: [
      { id: 'n1', kind: 'main', agent: null, title: 'Three checks fail on master since the last landing', action: 'Look', ago: 22, to: 'the checks' },
      { id: 'n2', kind: 'merge', agent: 'QA1', colorIndex: 2, title: 'Trace export keeps its headers was approved but not merged', action: 'Try again', ago: 61, to: 'the task' },
      { id: 'n3', kind: 'stall', agent: 'Builder', colorIndex: 0, title: 'Profile pool editor has not moved for 40 minutes', action: 'Mend', ago: 40, to: 'the build' },
      { id: 'n4', kind: 'question', agent: 'Architect', colorIndex: 1, title: 'Should budgets reset weekly or monthly?', action: 'Answer', ago: 130, to: 'the thread' },
      { id: 'n5', kind: 'review', agent: 'Builder', colorIndex: 0, title: 'Checkpoints list keeps its filters', action: 'Review', ago: 190, to: 'the task' },
    ],
    running: [{ id: 'r1', agent: 'Builder', colorIndex: 0, what: 'Fix the failing checks on master', outcome: 'running', ago: 9, to: 'the thread' }],
    finished: [
      { id: 'f1', agent: 'QA1', colorIndex: 2, what: 'Trace export keeps its headers', outcome: 'landed', ago: 61, usd: 0.7, to: 'the task' },
      { id: 'f2', agent: 'Builder', colorIndex: 0, what: 'Jobs list shows the next run', outcome: 'failed', ago: 150, usd: 2.9, to: 'the run' },
      { id: 'f3', agent: 'Builder', colorIndex: 0, what: 'Checkpoints list keeps its filters', outcome: 'sent_back', ago: 190, usd: 1.4, to: 'the task' },
      { id: 'f4', agent: 'Architect', colorIndex: 1, what: 'Draft the budgets change', outcome: 'stopped', ago: 260, usd: null, to: 'the thread' },
    ],
    finishedToday: { landed: 1, sentBack: 1, failed: 1 },
    spend: { todayUsd: 19.6, periodUsd: 55.1, periodLabel: 'this week', budgetUsd: 60, trend: trend([6.2, 9.8, 14.6, 11.3, null, 12.9, 19.6]), unpricedTurns: 5 },
    main: { state: 'failing', branch: 'master', heldLandings: 1, knownFailing: 2, detail: 'Three checks fail on master' },
    builds: [{ id: 'b1', title: 'Profile pool editor', done: 3, total: 8, stage: 'Stalled', needsYou: true, to: 'the build' }],
  },
}