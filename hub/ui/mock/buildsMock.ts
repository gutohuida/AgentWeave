import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { ProjectBuildRow } from '@/api/projectBuilds'
import type { TraceDetail } from '@/api/traces'
import {
  addressQuery,
  buildTotals,
  costTotal,
  parseAddress,
  runSeconds,
  type BuildAddress,
  type BuildRead,
  type BuildRunRead,
  type RunRole,
} from '@/components/builds/buildViewModel'
import type { BuildView as SpecBuildView, TaskStatus } from '@/components/spec/page/model'
import buildsJson from './fixtures/builds.json'
import { PROJECT_ID } from './fixtures'

/** The build view's fixtures: real builds of this repository, recorded read-only from the
 *  operator's Hub by `py -3.11 mock/record_builds.py <db> <project>` in the shape the build read
 *  route is to return (`BuildRead`). */
export const RECORDED_BUILDS = buildsJson as unknown as BuildRead[]

export const DEFAULT_BUILD = 'build-04e780a89c1c'

/** The states the recording lacks, chosen with `?state=` (`// mock state`, each marked below). */
export const BUILD_MOCK_STATES = [
  { value: 'recorded', label: 'As recorded' },
  { value: 'live', label: 'Running: a task working, one in review, one stalled' },
  { value: 'unpriced', label: 'One task with every run unpriced' },
  { value: 'all-unpriced', label: 'Every run unpriced' },
  { value: 'empty', label: 'No tasks yet' },
  { value: 'loading', label: 'Loading' },
  { value: 'error', label: 'Could not load' },
  { value: 'stale', label: 'Refresh failed: stale' },
] as const
export type BuildMockState = (typeof BUILD_MOCK_STATES)[number]['value']

function minutesBefore(iso: string, minutes: number): string {
  return new Date(new Date(iso).getTime() - minutes * 60_000).toISOString()
}

/** The recorded build, changed by a mock state. Never edits the fixture itself. */
export function buildFor(id: string, state: BuildMockState): BuildRead | null {
  const recorded = RECORDED_BUILDS.find((b) => b.build.id === id) ?? RECORDED_BUILDS.find((b) => b.build.id === DEFAULT_BUILD) ?? RECORDED_BUILDS[0]
  if (!recorded) return null
  const read: BuildRead = structuredClone(recorded)
  const unpriced = (r: BuildRunRead): BuildRunRead => ({ ...r, cost_state: r.cost_state === 'running' ? 'running' : 'unpriced', cost_usd_micros: null, tokens: null })
  if (state === 'empty') {
    // mock state: a build whose tasks have not been filed yet.
    return { ...read, build: { ...read.build, state: 'running', stopped_at: null }, tasks: [], build_runs: [] }
  }
  if (state === 'all-unpriced') {
    // mock state: no run of the build reported a price.
    read.tasks = read.tasks.map((t) => ({ ...t, runs: t.runs.map(unpriced) }))
    read.build_runs = read.build_runs.map(unpriced)
  }
  if (state === 'unpriced' && read.tasks[1]) {
    // mock state: the second task's runs all went unpriced; the others keep their recorded prices.
    read.tasks[1] = { ...read.tasks[1], runs: read.tasks[1].runs.map(unpriced) }
  }
  if (state === 'live') {
    // mock state: the recording's running build had already approved every task. Here the last
    // task is being built now, the fourth waits for review with one piece of evidence awaiting,
    // and the third is stalled (its reason is the real stall's, moved onto it).
    const asOf = read.as_of
    read.build = { ...read.build, state: 'running', stopped_at: null }
    const n = read.tasks.length
    const last = read.tasks[n - 1]
    if (last) {
      const builder = last.builder ?? 'DeveloperOpus'
      read.tasks[n - 1] = {
        ...last,
        status: 'in_progress',
        last_change_at: minutesBefore(asOf, 4),
        requirements: last.requirements.map((r) => ({ ...r, evidence: 'missing' })),
        runs: [
          ...last.runs.slice(0, 2),
          {
            id: 'run-mock-live',
            role: 'build',
            agent: builder,
            model: 'claude-sonnet-5',
            conversation_id: 'conv-mock-live',
            started_at: minutesBefore(asOf, 4),
            ended_at: null,
            status: 'running',
            cost_state: 'running',
            cost_usd_micros: null,
            tokens: null,
            moves: [{ from: 'revision_needed', to: 'in_progress' }],
            mend: null,
          },
        ],
      }
    }
    const fourth = read.tasks[3]
    if (fourth) {
      read.tasks[3] = {
        ...fourth,
        status: 'under_review',
        checker: fourth.checker ?? 'QA',
        last_change_at: minutesBefore(asOf, 11),
        requirements: fourth.requirements.map((r, i) => (i === 0 ? { ...r, evidence: 'awaiting' } : r)),
        runs: fourth.runs.slice(0, 1),
      }
    }
    const third = read.tasks[2]
    if (third) {
      read.tasks[2] = {
        ...third,
        status: 'under_review',
        last_change_at: minutesBefore(asOf, 26),
        needs_operator: {
          kind: 'stalled',
          text: `QA2 holds ${third.ref ?? 'this task'}, and delivering its turn was refused: Claude Code's sign-in has expired and cannot be renewed. Run \`claude auth login\` in a terminal, then withdraw that input so the next firing briefs QA2 again.`,
        },
      }
    }
  }
  return read
}

