/** The redesigned spec page's view model (spec `the-spec-page-redesigned`).
 *
 *  Everything the page draws is one of these shapes, so the components never see a route payload:
 *  the mock builds them from recorded fixtures, and wiring builds them from the Hub's hooks. The
 *  helpers here are pure (filtering, ordering, which actions a state offers) so the same rules hold
 *  in the Spec tab and the conversation's side panel. */

export type SpecKind = 'change-spec' | 'roadmap' | 'capability' | 'baseline' | 'system-map'
export type SpecPhase = 'exploring' | 'proposed' | 'approved' | 'archived' | 'current'

/** Where a document is on its way, as the operator thinks of it. `writing` and `ready` are both
 *  being written; `ready` is a writing document whose last check found nothing blocking. */
export type DocState = 'writing' | 'ready' | 'approved' | 'building' | 'archived'

export type EvidenceState = 'verified' | 'awaiting' | 'in_progress' | 'held' | 'not_started' | 'rejected'

export type TaskStatus =
  | 'pending'
  | 'assigned'
  | 'in_progress'
  | 'completed'
  | 'under_review'
  | 'revision_needed'
  | 'approved'
  | 'rejected'

export interface SpecCriterion {
  key: string
  given: string
  when: string
  then: string
  howToCheck?: string | null
}

export interface SpecRequirementView {
  identifier: string
  key: string
  modal: string
  statement: string
  rationale?: string | null
  criteria: SpecCriterion[]
  evidence: EvidenceState
  /** Keys of the document's tasks that serve it. */
  taskKeys: string[]
}

export interface SpecTaskView {
  key: string
  title: string
  description: string
  dependsOn: string[]
  requirementIds: string[]
  /** Set once the plan is laid out as tasks (approved); a writing document's tasks are a plan only. */
  taskId?: string | null
  status?: TaskStatus | null
  agent?: string | null
}

export interface SpecSlice {
  key: string
  title: string
  intent: string
  done: string
  buildsAfter: string[]
  /** The change document that specifies the slice, and where it stands. */
  document?: { path: string; title: string; state: DocState } | null
}

export interface SpecDocumentView {
  id: string
  path: string
  title: string
  kind: SpecKind
  phase: SpecPhase
  state: DocState
  shown: ShownState
  summary: string
  problem: string
  inScope: string[]
  nonGoals: string[]
  design: string
  requirements: SpecRequirementView[]
  tasks: SpecTaskView[]
  openQuestions: Array<{ question: string; resolved: boolean }>
  /** A finished change not yet folded into a capability: Fold is its next action. */
  foldReady?: boolean
  /** A roadmap's slices and the procedures a document describes. */
  slices?: SpecSlice[]
  algorithms?: Array<{ name: string; steps: string[] }>
  /** The roadmap this document is a slice of, and its neighbours in build order. */
  roadmap?: {
    path: string
    title: string
    sliceTitle: string
    previous?: { path: string; title: string } | null
    next?: { path: string; title: string } | null
  } | null
  updatedAt: string
}

/** What one press of Check found. `target` names what it concerns: a requirement's identifier, a
 *  task's key, or a section id. */
export interface CheckFinding {
  id: string
  severity: 'blocking' | 'warning'
  target: { kind: 'requirement' | 'task' | 'section'; id: string }
  message: string
}

export type CheckState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'done'; findings: CheckFinding[]; at: string }

// ── Builds ──────────────────────────────────────────────────────────────

export type BuildDriver = 'flow' | 'lead' | 'hand'
export type BuildLevel = 'fast' | 'reviewed' | 'gated'

export const DRIVER_LABEL: Record<BuildDriver, string> = { flow: 'Hub flow', lead: 'Lead agent', hand: 'By hand' }
export const DRIVER_ICON: Record<BuildDriver, string> = { flow: 'sync', lead: 'compass', hand: 'hand' }
export const LEVEL_LABEL: Record<BuildLevel, string> = { fast: 'Fast', reviewed: 'Reviewed', gated: 'Gated' }
export const LEVEL_MEANING: Record<BuildLevel, string> = {
  fast: 'The builder or the lead approves its own work once the checks pass.',
  reviewed: 'Anyone but the builder approves it; the checks still run.',
  gated: 'A reviewer accepts evidence for every requirement before it merges.',
}
export const DRIVER_MEANING: Record<BuildDriver, string> = {
  flow: 'The Hub hands out each task as soon as its prerequisites are met.',
  lead: 'One agent decides who builds what, and when.',
  hand: 'Nothing is handed out; you assign each task yourself.',
}

