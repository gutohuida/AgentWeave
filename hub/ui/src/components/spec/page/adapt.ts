/** From the Hub's routes to the redesigned page's view model (spec `the-spec-page-redesigned`).
 *
 *  The components in this folder never see a route payload (`model.ts`); this file is the one place
 *  that turns what the Hub answers into what they draw: the document read, its coverage rows, its
 *  tasks, its builds and the figures behind them, and the document list. Pure functions, so each
 *  is tested against the shape the route returns. */
import type { BuildFigures } from '@/api/buildFigures'
import type { CoverageEntry, SpecBlockingFinding, SpecBuild, SpecDocumentRecord, SpecEntry } from '@/api/spec'
import type { Task } from '@/api/tasks'
import {
  type BuildView,
  type CheckFinding,
  type DocState,
  type EvidenceState,
  type SpecDocumentView,
  type SpecKind,
  type SpecListEntry,
  type SpecPhase,
  type SpecTaskView,
  type TaskStatus,
  shownOf,
} from './model'

// ── The document's structure ────────────────────────────────────────────

/** The structure the Hub keeps for a document. The read returns it inside the rendered page. */
export interface SpecPayload {
  title?: string
  kind?: string
  summary?: string
  problem?: string
  design?: string
  scope?: { in_scope?: string[]; non_goals?: string[] }
  requirements?: Array<{ key: string; modal: string; statement: string; rationale?: string | null }>
  acceptance_criteria?: Array<{ key: string; requirement: string; given: string; when: string; then: string; how_to_check?: string | null }>
  tasks?: Array<{ key: string; title?: string; description?: string; depends_on?: string[]; requirements?: string[] }>
  open_questions?: Array<{ question: string; resolved?: boolean }>
  slices?: Array<{ key: string; title?: string; intent?: string; done?: string; builds_after?: string[] }>
  algorithms?: Array<{ name: string; steps?: string[] }>
  /** `{ requirements: { key: 'FR-n' } }`: the identifiers the Hub minted. */
  aw_identity?: { requirements?: Record<string, string> }
}

/** The payload kept in the page's `aw-spec-payload` block, or null when there is none (the
 *  document is not a structured one: the overview, a file found on disk). */
export function parsePayload(content: string): SpecPayload | null {
  const match = /<script[^>]*id="aw-spec-payload"[^>]*>([\s\S]*?)<\/script>/.exec(content)
  if (!match) return null
  try {
    return JSON.parse(match[1]!) as SpecPayload
  } catch {
    return null
  }
}

const KINDS: SpecKind[] = ['change-spec', 'roadmap', 'capability', 'baseline', 'system-map']
export function kindOf(kind: string | null | undefined): SpecKind {
  return KINDS.includes(kind as SpecKind) ? (kind as SpecKind) : 'baseline'
}

// ── Evidence ────────────────────────────────────────────────────────────

/** The state a requirement's coverage row means to the operator. A piece a send-back held is its
 *  own state: not rejected (nobody named it failing), not accepted, and approval waits for it. */
export function evidenceOf(entry: CoverageEntry | undefined): EvidenceState {
  if (!entry) return 'not_started'
  switch (entry.state) {
    case 'verified':
      return 'verified'
    case 'evidence_awaiting_review':
    case 'amendment_unreviewed':
      return 'awaiting'
    case 'rejected':
      return 'rejected'
    case 'in_progress':
      return entry.reason?.includes('held evidence only') ? 'held' : 'in_progress'
    case 'stale':
    case 'drifting':
      return 'in_progress'
    default:
      return 'not_started'
  }
}

// ── Tasks ───────────────────────────────────────────────────────────────

const TASK_STATUSES: TaskStatus[] = ['pending', 'assigned', 'in_progress', 'completed', 'under_review', 'revision_needed', 'approved', 'rejected']

/** A task's status as the page names it. A task parked on a question is still being built. */
export function taskStatusOf(status: string | undefined): TaskStatus | null {
  if (!status) return null
  if (TASK_STATUSES.includes(status as TaskStatus)) return status as TaskStatus
  return status === 'blocked' ? 'in_progress' : 'pending'
}

export function countTasks(tasks: Task[]): Record<TaskStatus, number> {
  const counts = Object.fromEntries(TASK_STATUSES.map((s) => [s, 0])) as Record<TaskStatus, number>
  for (const task of tasks) {
    const status = taskStatusOf(task.status)
    if (status) counts[status] += 1
  }
  return counts
}

// ── The document ────────────────────────────────────────────────────────

export function stateOf(phase: SpecDocumentRecord['phase'], building: boolean, checkedClean: boolean): DocState {
  if (phase === 'exploring') return checkedClean ? 'ready' : 'writing'
  if (phase === 'archived') return 'archived'
  return building ? 'building' : 'approved'
}

const PHASES: SpecPhase[] = ['exploring', 'proposed', 'approved', 'archived', 'current']

