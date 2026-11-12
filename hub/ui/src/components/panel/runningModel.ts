import type { Job, LoopSummary } from '@/api/jobs'
import type { SpecBuild } from '@/api/spec'
import { describeCron, formatAgo, formatIn } from '@/lib/format'

/** The side panel's Running tab (roadmap `a-side-panel-worth-keeping-open-…`, slice `activity-tab`):
 *  every build, loop and scheduled job in one list, what each is doing now, and what waits on the
 *  operator first. Pure: the rows are derived here so the component only draws them. */

export type RunningKind = 'build' | 'loop' | 'job'

/** Where a row sits. The order of this list is the order of the groups on screen. */
export const RUNNING_PHASES = ['needs-you', 'working', 'between', 'scheduled', 'paused', 'finished', 'stopped'] as const
export type RunningPhase = (typeof RUNNING_PHASES)[number]

export const PHASE_LABEL: Record<RunningPhase, string> = {
  'needs-you': 'Needs you',
  working: 'Working now',
  between: 'Between steps',
  scheduled: 'Scheduled',
  paused: 'Paused',
  finished: 'Finished',
  stopped: 'Stopped early',
}

export type RunningFilter = 'now' | 'finished' | 'all'
export type RunningKindFilter = 'any' | RunningKind

export interface RunningWorker {
  agent: string
  /** "building", "checking", "holding", "next" — what the agent is to the task, in words. */
  doing: string
  task: string
}

export interface RunningItem {
  id: string
  kind: RunningKind
  title: string
  phase: RunningPhase
  /** What waits on the operator, in one sentence. Only on a `needs-you` row. */
  attention: { kind: 'question' | 'stall'; text: string } | null
  /** The one line under the title saying what is happening, when nobody is working a task. */
  status: string
  workers: RunningWorker[]
  progress: { done: number; total: number } | null
  /** The time that matters for this row's phase, already in words: "next in 4m", "started 2h ago". */
  when: string
  spentUsd: number | null
}

/** A build as the panel receives it: the Hub's record, the document it builds, and its loop. */
export interface RunningBuildInput {
  build: SpecBuild
  number: number
  documentTitle: string
  loop: LoopSummary | null
  nextRun?: string | null
}

const DONE_STATUSES = new Set(['approved', 'rejected'])

function progressOf(loop: LoopSummary | null): RunningItem['progress'] {
  if (!loop) return null
  const total = Object.values(loop.queue).reduce((n, v) => n + v, 0)
  if (total === 0) return null
  const done = Object.entries(loop.queue).reduce((n, [status, v]) => n + (DONE_STATUSES.has(status) ? v : 0), 0)
  return { done, total }
}

function doingOf(status: string, capacity: string | undefined): string {
  if (capacity === 'next') return 'is next on'
  if (capacity === 'held') return 'is holding'
  if (capacity === 'assigned') return 'is waiting on'
  if (status === 'under_review' || status === 'completed') return 'is checking'
  return 'is building'
}

function workersOf(loop: LoopSummary | null): RunningWorker[] {
  return (loop?.current_tasks ?? [])
    .filter((t) => t.agent)
    .map((t) => ({ agent: t.agent!, doing: doingOf(t.status, t.agent_capacity), task: t.title }))
}

function attentionOf(loop: LoopSummary | null): RunningItem['attention'] {
  if (!loop) return null
  if (loop.open_questions > 0) {
    const text = loop.open_questions === 1 ? 'A question is waiting for your answer' : `${loop.open_questions} questions are waiting for your answer`
    return { kind: 'question', text }
  }
  if (loop.stall_reason) return { kind: 'stall', text: loop.stall_reason }
  return null
}

function loopPhase(loop: LoopSummary, attention: RunningItem['attention'], workers: RunningWorker[]): RunningPhase {
  if (loop.ending_state === 'completed') return 'finished'
  if (loop.ending_state === 'stopped') return 'stopped'
  if (attention) return 'needs-you'
  if (loop.firing_active || workers.some((w) => w.doing === 'is building' || w.doing === 'is checking')) return 'working'
  return 'between'
}

function ago(value: string, now: Date): string {
  const short = formatAgo(value, now)
  return short === 'now' ? 'just now' : /^\d+[mhdw]$/.test(short) ? `${short} ago` : `on ${short}`
}

function whenOf(phase: RunningPhase, now: Date, times: { started?: string | null; ended?: string | null; next?: string | null }): string {
  if ((phase === 'finished' || phase === 'stopped') && times.ended) return `ended ${ago(times.ended, now)}`
  if ((phase === 'between' || phase === 'scheduled') && times.next) return `next ${formatIn(times.next, now).replace(/^now$/, 'any moment')}`
  if (times.started) return `started ${ago(times.started, now)}`
  return ''
}