/** Wall time, in seconds, split by what the build was doing. */
export interface BuildTime {
  building: number
  reviewing: number
  checks: number
  /** Done and waiting, with the newest check on it failed (`work_tally`: held by a failed check). */
  held: number
  /** Done and waiting for a reviewer. */
  review: number
  waiting: number
}

/** In the order the Hub gives an instant to the first part that applies, so the bar reads left to
 *  right as the work moves: a part's seconds never overlap another's. */
export const TIME_PARTS: Array<{ key: keyof BuildTime; label: string; tone: string }> = [
  { key: 'building', label: 'Building', tone: 'var(--blue)' },
  { key: 'reviewing', label: 'Reviewing', tone: 'var(--purple)' },
  { key: 'checks', label: 'Checks', tone: 'var(--ring)' },
  { key: 'held', label: 'Held by a failed check', tone: 'var(--red)' },
  { key: 'review', label: 'Waiting for review', tone: 'var(--amber)' },
  { key: 'waiting', label: 'Waiting to be handed out', tone: 'var(--text-3)' },
]

/** Dollars, split by who spent them (mending: the Hub's mender, on a line of its own). A role whose
 *  runs reported no cost is null: unknown, not $0. */
export interface BuildCost {
  build: number | null
  review: number | null
  lead: number | null
  mend: number | null
}

export interface BuildView {
  id: string
  number: number
  driver: BuildDriver
  level: BuildLevel
  builders: string[]
  reviewers: string[]
  lead: string | null
  running: boolean
  /** How a build that is no longer running ended: it finished, or it was stopped (by the operator, a cap or a window). */
  ended?: 'finished' | 'stopped'
  startedAt: string
  finishedAt: string | null
  landsOn: string
  budget: number | null
  tasks: Record<TaskStatus, number>
  time: BuildTime
  cost: BuildCost
  runs: number
  /** Runs counted beside the cost: none reported one. */
  unpriced: number
  /** The build's check runs, on a line of their own. */
  checks: { runs: number; passed: number; failed: number; seconds: number }
}

export interface StartBuildChoice {
  driver: BuildDriver
  level: BuildLevel
  builders: string[]
  reviewers: string[]
  lead: string | null
  budget: number | null
  window: 'now' | 'tonight' | 'weekdays'
  landsOn: 'main' | 'branch'
  branch: string
}

// ── The header's actions ────────────────────────────────────────────────

export type SpecAction = 'check' | 'approve' | 'approve-and-build' | 'build' | 'open-build' | 'reopen' | 'fold'

export interface HeaderActions {
  /** The one the document is waiting for: drawn as the primary button. */
  primary: SpecAction | null
  /** The others open to it, in display order. */
  secondary: SpecAction[]
}

/** Exactly the actions open to a document in each state. Check is open while a document is being
 *  written or is approved but not yet built, and never changes the phase. */
export function actionsFor(state: DocState, kind: SpecKind = 'change-spec', foldReady = false): HeaderActions {
  // Only a change is built: any other kind is approved and read, and has no build to start.
  const builds = kind === 'change-spec'
  switch (state) {
    case 'writing':
      return { primary: 'check', secondary: [] }
    case 'ready':
      return { primary: 'approve', secondary: builds ? ['check', 'approve-and-build'] : ['check'] }
    case 'approved':
      // Every task decided and in no capability yet: folding is the close-out.
      if (foldReady && builds) return { primary: 'fold', secondary: [] }
      return builds ? { primary: 'build', secondary: ['check'] } : { primary: null, secondary: [] }
    case 'building':
      return { primary: 'open-build', secondary: [] }
    case 'archived':
      // The Hub has no transition out of archived: nothing is offered.
      return { primary: null, secondary: [] }
  }
}

/** The journey ribbon's stops, and where each state sits on it. */
export const JOURNEY: Array<{ key: string; label: string }> = [
  { key: 'writing', label: 'Writing' },
  { key: 'approved', label: 'Approved' },
  { key: 'building', label: 'Building' },
  { key: 'done', label: 'Done' },
]

export function journeyIndex(state: ShownState): number {
  return { writing: 0, ready: 0, approved: 1, building: 2, done: 3, archived: 3 }[state]
}

export const STATE_LABEL: Record<DocState, string> = {
  writing: 'Writing',
  ready: 'Ready to approve',
  approved: 'Approved',
  building: 'Building',
  archived: 'Archived',
}