export interface DocumentInputs {
  record: SpecDocumentRecord
  payload: SpecPayload
  updatedAt: string
  coverage: CoverageEntry[]
  tasks: Task[]
  builds: SpecBuild[]
  entries: SpecListEntry[]
  checkedClean: boolean
  /** The fold dialog is the document's next action. */
  foldReady?: boolean
  /** `{slice key: path}` of the change documents that name a roadmap's slices. */
  sliceDocuments?: Record<string, string>
}

export function documentView(input: DocumentInputs): SpecDocumentView {
  const { record, payload, coverage, tasks, builds, entries } = input
  const requirements = payload.requirements ?? []
  const identifiers = payload.aw_identity?.requirements ?? {}
  const identifierOf = (key: string) => identifiers[key] ?? `FR-${requirements.findIndex((r) => r.key === key) + 1}`
  const byTaskKey = new Map(tasks.filter((t) => t.spec_task_key).map((t) => [t.spec_task_key!, t]))
  const planned = payload.tasks ?? []
  const building = builds.some((b) => b.state === 'running')
  return {
    id: record.id,
    path: record.path,
    title: record.title || payload.title || record.path,
    kind: kindOf(record.kind),
    phase: PHASES.includes(record.phase as SpecPhase) ? (record.phase as SpecPhase) : 'approved',
    state: stateOf(record.phase, building, input.checkedClean),
    shown: shownOf(stateOf(record.phase, building, input.checkedClean), record.display_phase),
    summary: payload.summary ?? '',
    problem: payload.problem ?? '',
    inScope: payload.scope?.in_scope ?? [],
    nonGoals: payload.scope?.non_goals ?? [],
    design: payload.design ?? '',
    requirements: requirements.map((r) => {
      const identifier = identifierOf(r.key)
      return {
        identifier,
        key: r.key,
        modal: r.modal,
        statement: r.statement,
        rationale: r.rationale,
        criteria: (payload.acceptance_criteria ?? [])
          .filter((c) => c.requirement === r.key)
          .map((c) => ({ key: c.key, given: c.given, when: c.when, then: c.then, howToCheck: c.how_to_check })),
        evidence: evidenceOf(coverage.find((c) => c.identifier === identifier)),
        taskKeys: planned.filter((t) => (t.requirements ?? []).includes(r.key)).map((t) => t.key),
      }
    }),
    tasks: planned.map((t): SpecTaskView => {
      const row = byTaskKey.get(t.key)
      return {
        key: t.key,
        title: t.title || t.key,
        description: t.description ?? '',
        dependsOn: t.depends_on ?? [],
        requirementIds: (t.requirements ?? []).map(identifierOf),
        taskId: row?.id ?? null,
        status: row ? taskStatusOf(row.status) : null,
        agent: row?.assignee ?? null,
      }
    }),
    foldReady: input.foldReady === true,
    slices: (payload.slices ?? []).map((slice) => {
      const at = input.sliceDocuments?.[slice.key]
      const entry = at ? entries.find((e) => e.path === at) : undefined
      return {
        key: slice.key,
        title: slice.title || slice.key,
        intent: slice.intent ?? '',
        done: slice.done ?? '',
        buildsAfter: slice.builds_after ?? [],
        document: at ? { path: at, title: entry?.title ?? at, state: entry?.state ?? 'writing' } : null,
      }
    }),
    algorithms: (payload.algorithms ?? []).map((a) => ({ name: a.name, steps: a.steps ?? [] })),
    openQuestions: (payload.open_questions ?? []).map((q) => ({ question: q.question, resolved: q.resolved === true })),
    roadmap: roadmapOf(record.path, entries),
    updatedAt: input.updatedAt,
  }
}

/** Where a slice sits: its roadmap, and the slices on either side of it in build order. */
export function roadmapOf(path: string, entries: SpecListEntry[]): SpecDocumentView['roadmap'] {
  const self = entries.find((e) => e.path === path)
  if (!self?.roadmap) return null
  const roadmap = entries.find((e) => e.path === self.roadmap!.path)
  if (!roadmap) return null
  const slices = entries.filter((e) => e.roadmap?.path === roadmap.path).sort((a, b) => a.roadmap!.order - b.roadmap!.order)
  const at = slices.findIndex((e) => e.path === path)
  const link = (e: SpecListEntry | undefined) => (e ? { path: e.path, title: e.title } : null)
  return { path: roadmap.path, title: roadmap.title, sliceTitle: self.title, previous: link(slices[at - 1]), next: link(slices[at + 1]) }
}

// ── The list ────────────────────────────────────────────────────────────

const ARCHIVE_PREFIX = 'spec/changes/archive/'

