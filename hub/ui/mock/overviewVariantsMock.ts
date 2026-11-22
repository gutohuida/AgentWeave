// mock state for the Briefing and Team-lanes Overview variants. They show the same project as the
// dashboard variant, so everything they share comes from NEXT_FIXTURES; only what those two designs
// need beyond it is written here: when the operator last looked, and each profile's lane.
// Times are minutes before the mock clock.
import type { LaneStatus } from '@/components/overview/overviewLanesModel'
import type { ActivityOutcome } from '@/components/overview/OverviewDashboard'
import type { OverviewNextState } from './overviewNextMock'

export type OverviewVariantState = OverviewNextState

/** Minutes since the operator last looked at the project; null = the Hub has no record (a first visit). */
export const LAST_SEEN_AGO: Record<OverviewVariantState, number | null> = { busy: 120, quiet: 500, trouble: 200 }

export interface LaneSpec {
  id: string
  name: string
  colorIndex: number
  status: LaneStatus
  doing: { what: string; ago: number } | null
  last: { what: string; outcome: ActivityOutcome; ago: number } | null
  /** Titles of what this profile has open with the operator. */
  asks: string[]
  /** Today, in dollars; null = turns the Hub could not price. */
  spendToday: number | null
}

export const LANE_FIXTURES: Record<OverviewVariantState, LaneSpec[]> = {
  busy: [
    {
      id: 'Builder', name: 'Builder', colorIndex: 0, status: 'working',
      doing: { what: 'Wire the checkpoints tab to its route', ago: 4 },
      last: { what: 'Checkpoints list keeps its filters', outcome: 'landed', ago: 38 },
      asks: ['Jobs list shows the next run', 'Install the chart package in the web folder'], spendToday: 8.4,
    },
    {
      id: 'QA1', name: 'QA1', colorIndex: 2, status: 'waiting',
      doing: { what: 'Allow a 30-second cache on search results?', ago: 6 },
      last: { what: 'Trace export keeps its headers', outcome: 'sent_back', ago: 71 },
      asks: ['Allow a 30-second cache on search results?'], spendToday: 1.72,
    },
    {
      id: 'Architect', name: 'Architect', colorIndex: 1, status: 'working',
      doing: { what: 'Draft the budgets change', ago: 17 },
      last: { what: 'Spec: leaner navigation', outcome: 'landed', ago: 210 },
      asks: [], spendToday: null,
    },
    { id: 'Docs', name: 'Docs', colorIndex: 4, status: 'idle', doing: null, last: null, asks: [], spendToday: 0 },
  ],
  quiet: [
    { id: 'Builder', name: 'Builder', colorIndex: 0, status: 'idle', doing: null, last: { what: 'Checkpoints tab wired to the route', outcome: 'landed', ago: 95 }, asks: [], spendToday: 1.84 },
    { id: 'Architect', name: 'Architect', colorIndex: 1, status: 'idle', doing: null, last: { what: 'Spec: leaner navigation', outcome: 'landed', ago: 420 }, asks: [], spendToday: 1.26 },
    { id: 'QA1', name: 'QA1', colorIndex: 2, status: 'idle', doing: null, last: null, asks: [], spendToday: 0 },
    { id: 'Docs', name: 'Docs', colorIndex: 4, status: 'idle', doing: null, last: null, asks: [], spendToday: 0 },
  ],
  trouble: [
    {
      id: 'Builder', name: 'Builder', colorIndex: 0, status: 'stalled',
      doing: { what: 'Profile pool editor has not moved for 40 minutes', ago: 40 },
      last: { what: 'Jobs list shows the next run', outcome: 'failed', ago: 150 },
      asks: ['Profile pool editor has not moved for 40 minutes', 'Checkpoints list keeps its filters'], spendToday: 11.3,
    },
    {
      id: 'QA1', name: 'QA1', colorIndex: 2, status: 'waiting',
      doing: { what: 'Trace export keeps its headers is approved but not merged', ago: 61 },
      last: { what: 'Trace export keeps its headers', outcome: 'landed', ago: 61 },
      asks: ['Trace export keeps its headers was approved but not merged'], spendToday: 0.7,
    },
    {
      id: 'Architect', name: 'Architect', colorIndex: 1, status: 'waiting',
      doing: { what: 'Should budgets reset weekly or monthly?', ago: 130 },
      last: { what: 'Draft the budgets change', outcome: 'stopped', ago: 260 },
      asks: ['Should budgets reset weekly or monthly?'], spendToday: null,
    },
    { id: 'Docs', name: 'Docs', colorIndex: 4, status: 'idle', doing: null, last: null, asks: [], spendToday: 0 },
  ],
}