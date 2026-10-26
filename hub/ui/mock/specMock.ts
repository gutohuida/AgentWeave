/** The redesigned spec page's mock data and the state a real container would hold, shared by the
 *  Spec screen and the conversation's spec panel. The document, its requirements, criteria, tasks,
 *  coverage and the document list are the replica's recordings; the five document states, Check's
 *  findings and the builds are simulated (`// mock state`), because the behaviour behind them is
 *  roadmap slices C and D, not yet built. */
import * as React from 'react'
import { toast } from '@/lib/toast'
import { NO_DOCUMENT_FILTERS, type BuildView, type CheckFinding, type CheckState, type DocState, type DocumentFilters, type EvidenceState, type SpecAction, type SpecDocumentView, type SpecListEntry, type StartBuildChoice, type TaskStatus } from '@/components/spec/page/model'
import type { SpecSurfaceProps } from '@/components/spec/page/SpecWorkspace'
import { agents, tasks as taskFixtures } from './fixtures'
import coverageJson from './fixtures/spec_coverage.json'
import documentJson from './fixtures/spec_document.json'
import documentsJson from './fixtures/spec_documents.json'

// ── The recorded document ──────────────────────────────────────────────

interface Payload {
  title: string
  kind: SpecDocumentView['kind']
  summary: string
  problem: string
  design: string
  scope: { in_scope: string[]; non_goals: string[] }
  requirements: Array<{ key: string; modal: string; statement: string; rationale?: string | null }>
  acceptance_criteria: Array<{ key: string; requirement: string; given: string; when: string; then: string; how_to_check?: string | null }>
  tasks: Array<{ key: string; title: string; description: string; depends_on: string[]; requirements: string[] }>
  open_questions: Array<{ question: string; resolved: boolean }>
}

interface ListRecord {
  id: string
  path: string
  title: string
  kind: SpecDocumentView['kind']
  phase: SpecDocumentView['phase']
  updated_at: string
}

const RECORD = documentJson as unknown as { path: string; content: string; updated_at: string }
const DOCUMENTS = (documentsJson as unknown as { documents: ListRecord[] }).documents
const ROW = DOCUMENTS.find((d) => d.path === RECORD.path)!
/** The Hub's document read returns this structure; the recording kept it inside the rendered HTML. */
const PAYLOAD = JSON.parse(/<script[^>]*id="aw-spec-payload"[^>]*>([\s\S]*?)<\/script>/.exec(RECORD.content)![1]!) as Payload
const COVERAGE = (coverageJson as unknown as { requirements: Array<{ identifier: string; state: string }> }).requirements
const RECORDED_TASKS = taskFixtures.filter((t) => t.spec_document_id === ROW.id)

const identifierOf = (key: string) => `FR-${PAYLOAD.requirements.findIndex((r) => r.key === key) + 1}`
const ROADMAP_PATH = 'spec/changes/terra-agent-control-center-roadmap/spec.json'
const NEXT_SLICE = 'spec/changes/cairn-interactive-setup-and-skill-selection/spec.json'

export const AGENT_NAMES = agents.map((a) => a.name)

// ── Mock controls (the mock bar writes them; the hash can preset them) ───

export interface SpecMockControls {
  state: DocState
  layout: 'column' | 'switcher'
}

const STATES: DocState[] = ['writing', 'ready', 'approved', 'building', 'archived']

function readHashControls(): Partial<SpecMockControls> & { at?: string } {
  const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  const state = query.get('state') as DocState | null
  const layout = query.get('layout')
  return {
    state: state && STATES.includes(state) ? state : undefined,
    layout: layout === 'switcher' || layout === 'column' ? layout : undefined,
    at: query.get('at') ?? undefined,
  }
}

let controls: SpecMockControls = { state: 'building', layout: 'column', ...stripUndefined(readHashControls()) }
const listeners = new Set<() => void>()

function stripUndefined<T extends object>(o: T): Partial<T> {
  return Object.fromEntries(Object.entries(o).filter(([k, v]) => v !== undefined && k !== 'at')) as Partial<T>
}

export function setSpecMockControls(patch: Partial<SpecMockControls>) {
  controls = { ...controls, ...patch }
  listeners.forEach((l) => l())
}

export function useSpecMockControls(): SpecMockControls {
  return React.useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => controls,
  )
}

export const SPEC_MOCK_STATES: Array<{ value: DocState; label: string }> = [
  { value: 'writing', label: 'Being written' },
  { value: 'ready', label: 'Ready (checked clean)' },
  { value: 'approved', label: 'Approved, no build' },
  { value: 'building', label: 'Building' },
  { value: 'archived', label: 'Archived (built)' },
]