/** What a document reads as to the operator (F1089): its state, except a built change that has
 *  nothing open reads `done`. The Hub decides it (`display_phase`); the actions still follow
 *  `DocState`, because they depend on whether a build is *running*. */
export type ShownState = DocState | 'done'

export const SHOWN_LABEL: Record<ShownState, string> = { ...STATE_LABEL, done: 'Done' }

export function shownOf(state: DocState, displayPhase?: string | null): ShownState {
  if (state !== 'approved' && state !== 'building') return state
  return displayPhase === 'done' || displayPhase === 'building' || displayPhase === 'approved' ? displayPhase : state
}

// ── Within a document ──────────────────────────────────────────────────

export const EVIDENCE_LABEL: Record<EvidenceState, string> = {
  verified: 'Verified',
  awaiting: 'Awaiting review',
  in_progress: 'No evidence yet',
  held: 'Held, sent back',
  not_started: 'Not started',
  rejected: 'Evidence rejected',
}

export const EVIDENCE_TONE: Record<EvidenceState, string> = {
  verified: 'var(--green)',
  awaiting: 'var(--amber)',
  in_progress: 'var(--blue)',
  held: 'var(--text-2)',
  not_started: 'var(--text-3)',
  rejected: 'var(--red)',
}

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  pending: 'Waiting',
  assigned: 'Assigned',
  in_progress: 'Building',
  completed: 'Built',
  under_review: 'In review',
  revision_needed: 'Sent back',
  approved: 'Approved',
  rejected: 'Rejected',
}

/** The order status sorts in: what needs attention first, what is done last. */
const STATUS_RANK: Record<TaskStatus, number> = {
  revision_needed: 0,
  under_review: 1,
  completed: 2,
  in_progress: 3,
  assigned: 4,
  pending: 5,
  approved: 6,
  rejected: 7,
}

export interface DocumentFilters {
  evidence: EvidenceState | 'any'
  /** A task key: requirements that task serves. */
  task: string | 'any'
  status: TaskStatus | 'any'
  agent: string | 'any'
  order: 'build' | 'status'
}

export const NO_DOCUMENT_FILTERS: DocumentFilters = { evidence: 'any', task: 'any', status: 'any', agent: 'any', order: 'build' }

export function filterRequirements(requirements: SpecRequirementView[], filters: DocumentFilters): SpecRequirementView[] {
  return requirements.filter(
    (r) => (filters.evidence === 'any' || r.evidence === filters.evidence) && (filters.task === 'any' || r.taskKeys.includes(filters.task)),
  )
}

/** Each task's depth in its dependency graph: 0 for a task with no prerequisites. */
export function buildLevels(tasks: SpecTaskView[]): Map<string, number> {
  const byKey = new Map(tasks.map((t) => [t.key, t]))
  const depth = new Map<string, number>()
  const visit = (key: string, seen: Set<string>): number => {
    const known = depth.get(key)
    if (known !== undefined) return known
    if (seen.has(key)) return 0
    seen.add(key)
    const task = byKey.get(key)
    const d = task ? Math.max(-1, ...task.dependsOn.filter((k) => byKey.has(k)).map((k) => visit(k, seen))) + 1 : 0
    depth.set(key, d)
    return d
  }
  tasks.forEach((t) => visit(t.key, new Set()))
  return depth
}

export function orderTasks(tasks: SpecTaskView[], filters: DocumentFilters): SpecTaskView[] {
  const shown = tasks.filter(
    (t) => (filters.status === 'any' || t.status === filters.status) && (filters.agent === 'any' || t.agent === filters.agent),
  )
  const declared = new Map(tasks.map((t, i) => [t.key, i]))
  if (filters.order === 'status') {
    return [...shown].sort(
      (a, b) =>
        (STATUS_RANK[a.status ?? 'pending'] - STATUS_RANK[b.status ?? 'pending']) || declared.get(a.key)! - declared.get(b.key)!,
    )
  }
  const levels = buildLevels(tasks)
  return [...shown].sort((a, b) => levels.get(a.key)! - levels.get(b.key)! || declared.get(a.key)! - declared.get(b.key)!)
}

export function countFilters(filters: DocumentFilters): number {
  return (['evidence', 'task', 'status', 'agent'] as const).filter((k) => filters[k] !== 'any').length
}

// ── The document list ───────────────────────────────────────────────────

export interface SpecListEntry {
  id: string
  path: string
  title: string
  kind: SpecKind
  phase: SpecPhase
  state: DocState
  shown: ShownState
  updatedAt: string
  /** A slice: the roadmap's path and its position in the roadmap's build order. */
  roadmap?: { path: string; order: number } | null
  building: boolean
  /** On disk, but the Hub keeps no record of it: it can be adopted. */
  untracked?: boolean
}