export function buildItem(input: RunningBuildInput, now: Date): RunningItem {
  const { build, loop } = input
  const workers = workersOf(loop)
  const attention = build.state === 'running' ? attentionOf(loop) : null
  const phase: RunningPhase =
    build.state === 'finished' ? 'finished' : build.state === 'stopped' ? 'stopped' : loop ? loopPhase(loop, attention, workers) : 'working'
  const status =
    phase === 'stopped'
      ? build.stop_reason ?? 'Stopped before its tasks were done'
      : phase === 'finished'
        ? 'Every task done'
        : phase === 'between'
          ? 'Waiting for its next step'
          : ''
  return {
    id: build.id,
    kind: 'build',
    title: input.documentTitle,
    phase,
    attention: phase === 'needs-you' ? attention : null,
    status,
    workers: phase === 'finished' || phase === 'stopped' ? [] : workers,
    progress: progressOf(loop),
    when: whenOf(phase, now, { started: build.created_at, ended: build.stopped_at, next: input.nextRun }),
    spentUsd: build.spent_usd,
  }
}

export function loopItem(loop: LoopSummary, now: Date, times: { started?: string | null; next?: string | null } = {}): RunningItem {
  const workers = workersOf(loop)
  const attention = attentionOf(loop)
  const phase = loopPhase(loop, attention, workers)
  return {
    id: loop.id,
    kind: 'loop',
    title: loop.label,
    phase,
    attention: phase === 'needs-you' ? attention : null,
    status: phase === 'stopped' ? loop.stop_reason ?? 'Stopped before its queue was empty' : phase === 'finished' ? 'Its queue is empty' : phase === 'between' ? 'Waiting for its next firing' : '',
    workers: phase === 'finished' || phase === 'stopped' ? [] : workers,
    progress: progressOf(loop),
    when: whenOf(phase, now, { started: times.started, ended: loop.stopped_at, next: times.next }),
    spentUsd: null,
  }
}

export function jobItem(job: Job, now: Date): RunningItem {
  const current = job.history?.find((run) => run.status === 'in_progress') ?? null
  const running = current !== null
  const phase: RunningPhase = job.archived_at ? 'finished' : running ? 'working' : job.enabled ? 'scheduled' : 'paused'
  // describeCron returns an expression it cannot say as-is; a raw cron string never reaches the screen.
  const described = describeCron(job.cron)
  const schedule = described === job.cron ? 'On its own schedule' : described
  return {
    id: job.id,
    kind: 'job',
    title: job.name,
    phase,
    attention: null,
    status: phase === 'paused' ? `${schedule}, paused` : schedule,
    workers: running ? [{ agent: job.agent, doing: 'is running', task: 'this job' }] : [],
    progress: null,
    when:
      phase === 'paused' && job.last_run
        ? `last ran ${ago(job.last_run, now)}`
        : whenOf(phase, now, { started: current?.fired_at ?? job.last_run, ended: job.archived_at, next: job.next_run }),
    spentUsd: null,
  }
}

/** Builds, loops that are not a build's, and jobs that are not a loop's: each piece of work once. */
export function runningItems(input: { builds: RunningBuildInput[]; loops: LoopSummary[]; jobs: Job[]; now: Date }): RunningItem[] {
  const buildLoops = new Set(input.builds.map((b) => b.build.loop_id).filter(Boolean))
  const loopJobs = new Map(input.jobs.filter((j) => j.loop).map((j) => [j.loop!.id, j]))
  return [
    ...input.builds.map((b) => buildItem(b, input.now)),
    ...input.loops
      .filter((l) => !buildLoops.has(l.id))
      .map((l) => loopItem(l, input.now, { started: loopJobs.get(l.id)?.created_at, next: loopJobs.get(l.id)?.next_run })),
    ...input.jobs.filter((j) => !j.loop).map((j) => jobItem(j, input.now)),
  ]
}

const ENDED: ReadonlySet<RunningPhase> = new Set(['finished', 'stopped'])

export function matchesFilter(item: RunningItem, filter: RunningFilter, kind: RunningKindFilter): boolean {
  if (kind !== 'any' && item.kind !== kind) return false
  if (filter === 'now') return !ENDED.has(item.phase)
  if (filter === 'finished') return ENDED.has(item.phase)
  return true
}

/** The rows in their groups, in `RUNNING_PHASES` order; empty groups are left out. */
export function groupItems(items: RunningItem[]): Array<{ phase: RunningPhase; items: RunningItem[] }> {
  return RUNNING_PHASES.map((phase) => ({ phase, items: items.filter((i) => i.phase === phase) })).filter((g) => g.items.length > 0)
}

/** The tab's one summary line: "1 needs you · 2 working · 3 scheduled". */
export function summaryLine(items: RunningItem[]): string {
  const count = (p: RunningPhase[]) => items.filter((i) => p.includes(i.phase)).length
  const parts = [
    [count(['needs-you']), 'needs you'],
    [count(['working']), 'working'],
    [count(['between', 'scheduled']), 'waiting'],
  ] as const
  const said = parts.filter(([n]) => n > 0).map(([n, what]) => `${n} ${what}`)
  return said.length ? said.join(' · ') : 'Nothing is running'
}