// ── Simulated pieces ────────────────────────────────────────────────────

// mock state: what Check finds on the document while it is being written. One gap blocks
// approval; one only warns.
const FIRST_CHECK: CheckFinding[] = [
  {
    id: 'f1',
    severity: 'blocking',
    target: { kind: 'requirement', id: identifierOf('structured-metadata') },
    message: 'No acceptance criterion says how this is checked. Add one, or say a person checks it.',
  },
  {
    id: 'f2',
    severity: 'warning',
    target: { kind: 'task', id: 'skill-installer' },
    message: 'No reviewer is named here or on the document, so any free agent will review it.',
  },
]

// mock state: evidence a running build has produced so far (the recording's coverage, with one
// piece waiting for review and one sent back, so every state shows).
const BUILDING_EVIDENCE: Record<string, EvidenceState> = { 'FR-2': 'awaiting', 'FR-3': 'awaiting', 'FR-11': 'rejected', 'FR-15': 'awaiting' }

// mock state: the running build's tasks, advanced by a timer.
const BUILDING_TASKS: Record<string, { status: TaskStatus; agent: string | null }> = {
  'chain-format': { status: 'approved', agent: 'Builder' },
  'create-command': { status: 'under_review', agent: 'Builder' },
  'resume-command': { status: 'in_progress', agent: 'QA2' },
  'skill-installer': { status: 'pending', agent: null },
  'install-and-drive-green': { status: 'pending', agent: null },
}

const STEP: Partial<Record<TaskStatus, TaskStatus>> = { pending: 'in_progress', in_progress: 'under_review', under_review: 'approved' }

// mock state: Build 1 is the 2026-10-25 shape (a Gated Hub flow, one reviewer, hours waiting for
// review); Build 2 is the same plan at Fast with a lead, running now.
function finishedBuild(): BuildView {
  return {
    id: 'b1',
    number: 1,
    driver: 'flow',
    level: 'gated',
    builders: ['Builder'],
    reviewers: ['QA1'],
    lead: null,
    running: false,
    startedAt: '2026-10-16T14:02:00Z',
    finishedAt: '2026-10-16T21:28:00Z',
    landsOn: 'a branch',
    budget: null,
    tasks: counts({ approved: 5 }),
    time: { building: 2 * 3600 + 14 * 60, review: 3 * 3600 + 18 * 60, checks: 52 * 60, waiting: 62 * 60 },
    cost: { build: 31.4, review: 20.6, lead: 0 },
    runs: 23,
  }
}

function runningBuild(choice?: StartBuildChoice, number = 2): BuildView {
  return {
    id: `b${number}`,
    number,
    driver: choice?.driver ?? 'lead',
    level: choice?.level ?? 'fast',
    builders: choice?.builders ?? ['Builder', 'QA2'],
    reviewers: choice?.level === 'fast' ? [] : (choice?.reviewers ?? []),
    lead: choice?.driver === 'lead' || !choice ? (choice?.lead ?? 'Architect') : null,
    running: true,
    startedAt: '2026-10-17T11:24:00Z',
    finishedAt: null,
    landsOn: choice ? (choice.landsOn === 'main' ? 'main' : choice.branch) : 'main',
    budget: choice ? choice.budget : 25,
    tasks: counts({}),
    time: choice ? { building: 0, review: 0, checks: 0, waiting: 0 } : { building: 31 * 60, review: 4 * 60, checks: 6 * 60, waiting: 2 * 60 },
    cost: choice ? { build: 0, review: 0, lead: 0 } : { build: 6.2, review: 0, lead: 1.1 },
    runs: choice ? 0 : 7,
  }
}

function counts(partial: Partial<Record<TaskStatus, number>>): Record<TaskStatus, number> {
  return { pending: 0, assigned: 0, in_progress: 0, completed: 0, under_review: 0, revision_needed: 0, approved: 0, rejected: 0, ...partial }
}

function tally(tasks: Record<string, { status: TaskStatus }>): Record<TaskStatus, number> {
  const c = counts({})
  Object.values(tasks).forEach((t) => (c[t.status] += 1))
  return c
}

// ── The view the page draws ─────────────────────────────────────────────