export type ListOrder = 'changed' | 'phase' | 'title' | 'roadmap'
export type ListKindFilter = 'all' | 'change-spec' | 'roadmap' | 'capability'
export type ListPhaseFilter = 'any' | 'writing' | 'approved' | 'archived'

export interface ListPreferences {
  query: string
  kind: ListKindFilter
  phase: ListPhaseFilter
  buildingOnly: boolean
  order: ListOrder
}

export const DEFAULT_LIST_PREFERENCES: ListPreferences = { query: '', kind: 'all', phase: 'any', buildingOnly: false, order: 'roadmap' }

const PHASE_RANK: Record<ShownState, number> = { building: 0, ready: 1, writing: 2, approved: 3, done: 4, archived: 5 }

function matchesPhase(state: DocState, filter: ListPhaseFilter): boolean {
  if (filter === 'any') return true
  if (filter === 'writing') return state === 'writing' || state === 'ready'
  if (filter === 'approved') return state === 'approved' || state === 'building'
  return state === 'archived'
}

export interface ListGroup {
  /** The roadmap heading a group of slices sits under, or null for a plain run of documents. */
  roadmap: SpecListEntry | null
  label: string | null
  entries: SpecListEntry[]
}

/** The list after the operator's filters and order. Ordering by roadmap groups each roadmap's
 *  slices under it in build order; ordering by phase groups by phase; the others are one run. A
 *  roadmap whose slices match stays as their heading even when it does not match itself. */
export function arrangeList(entries: SpecListEntry[], prefs: ListPreferences): ListGroup[] {
  const query = prefs.query.trim().toLowerCase()
  const matches = (e: SpecListEntry) =>
    (prefs.kind === 'all' || e.kind === prefs.kind) &&
    matchesPhase(e.state, prefs.phase) &&
    (!prefs.buildingOnly || e.building) &&
    (!query || e.title.toLowerCase().includes(query) || e.path.toLowerCase().includes(query))
  const shown = entries.filter(matches)
  const byChanged = (a: SpecListEntry, b: SpecListEntry) => b.updatedAt.localeCompare(a.updatedAt)

  switch (prefs.order) {
    case 'changed':
      return [{ roadmap: null, label: null, entries: [...shown].sort(byChanged) }]
    case 'title':
      return [{ roadmap: null, label: null, entries: [...shown].sort((a, b) => a.title.localeCompare(b.title)) }]
    case 'phase': {
      const groups: ListGroup[] = []
      for (const [label, states] of [
        ['Building', ['building']],
        ['Writing', ['ready', 'writing']],
        ['Approved', ['approved']],
        ['Done', ['done']],
        ['Archived', ['archived']],
      ] as Array<[string, ShownState[]]>) {
        const inGroup = shown.filter((e) => states.includes(e.shown)).sort((a, b) => PHASE_RANK[a.shown] - PHASE_RANK[b.shown] || byChanged(a, b))
        if (inGroup.length) groups.push({ roadmap: null, label, entries: inGroup })
      }
      return groups
    }
    case 'roadmap': {
      const roadmaps = entries.filter((e) => e.kind === 'roadmap')
      const groups: ListGroup[] = []
      for (const roadmap of roadmaps.sort(byChanged)) {
        const slices = shown.filter((e) => e.roadmap?.path === roadmap.path).sort((a, b) => a.roadmap!.order - b.roadmap!.order)
        if (slices.length || shown.includes(roadmap)) groups.push({ roadmap, label: null, entries: slices })
      }
      const loose = shown.filter((e) => e.kind !== 'roadmap' && !roadmaps.some((r) => r.path === e.roadmap?.path)).sort(byChanged)
      if (loose.length) groups.push({ roadmap: null, label: groups.length ? 'Not in a roadmap' : null, entries: loose })
      return groups
    }
  }
}

/** An anchor id for a position in the document, used by the outline, links and history. */
export const anchors = {
  section: (id: string) => `section-${id}`,
  requirement: (identifier: string) => identifier,
  task: (key: string) => `task-${key}`,
  build: (id: string) => `build-${id}`,
}

/** Where a capability titled so lives, or null when the title holds nothing a path can be made of.
 *  The same folding as the Hub's `spec_naming.slugify`, under its `CAPABILITY_ROOT`. */
export function capabilityPathFor(title: string): string | null {
  const slug = title
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug ? `spec/capabilities/${slug}/spec.json` : null
}
