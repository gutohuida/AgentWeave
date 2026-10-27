import type { WorkGroup, WorkRow, WorkTally } from '@/api/stats'

/** The night of 2026-10-26/27 on slice B, as the work tally reads it: the figures the operator had to
 *  get with SQL (mending 42 runs $15.86, building 9 runs $14.66, reviewing 11 runs $11.28, 10 check
 *  runs of which 4 failed, 3 reviews beside a failing check costing $4.39). Slice D had not shipped, so
 *  all of it is "before builds" and has no level recorded. */
const M = 1_000_000

function row(over: Partial<WorkRow> = {}): WorkRow {
  return {
    runs: { building: 0, reviewing: 0, leading: 0, mending: 0, other: 0, total: 0 },
    cost_micros: { building: null, reviewing: null, leading: null, mending: null, other: null, total: null },
    run_seconds: { building: 0, reviewing: 0, leading: 0, mending: 0, other: 0, total: 0 },
    unpriced: 0,
    turns: 0,
    tokens: null,
    ai_nano_aiu: null,
    premium_requests: null,
    wall: { building: 0, reviewing: 0, checks: 0, held: 0, review: 0, waiting: 0, total: 0 },
    checks: { runs: 0, passed: 0, failed: 0, seconds: 0 },
    send_backs: { made: 0, received: 0 },
    pieces: { accepted: 0, rejected: 0, held: 0, awaiting: 0 },
    beside_failing: { count: 0, cost_micros: null, run_seconds: 0 },
    ...over,
  }
}

const NIGHT: WorkRow = row({
  runs: { building: 9, reviewing: 11, leading: 0, mending: 42, other: 0, total: 62 },
  cost_micros: { building: 14.66 * M, reviewing: 11.28 * M, leading: null, mending: 15.86 * M, other: null, total: 41.8 * M },
  run_seconds: { building: 2 * 3600 + 14 * 60, reviewing: 3600 + 5 * 60, leading: 0, mending: 3 * 3600 + 20 * 60, other: 0, total: 6 * 3600 + 39 * 60 },
  turns: 62,
  tokens: 9_400_000,
  checks: { runs: 10, passed: 6, failed: 4, seconds: 108 * 60 },
  send_backs: { made: 4, received: 4 },
  pieces: { accepted: 11, rejected: 4, held: 3, awaiting: 0 },
  beside_failing: { count: 3, cost_micros: 4.39 * M, run_seconds: 22 * 60 },
})

const SLICE_B: WorkGroup = {
  key: 'spdoc-484b096e0803',
  label: 'Slice B: the spec page needs a build',
  path: 'spec/changes/slice-b/spec.json',
  row: NIGHT,
  builds: [],
  before_builds: NIGHT,
}

function by(key: string | null, label: string, over: Partial<WorkRow>): WorkGroup {
  return { key, label, row: row(over) }
}

export const NIGHT_TALLY: WorkTally = {
  since: null,
  total: NIGHT,
  workers: row({ cost_micros: { building: null, reviewing: null, leading: null, mending: null, other: null, total: 0.4 * M }, tokens: 52_000 }),
  project: NIGHT,
  builds: {},
  groups: {
    spec: [SLICE_B, { key: null, label: 'not from a spec', row: row(), builds: [], before_builds: null }],
    agent: [
      by('Mender', 'Mender', {
        runs: { building: 0, reviewing: 0, leading: 0, mending: 42, other: 0, total: 42 },
        cost_micros: { building: null, reviewing: null, leading: null, mending: 15.86 * M, other: null, total: 15.86 * M },
        run_seconds: { building: 0, reviewing: 0, leading: 0, mending: 3 * 3600 + 20 * 60, other: 0, total: 3 * 3600 + 20 * 60 },
        turns: 42,
      }),
      by('Developer', 'Developer', {
        runs: { building: 9, reviewing: 0, leading: 0, mending: 0, other: 0, total: 9 },
        cost_micros: { building: 14.66 * M, reviewing: null, leading: null, mending: null, other: null, total: 14.66 * M },
        run_seconds: { building: 2 * 3600 + 14 * 60, reviewing: 0, leading: 0, mending: 0, other: 0, total: 2 * 3600 + 14 * 60 },
        turns: 9,
        send_backs: { made: 0, received: 4 },
      }),
      by('QA', 'QA', {
        runs: { building: 0, reviewing: 11, leading: 0, mending: 0, other: 0, total: 11 },
        cost_micros: { building: null, reviewing: 11.28 * M, leading: null, mending: null, other: null, total: 11.28 * M },
        run_seconds: { building: 0, reviewing: 3600 + 5 * 60, leading: 0, mending: 0, other: 0, total: 3600 + 5 * 60 },
        turns: 11,
        send_backs: { made: 4, received: 0 },
        beside_failing: { count: 3, cost_micros: 4.39 * M, run_seconds: 22 * 60 },
      }),
      by(null, 'checks and wall time', { checks: { runs: 10, passed: 6, failed: 4, seconds: 108 * 60 } }),
    ],
    model: [
      by('claude-opus-5', 'claude-opus-5', {
        runs: { building: 0, reviewing: 11, leading: 0, mending: 42, other: 0, total: 53 },
        cost_micros: { building: null, reviewing: 11.28 * M, leading: null, mending: 15.86 * M, other: null, total: 27.14 * M },
        turns: 53,
      }),
      by('claude-sonnet-5', 'claude-sonnet-5', {
        runs: { building: 9, reviewing: 0, leading: 0, mending: 0, other: 0, total: 9 },
        cost_micros: { building: 14.66 * M, reviewing: null, leading: null, mending: null, other: null, total: 14.66 * M },
        turns: 9,
      }),
    ],
    level: [by(null, 'no level recorded', NIGHT)],
  },
}