function documentView(state: DocState, live: Record<string, { status: TaskStatus; agent: string | null }>): SpecDocumentView {
  const planned = state === 'writing' || state === 'ready' || state === 'approved'
  const evidence = (identifier: string): EvidenceState => {
    if (planned) return 'not_started'
    if (state === 'building' && BUILDING_EVIDENCE[identifier]) return BUILDING_EVIDENCE[identifier]!
    const recorded = COVERAGE.find((c) => c.identifier === identifier)?.state
    return recorded === 'verified' ? 'verified' : 'in_progress'
  }
  return {
    id: ROW.id,
    path: ROW.path,
    title: PAYLOAD.title,
    kind: PAYLOAD.kind,
    phase: state === 'writing' || state === 'ready' ? 'exploring' : state === 'archived' ? 'archived' : 'approved',
    state,
    summary: PAYLOAD.summary,
    problem: PAYLOAD.problem,
    inScope: PAYLOAD.scope.in_scope,
    nonGoals: PAYLOAD.scope.non_goals,
    design: PAYLOAD.design,
    requirements: PAYLOAD.requirements.map((r, i) => {
      const identifier = `FR-${i + 1}`
      return {
        identifier,
        key: r.key,
        modal: r.modal,
        statement: r.statement,
        rationale: r.rationale,
        criteria: PAYLOAD.acceptance_criteria
          .filter((c) => c.requirement === r.key)
          .map((c) => ({ key: c.key, given: c.given, when: c.when, then: c.then, howToCheck: c.how_to_check })),
        evidence: evidence(identifier),
        taskKeys: PAYLOAD.tasks.filter((t) => t.requirements.includes(r.key)).map((t) => t.key),
      }
    }),
    tasks: PAYLOAD.tasks.map((t) => {
      const recorded = RECORDED_TASKS.find((r) => r.spec_task_key === t.key)
      const status: TaskStatus | null = planned ? (state === 'approved' ? 'pending' : null) : state === 'building' ? live[t.key]!.status : ((recorded?.status as TaskStatus) ?? 'approved')
      return {
        key: t.key,
        title: t.title,
        description: t.description,
        dependsOn: t.depends_on,
        requirementIds: t.requirements.map(identifierOf),
        taskId: planned && state !== 'approved' ? null : (recorded?.id ?? null),
        status,
        agent: state === 'building' ? live[t.key]!.agent : state === 'archived' ? (recorded?.assignee ?? null) : null,
      }
    }),
    openQuestions: PAYLOAD.open_questions,
    roadmap: {
      path: ROADMAP_PATH,
      title: 'Terra agent control center',
      sliceTitle: 'Cairn: standalone handoff tool',
      previous: null,
      next: { path: NEXT_SLICE, title: 'Cairn interactive setup and skill selection' },
    },
    updatedAt: RECORD.updated_at,
  }
}

/** The document list: the replica's four documents, plus (mock state) the rest of the Terra
 *  roadmap's slices, two capabilities and an archived change, so ordering, grouping and the filters
 *  have something to work on. */
function listEntries(state: DocState): SpecListEntry[] {
  const order: Record<string, number> = { [ROW.path]: 1, [NEXT_SLICE]: 2, 'spec/changes/terra-app-and-plugin-contract/spec.json': 3 }
  const recorded: SpecListEntry[] = DOCUMENTS.map((d) => {
    const isOpen = d.path === ROW.path
    const docState: DocState = isOpen ? state : d.phase === 'exploring' ? 'writing' : d.phase === 'archived' ? 'archived' : 'approved'
    return {
      id: d.id,
      path: d.path,
      title: d.title,
      kind: d.kind,
      phase: d.phase,
      state: d.path === 'spec/changes/terra-app-and-plugin-contract/spec.json' ? 'building' : docState,
      updatedAt: d.updated_at,
      roadmap: order[d.path] ? { path: ROADMAP_PATH, order: order[d.path]! } : null,
      building: (isOpen && state === 'building') || d.path === 'spec/changes/terra-app-and-plugin-contract/spec.json',
    }
  })
  const simulated: SpecListEntry[] = [
    { id: 'm1', path: 'spec/changes/terra-observe-agents-across-projects/spec.json', title: 'Terra: observe agents across projects', kind: 'change-spec', phase: 'exploring', state: 'writing', updatedAt: '2026-10-17T09:40:00Z', roadmap: { path: ROADMAP_PATH, order: 4 }, building: false },
    { id: 'm2', path: 'spec/changes/terra-plugin-registry/spec.json', title: 'Terra: a registry of plugins', kind: 'change-spec', phase: 'exploring', state: 'writing', updatedAt: '2026-10-15T16:05:00Z', roadmap: { path: ROADMAP_PATH, order: 5 }, building: false },
    { id: 'm3', path: 'spec/capabilities/handoff-chain/spec.json', title: 'Handoff chain', kind: 'capability', phase: 'current', state: 'approved', updatedAt: '2026-10-12T10:00:00Z', roadmap: null, building: false },
    { id: 'm4', path: 'spec/capabilities/agent-skills/spec.json', title: 'Agent skills', kind: 'capability', phase: 'current', state: 'approved', updatedAt: '2026-10-09T08:30:00Z', roadmap: null, building: false },
    { id: 'm5', path: 'spec/changes/cairn-first-sketch/spec.json', title: 'Cairn: a first sketch', kind: 'change-spec', phase: 'archived', state: 'archived', updatedAt: '2026-10-11T18:20:00Z', roadmap: null, building: false },
  ]
  return [...recorded, ...simulated]
}