export function listEntries(specs: SpecEntry[], records: SpecDocumentRecord[]): SpecListEntry[] {
  const byPath = new Map(records.map((r) => [r.path, r]))
  const kindByPath = new Map(specs.map((s) => [s.path, kindOf(byPath.get(s.path)?.kind ?? s.kind)]))
  return specs.map((entry) => {
    const record = byPath.get(entry.path)
    const phase = (record?.phase ?? entry.phase ?? (entry.path.startsWith('spec/capabilities/') ? 'current' : 'approved')) as SpecPhase
    const archived = phase === 'archived' || entry.path.startsWith(ARCHIVE_PREFIX)
    const building = !!record?.build
    const state: DocState = archived ? 'archived' : phase === 'exploring' ? 'writing' : building ? 'building' : 'approved'
    const parentIsRoadmap = !!entry.parent && kindByPath.get(entry.parent) === 'roadmap'
    return {
      id: record?.id ?? entry.document_id ?? entry.path,
      path: entry.path,
      title: record?.title ?? entry.title ?? entry.path,
      kind: kindByPath.get(entry.path) ?? 'baseline',
      phase: archived ? 'archived' : PHASES.includes(phase) ? phase : 'approved',
      state,
      shown: shownOf(state, record?.display_phase ?? entry.display_phase),
      updatedAt: record?.updated_at ?? entry.updated_at ?? '',
      roadmap: parentIsRoadmap ? { path: entry.parent!, order: entry.order ?? 0 } : null,
      building,
      untracked: !record && !entry.document_id,
    }
  })
}

// ── Builds ──────────────────────────────────────────────────────────────

const NO_FIGURES: Pick<BuildFigures, 'runs' | 'time' | 'cost' | 'unpriced' | 'checks'> = {
  runs: 0,
  time: { building: 0, reviewing: 0, checks: 0, held: 0, review: 0, waiting: 0 },
  cost: { build: 0, review: 0, lead: 0, mend: 0 },
  unpriced: 0,
  checks: { runs: 0, passed: 0, failed: 0, seconds: 0 },
}

/** The document's builds, newest first as the Hub lists them, numbered from the oldest. */
export function buildViews(builds: SpecBuild[], tasks: Task[], figures: Record<string, BuildFigures | undefined>): BuildView[] {
  return builds.map((build, index) => {
    const mine = figures[build.id] ?? NO_FIGURES
    const running = build.state === 'running'
    return {
      id: build.id,
      number: builds.length - index,
      driver: build.driver,
      level: build.level,
      builders: build.builders,
      reviewers: build.reviewers,
      lead: build.lead,
      running,
      ended: running ? undefined : build.state === 'stopped' ? 'stopped' : 'finished',
      startedAt: build.created_at ?? '',
      finishedAt: running ? null : build.stopped_at,
      landsOn: build.landing === 'main' ? 'main' : 'nowhere',
      budget: build.budget_cap_usd,
      tasks: countTasks(tasks.filter((t) => t.build_id === build.id)),
      time: { ...mine.time },
      cost: mine.cost,
      runs: mine.runs,
      unpriced: mine.unpriced,
      checks: mine.checks,
    }
  })
}

// ── What Check found ────────────────────────────────────────────────────

/** Which part of the document a finding concerns, from the Hub's `where` (`requirements[1]`,
 *  `tasks[0].depends_on[0]`, `acceptance_criteria[3]`, `scope.non_goals`). */
export function findingTarget(where: string, doc: SpecDocumentView, payload: SpecPayload | null): CheckFinding['target'] {
  const index = (name: string) => {
    const m = new RegExp(`^${name}\\[(\\d+)\\]`).exec(where)
    return m ? Number(m[1]) : null
  }
  const requirement = index('requirements')
  if (requirement !== null && doc.requirements[requirement]) return { kind: 'requirement', id: doc.requirements[requirement]!.identifier }
  const task = index('tasks')
  if (task !== null) {
    const key = payload?.tasks?.[task]?.key
    if (key && doc.tasks.some((t) => t.key === key)) return { kind: 'task', id: key }
  }
  const criterion = index('acceptance_criteria')
  if (criterion !== null) {
    const owner = payload?.acceptance_criteria?.[criterion]?.requirement
    const found = doc.requirements.find((r) => r.key === owner)
    if (found) return { kind: 'requirement', id: found.identifier }
  }
  if (index('open_questions') !== null) return { kind: 'section', id: 'questions' }
  if (where.startsWith('scope')) return { kind: 'section', id: 'scope' }
  if (where.startsWith('problem')) return { kind: 'section', id: 'problem' }
  return { kind: 'section', id: 'summary' }
}

export function findingsOf(
  blocking: SpecBlockingFinding[],
  warnings: SpecBlockingFinding[],
  doc: SpecDocumentView,
  payload: SpecPayload | null,
): CheckFinding[] {
  const make = (severity: CheckFinding['severity']) => (f: SpecBlockingFinding, i: number): CheckFinding => ({
    id: `${severity}:${f.code}:${f.where}:${i}`,
    severity,
    target: findingTarget(f.where, doc, payload),
    message: f.message,
  })
  return [...blocking.map(make('blocking')), ...warnings.map(make('warning'))]
}

/** The visible text of a rendered page: what a document with no structure says, never its markup. */
export function textOfPage(content: string): string {
  try {
    const parsed = new DOMParser().parseFromString(content, 'text/html')
    parsed.querySelectorAll('script,style').forEach((el) => el.remove())
    return (parsed.body.textContent ?? '').replace(/\n{3,}/g, '\n\n').trim()
  } catch {
    return ''
  }
}