/** The moment the recorded build is read at: when it was recorded, so "updated", "4m" and a running
 *  run's duration read as they did then (the mock's MOCK_NOW belongs to the October fixtures). */
export function nowFor(read: BuildRead | null): Date {
  return read ? new Date(read.as_of) : new Date()
}

/** Agent colours: the recorded agents are this repository's, not the Terra replica's the mock's
 *  agents fixture holds, so each gets a palette slot by first appearance (`// mock state`; the app
 *  reads `color_index` from the agents list). */
export function colorIndexer(reads: BuildRead[]): (agent: string) => number {
  const order: string[] = []
  for (const read of reads)
    for (const t of read.tasks) for (const name of [t.builder, t.checker, ...t.runs.map((r) => r.agent)]) if (name && !order.includes(name)) order.push(name)
  return (agent) => {
    const i = order.indexOf(agent)
    return i < 0 ? 0 : i % 8
  }
}

/** The address part of the hash (`#build/<id>?task=…&run=…&filter=…&state=…`), kept in step with
 *  the browser's history so Back closes the trace before it leaves the build. */
export function useBuildHash(): { buildId: string | null; address: BuildAddress; state: BuildMockState; setAddress: (a: BuildAddress) => void; setState: (s: BuildMockState) => void } {
  const read = () => {
    const [path, query = ''] = window.location.hash.replace(/^#/, '').split('?')
    const id = decodeURIComponent(path!.split('/')[1] ?? '') || null
    const q = new URLSearchParams(query)
    const state = (BUILD_MOCK_STATES.find((s) => s.value === q.get('state'))?.value ?? 'recorded') as BuildMockState
    return { buildId: id, address: parseAddress(query), state }
  }
  const [value, setValue] = React.useState(read)
  React.useEffect(() => {
    const on = () => setValue(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  // Opening a trace adds a history entry; closing it goes back over that entry, so Back closes the
  // trace before it leaves the build and closing never leaves an entry that reopens it.
  const pushedRun = React.useRef(false)
  const write = (address: BuildAddress, state: BuildMockState) => {
    if (!address.run && value.address.run && pushedRun.current && address.task === value.address.task && address.filter === value.address.filter) {
      pushedRun.current = false
      window.history.back()
      return
    }
    pushedRun.current = Boolean(address.run && !value.address.run)
    const q = addressQuery(address)
    const s = state === 'recorded' ? '' : `state=${state}`
    const query = [q, s].filter(Boolean).join('&')
    window.location.hash = `build/${value.buildId ?? DEFAULT_BUILD}${query ? `?${query}` : ''}`
  }
  return {
    ...value,
    setAddress: (address) => write(address, value.state),
    setState: (state) => write({ ...value.address, run: null }, state),
  }
}

export function buildHref(buildId: string, task?: string, state?: BuildMockState): string {
  const q = [task ? `task=${encodeURIComponent(task)}` : '', state && state !== 'recorded' ? `state=${state}` : ''].filter(Boolean).join('&')
  return `#build/${buildId}${q ? `?${q}` : ''}`
}

/** Seeds the trace drawer's query (`useRunTrace`) with the recorded whole traces, loaded on demand
 *  (the file is large). A run with no recorded trace shows the drawer's own "no trace" answer. */
export function useSeedRunTraces(read: BuildRead | null): void {
  const client = useQueryClient()
  React.useEffect(() => {
    if (!read) return
    let live = true
    void import('./fixtures/builds_traces.json').then((mod) => {
      if (!live) return
      const traces = (mod.default ?? mod) as unknown as Record<string, TraceDetail>
      for (const run of [...read.tasks.flatMap((t) => t.runs), ...read.build_runs]) {
        const key = ['project', PROJECT_ID, 'traces', 'by-run', run.id, 0]
        if (client.getQueryData(key) === undefined) client.setQueryData(key, traces[run.id] ?? null)
      }
    })
    return () => {
      live = false
    }
  }, [client, read])
}

const ROLE_COST: Record<RunRole, 'build' | 'review' | 'lead' | 'mend'> = { build: 'build', review: 'review', lead: 'lead', mender: 'mend' }

/** The spec page's build card for a recorded build, so its meters and the summary under them come
 *  from one build. // mock state: the card's wall-time split and check figures belong to the
 *  figures route, which the recording does not hold: building and reviewing are the runs' working
 *  time here, and checks are left empty. */
export function specCardOf(read: BuildRead, number: number): SpecBuildView {
  const now = nowFor(read)
  const runs = [...read.tasks.flatMap((t) => t.runs), ...read.build_runs]
  const byRole = (role: RunRole) => runs.filter((r) => r.role === role)
  const cost = (role: RunRole) => {
    const t = costTotal(byRole(role))
    return t.priced ? t.usd : byRole(role).length && t.unpriced ? null : 0
  }
  const secs = (role: RunRole) => byRole(role).reduce((n, r) => n + runSeconds(r, now), 0)
  const tasks = {} as Record<TaskStatus, number>
  for (const t of read.tasks) tasks[t.status] = (tasks[t.status] ?? 0) + 1
  const totals = buildTotals(read, now)
  const costs = { build: 0 as number | null, review: 0 as number | null, lead: 0 as number | null, mend: 0 as number | null }
  for (const role of ['build', 'review', 'lead', 'mender'] as RunRole[]) costs[ROLE_COST[role]] = cost(role)
  return {
    id: read.build.id,
    number,
    driver: 'flow',
    level: (read.build.level as SpecBuildView['level']) ?? 'reviewed',
    builders: [...new Set(byRole('build').map((r) => r.agent))],
    reviewers: [...new Set(byRole('review').map((r) => r.agent))],
    lead: null,
    running: read.build.state === 'running',
    ended: read.build.state === 'stopped' ? 'stopped' : read.build.state === 'finished' ? 'finished' : undefined,
    startedAt: read.build.created_at,
    finishedAt: read.build.stopped_at,
    landsOn: 'master',
    caught: [],
    openFixTasks: [],
    fixHeldReason: null,
    budget: null,
    tasks,
    time: { building: secs('build'), reviewing: secs('review'), checks: 0, held: 0, review: 0, waiting: 0 },
    cost: costs,
    runs: totals.runs,
    unpriced: totals.cost.unpriced,
    checks: { runs: 0, passed: 0, failed: 0, seconds: 0 },
  }
}

/** The Running tab's row for a recorded build (`GET /project/builds`), made from the same read so
 *  the row and its summary agree. // mock state: the recording does not hold the route's row; and
 *  on a screen whose clock is the October fixtures' (`clock`), its times keep their age. */
export function projectRowOf(read: BuildRead, clock?: Date): ProjectBuildRow {
  const totals = buildTotals(read, nowFor(read))
  const shift = clock ? clock.getTime() - nowFor(read).getTime() : 0
  const at = (iso: string | null) => (iso && shift ? new Date(new Date(iso).getTime() + shift).toISOString() : iso)
  return {
    id: read.build.id,
    document_id: read.build.document_id,
    document_title: read.build.document_title,
    state: read.build.state,
    driver: 'flow',
    level: 'reviewed',
    lead: null,
    loop_id: null,
    loop: null,
    tasks_total: totals.tasks,
    tasks_done: totals.approved,
    tasks_landing: 0,
    landings: [],
    spent_usd: totals.cost.priced ? totals.cost.usd : null,
    unpriced_turns: totals.cost.unpriced,
    stop_reason: read.build.stop_reason,
    created_at: at(read.build.created_at),
    stopped_at: at(read.build.stopped_at),
    finished_at: at(read.build.stopped_at),
    needs_operator: read.build.needs_operator ?? null,
    attention_dismissed: read.build.attention_dismissed ?? false,
    open_questions: 0,
    question: null,
  }
}