// ── The controller ──────────────────────────────────────────────────────

const DEFAULT_CHOICE: StartBuildChoice = {
  driver: 'lead',
  level: 'fast',
  builders: ['Builder', 'QA2'],
  reviewers: ['QA1'],
  lead: 'Architect',
  budget: 25,
  window: 'now',
  landsOn: 'main',
  branch: 'build/cairn-handoff',
}

function copy(text: string) {
  void navigator.clipboard?.writeText(text).catch(() => undefined)
}

/** Everything the page's components take, as a container would hold it. */
export function useSpecMock(routeHash: string) {
  const { state, layout } = useSpecMockControls()
  const initialAnchor = React.useMemo(() => readHashControls().at ?? null, [])
  const [check, setCheck] = React.useState<CheckState>(state === 'ready' ? { status: 'done', findings: [], at: 'preset' } : { status: 'idle' })
  const [filters, setFilters] = React.useState<DocumentFilters>(NO_DOCUMENT_FILTERS)
  const [live, setLive] = React.useState(BUILDING_TASKS)
  const [builds, setBuilds] = React.useState<BuildView[]>(() => buildsFor(state))
  const [dialog, setDialog] = React.useState<{ open: boolean; approving: boolean }>({ open: false, approving: false })
  const checks = React.useRef(0)
  const keepBuilds = React.useRef(false)

  // The mock bar changed the state: reset what depends on it (but not the build just started).
  React.useEffect(() => {
    if (keepBuilds.current) {
      keepBuilds.current = false
      setCheck({ status: 'idle' })
      return
    }
    setBuilds(buildsFor(state))
    setLive(BUILDING_TASKS)
    setCheck(state === 'ready' ? { status: 'done', findings: [], at: `preset-${Date.now()}` } : { status: 'idle' })
    checks.current = state === 'ready' ? 1 : 0
  }, [state])

  // mock state: the running build advances: time accrues, a task moves on every few seconds, and
  // the cost grows with it. Stops short of the last approval, so it keeps running.
  const running = builds.some((b) => b.running)
  React.useEffect(() => {
    if (!running) return
    let tick = 0
    const timer = window.setInterval(() => {
      tick += 1
      setLive((current) => {
        if (tick % 3 !== 0) return current
        const keys = Object.keys(current)
        const movable = keys.find((k) => current[k]!.status === 'under_review' && keys.filter((x) => current[x]!.status !== 'approved').length > 1) ?? keys.find((k) => current[k]!.status === 'in_progress') ?? keys.find((k) => current[k]!.status === 'pending')
        if (!movable) return current
        const next = STEP[current[movable]!.status]!
        return { ...current, [movable]: { status: next, agent: current[movable]!.agent ?? (Object.values(current).filter((t) => t.agent === 'Builder' && t.status === 'in_progress').length ? 'QA2' : 'Builder') } }
      })
      setBuilds((all) =>
        all.map((b) => {
          if (!b.running) return b
          const reviewing = b.tasks.under_review > 0
          return {
            ...b,
            time: { ...b.time, building: b.time.building + 40, review: b.time.review + (reviewing ? 25 : 0), checks: b.time.checks + (tick % 4 === 0 ? 30 : 0), waiting: b.time.waiting + (b.tasks.pending ? 6 : 0) },
            cost: { ...b.cost, build: +(b.cost.build + 0.18).toFixed(2), review: +(b.cost.review + (reviewing && b.level !== 'fast' ? 0.07 : 0)).toFixed(2), lead: +(b.cost.lead + (b.lead ? 0.03 : 0)).toFixed(2) },
            runs: b.runs + (tick % 3 === 0 ? 1 : 0),
          }
        }),
      )
    }, 1000)
    return () => window.clearInterval(timer)
  }, [running])

  // The running build's task counts follow the tasks.
  const shownBuilds = builds.map((b) => (b.running ? { ...b, tasks: tally(live) } : b))
  const doc = documentView(state, live)

  const linkTo = (anchor: string | null) => {
    const base = routeHash.split('?')[0]
    return `${window.location.origin}${window.location.pathname}#${base}?state=${state}${anchor ? `&at=${encodeURIComponent(anchor)}` : ''}`
  }

  const onAction = (action: SpecAction) => {
    switch (action) {
      case 'check': {
        setCheck({ status: 'checking' })
        window.setTimeout(() => {
          checks.current += 1
          // mock state: the first check finds a gap and a warning; the next, as if the writing agent
          // had answered them, finds nothing, and the document is ready. The phase does not change.
          const clean = checks.current > 1 || state === 'approved'
          setCheck({ status: 'done', findings: clean ? [] : FIRST_CHECK, at: String(Date.now()) })
          if (clean && state === 'writing') setSpecMockControls({ state: 'ready' })
          toast(clean ? { title: 'Nothing blocks approval', tone: 'success' } : { title: 'Check found 1 blocking gap and 1 warning', description: 'Each is shown beside what it concerns.' })
        }, 1100)
        return
      }
      case 'approve':
        setSpecMockControls({ state: 'approved' })
        toast({ title: 'Approved', description: '5 tasks are laid out as a plan. Nothing is running yet.', tone: 'success', action: { label: 'Undo', onClick: () => setSpecMockControls({ state: 'ready' }) } })
        return
      case 'approve-and-build':
        setDialog({ open: true, approving: true })
        return
      case 'build':
        setDialog({ open: true, approving: false })
        return
      case 'reopen':
        setSpecMockControls({ state: 'writing' })
        toast({ title: 'Reopened for changes', description: 'Its tasks and builds are kept.' })
        return
      case 'open-build':
        return
    }
  }

  const surface: SpecSurfaceProps = {
    doc,
    builds: [...shownBuilds].reverse(),
    check,
    filters,
    onFiltersChange: setFilters,
    now: new Date('2026-10-17T12:10:00Z'),
    initialAnchor,
    onAction,
    onOpenDocument: (path) => {
      if (path === doc.path) return
      const entry = listEntries(state).find((e) => e.path === path)
      toast({ title: `Opens ${entry?.title ?? (path === ROADMAP_PATH ? 'the roadmap' : 'that document')}`, description: 'The mock holds one full document.' })
    },
    onCopyLink: (anchor) => {
      copy(linkTo(anchor))
      toast({ title: 'Link copied', description: anchor ? `Opens this document at ${anchor.replace(/^(section|task|build)-/, '')}.` : 'Opens this document.', tone: 'success' })
    },
    onCopyPath: () => {
      copy(doc.path)
      toast({ title: 'Path copied', tone: 'success' })
    },
    onArchive: () => {
      setSpecMockControls({ state: 'archived' })
      toast({ title: 'Archived', action: { label: 'Undo', onClick: () => setSpecMockControls({ state: 'approved' }) } })
    },
    onDelete: () => toast({ title: 'Delete asks first', description: 'A confirm dialog names the tasks it removes.' }),
    onStartBuild: () => setDialog({ open: true, approving: false }),
    onOpenRuns: (b) => toast({ title: `Opens Build ${b.number}'s ${b.runs} runs`, description: 'The runs list, filtered to this build.' }),
    onStopBuild: (b) => {
      setBuilds((all) => all.map((x) => (x.id === b.id ? { ...x, running: false, finishedAt: '2026-10-17T12:10:00Z' } : x)))
      setSpecMockControls({ state: 'approved' })
      toast({ title: `Build ${b.number} stopped`, description: 'Work in progress stays on its branch.' })
    },
  }

  const startDialog = {
    open: dialog.open,
    approving: dialog.approving,
    agents: AGENT_NAMES,
    initial: DEFAULT_CHOICE,
    onOpenChange: (open: boolean) => setDialog((d) => ({ ...d, open })),
    onStart: (choice: StartBuildChoice) => {
      setDialog({ open: false, approving: false })
      setLive(Object.fromEntries(Object.keys(BUILDING_TASKS).map((k) => [k, { status: 'pending' as TaskStatus, agent: null }])))
      setBuilds((all) => [...all.map((b) => ({ ...b, running: false })), runningBuild(choice, all.length + 1)])
      keepBuilds.current = state !== 'building'
      setSpecMockControls({ state: 'building' })
      toast({ title: `Build ${builds.length + 1} started`, description: `${choice.level === 'fast' ? 'Fast' : choice.level === 'reviewed' ? 'Reviewed' : 'Gated'}, ${choice.builders.join(' and ')} building.`, tone: 'success' })
    },
  }

  return { surface, layout, entries: listEntries(state), startDialog }
}

function buildsFor(state: DocState): BuildView[] {
  if (state === 'building') return [finishedBuild(), runningBuild()]
  if (state === 'archived') return [finishedBuild()]
  return []
}
