import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'

import type { LoopDetail } from '@/api/loops'
import type { LoopSummary } from '@/api/jobs'
import type { OverviewRunning } from '@/api/overview'
import type { ProjectBuildRow } from '@/api/projectBuilds'
import type { SpecBuild } from '@/api/spec'
import type { Task } from '@/api/tasks'
import { useLoop } from '@/api/loops'
import { BuildView } from '@/components/builds/BuildView'
import { NO_ADDRESS, type BuildRead } from '@/components/builds/buildViewModel'
import { OverviewBriefing } from '@/components/overview/OverviewBriefing'
import { OverviewDashboard, type DashActivity } from '@/components/overview/OverviewDashboard'
import { RunningTab } from '@/components/panel/RunningTab'
import { runningItems } from '@/components/panel/runningModel'
import { LoopTab } from '@/components/spec/LoopTab'
import { SpecBuildsSection } from '@/components/spec/page/SpecBuilds'
import { SpecOutlineRail } from '@/components/spec/page/SpecOutline'
import { buildViews, specTaskOf } from '@/components/spec/page/adapt'
import type { SpecDocumentView } from '@/components/spec/page/model'
import { ThreadTaskCard } from '@/components/spec/page/threads/shared'
import { DependencyMapView } from '@/components/tasks/DependencyMapView'
import { checkMarker, type CheckState } from '@/lib/checkState'
import { stageVisual } from '@/lib/taskStageVisual'
import { STAGE_LABELS } from '@/lib/taskStage'
import { TaskStageWord } from '@/components/tasks/TaskStageWord'
import recorded from './fixtures/everyRouteStages.json'

/* Every surface that shows where a task is, rendered from the response its own route really gave
 * (`task-stages-in-the-build-view-and-dependency-map` FR-11, criterion every-route-carries-stage;
 * FR-2, FR-9, FR-12). The fixture is written by the Hub test that fetches every one of those routes
 * on one database, with a task in Landing checks and one in Pre-review checks
 * (`hub/tests/test_every_route_carries_the_stage.py`, `AW_RECORD_STAGE_ROUTES=1`); that test also
 * asserts each route says what the task list says. Here each surface must word each task alike. */

vi.mock('@/api/loops', () => ({
  useLoop: vi.fn(),
  useStopLoop: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useArchiveLoop: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useSetLoopControl: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useUpdateLoopSettings: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null, reset: vi.fn() }),
}))
vi.mock('@/api/jobs', () => ({ useJob: () => ({ data: undefined }) }))
vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [] }) }))

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

afterEach(cleanup)

const routes = recorded.routes as unknown as Record<string, unknown>
const [LANDING, PRE_REVIEW, AFTER] = recorded.ids as [string, string, string]
const tasks = (routes['/tasks?limit=1000'] as { tasks: Task[] }).tasks
const truth = new Map(tasks.map((t) => [t.id, { stage: t.stage!, check: t.check_state ?? null }]))
const titleOf = new Map(tasks.map((t) => [t.id, t.title]))
const wordOf = (id: string) => stageVisual(truth.get(id)!.stage).word
/** The check marker's sentence, or null where none shows (no check, or a passed one). */
const sentenceOf = (id: string) => checkMarker(truth.get(id)!.check as CheckState | null, truth.get(id)!.stage)?.title ?? null

/** The stage words and check sentences shown inside *scope*, in order. */
function shown(scope: HTMLElement) {
  return {
    words: Array.from(scope.querySelectorAll('.aw-stage-word-text, .aw-st-node-stage-word')).map((n) => n.textContent),
    checks: Array.from(scope.querySelectorAll('.aw-check-marker')).map((n) => n.getAttribute('aria-label')),
  }
}

function expectWords(scope: HTMLElement, id: string) {
  const { words, checks } = shown(scope)
  expect(words).toEqual([wordOf(id)])
  expect(checks).toEqual(sentenceOf(id) ? [sentenceOf(id)] : [])
}

describe('the recorded responses', () => {
  it('hold a task in Landing checks and one in Pre-review checks, with their words', () => {
    expect(truth.get(LANDING)!.stage).toBe('checking')
    expect(truth.get(PRE_REVIEW)).toEqual({ stage: 'pre_review_checks', check: { kind: 'pre_review', state: 'waiting' } })
    expect(wordOf(LANDING)).toBe('Landing checks')
    expect(wordOf(PRE_REVIEW)).toBe('Pre-review checks')
    expect(sentenceOf(PRE_REVIEW)).toBeTruthy()
  })
})

describe('each surface, from its own route, words each task as the task list does', () => {
  it('the dependency map, a prerequisite included', () => {
    const { container } = render(
      <DependencyMapView tasks={tasks} documents={[{ id: 'spdoc-everyroute', title: 'Every route', path: 'spec/x' }]} onOpenTask={() => {}} onOpenDocument={() => {}} />,
    )
    for (const id of recorded.ids) {
      const node = Array.from(container.querySelectorAll<HTMLElement>('.aw-st-node')).find((n) => n.textContent?.includes(titleOf.get(id)!))!
      expect(node, id).toBeTruthy()
      expectWords(node, id)
    }
    expect(container.textContent).not.toMatch(/\bChecking\b/)
  })

  it('the build view', () => {
    const read = routes['/project/builds/build-everyroute1/tasks'] as BuildRead
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <BuildView read={read} status="ready" now={new Date(read.as_of)} address={NO_ADDRESS} onAddressChange={vi.fn()} onRetry={vi.fn()} onOpenDocument={vi.fn()} onOpenConversation={vi.fn()} />
      </QueryClientProvider>,
    )
    const words = Array.from(container.querySelectorAll('.aw-bv-stage-word')).map((n) => n.textContent)
    expect(new Set(words)).toEqual(new Set(recorded.ids.map(wordOf)))
  })

  it('the Running panel, its landing rows and its workers', () => {
    const builds = (routes['/project/builds'] as { builds: ProjectBuildRow[] }).builds
    const loops = routes['/loops'] as LoopSummary[]
    const items = runningItems({ builds, loops, jobs: [], now: new Date() })
    render(<RunningTab items={items} colorIndexOf={() => 0} onOpen={() => {}} onAttend={() => {}} />)
    expectWords(screen.getByTestId(`running-landing-${LANDING}`), LANDING)
    const workers = Array.from(document.querySelectorAll<HTMLElement>('.aw-run-worker'))
    for (const entry of loops.flatMap((l) => l.current_tasks ?? []).filter((t) => t.agent)) {
      const worker = workers.find((w) => w.textContent?.includes(entry.title))!
      expect(worker, entry.id).toBeTruthy()
      expectWords(worker, entry.id)
    }
  })

  it('the Loop tab', () => {
    const loop = routes['/loops/loop-narrow'] as LoopDetail
    expect(loop.current_tasks?.length).toBeGreaterThan(0)
    vi.mocked(useLoop).mockReturnValue({ data: loop, isLoading: false, isError: false } as never)
    render(<LoopTab loopId="loop-narrow" onClose={vi.fn()} />)
    const rows = screen.getAllByTestId('loop-tab-current-task')
    loop.current_tasks!.forEach((entry, n) => {
      expectWords(rows[n]!, entry.id)
      expect(rows[n]!.textContent).not.toContain(`(${entry.status})`)
    })
  })

  it('the Overview, both tabs', () => {
    const running = (routes['/overview'] as { running: OverviewRunning[] }).running
    // As `OverviewScreen` maps the read's running rows.
    const activity: DashActivity[] = running.map((r) => ({
      id: `run-${r.run_id}`,
      agent: r.agent,
      what: r.what,
      outcome: 'running',
      at: r.started_at,
      stage: r.stage ?? null,
      check: r.check_state ?? null,
      onOpen: () => {},
    }))
    const now = new Date()
    const main = { state: 'unknown' } as never
    const dash = render(
      <OverviewDashboard projectName="P" needs={[]} running={activity} finished={[]} finishedToday={null} spend={null} main={main} builds={[]} onNavigate={() => {}} now={now} />,
    )
    for (const r of running.filter((x) => x.task_id)) {
      const row = within(dash.container).getByRole('button', { name: new RegExp(`^builder: ${r.what} \\(${wordOf(r.task_id!)}\\)`) })
      expectWords(row, r.task_id!)
    }
    dash.unmount()
    const brief = render(
      <OverviewBriefing projectName="P" lastSeenAt={null} needs={[]} running={activity} finished={[]} finishedToday={null} spend={null} main={main} builds={[]} onNavigate={() => {}} now={now} />,
    )
    for (const r of running.filter((x) => x.task_id)) {
      const line = within(brief.container).getByRole('button', { name: new RegExp(`^builder: ${r.what},`) }).closest('li')!
      expectWords(line as HTMLElement, r.task_id!)
    }
  })

  it("the spec page's tasks, outline and builds", () => {
    const docTasks = (routes['/tasks?spec_document_id=spdoc-everyroute'] as { tasks: Task[] }).tasks
    const views = docTasks.map((t) => specTaskOf({ key: t.id, title: t.title, description: '', depends_on: [], requirements: [] }, t, (k) => k))
    for (const view of views) {
      const { container, unmount } = render(<ThreadTaskCard task={view} all={views} />)
      expectWords(container, view.key)
      unmount()
    }
    const doc = { kind: 'change-spec', requirements: [], tasks: views, openQuestions: [], slices: [] } as unknown as SpecDocumentView
    const outline = render(<SpecOutlineRail doc={doc} findings={[]} builds={[]} active={null} onJump={() => {}} />)
    for (const view of views) {
      const item = within(outline.container).getByTitle(`${view.title}: ${wordOf(view.key)}`)
      expect(item.querySelector('.aw-sp-outline-stage')?.getAttribute('aria-label')).toBe(wordOf(view.key))
      const sentence = sentenceOf(view.key)
      expect(Array.from(item.querySelectorAll('.aw-check-marker')).map((n) => n.getAttribute('aria-label'))).toEqual(sentence ? [sentence] : [])
    }
    outline.unmount()
    const build = { id: 'build-everyroute1', state: 'running', driver: 'flow', level: 'reviewed', builders: [], reviewers: [], lead: null, landing: 'main', budget_cap_usd: null, created_at: '2026-11-26T00:00:00Z', stopped_at: null } as unknown as SpecBuild
    render(<SpecBuildsSection builds={buildViews([build], docTasks, {})} canBuild={false} now={new Date()} flash={null} onStartBuild={vi.fn()} onOpenRuns={vi.fn()} onStop={vi.fn()} onCopyLink={vi.fn()} />)
    const meter = screen.getByRole('img', { name: /^Tasks:/ })
    for (const id of recorded.ids) expect(meter.getAttribute('aria-label')).toContain(wordOf(id))
    expect(meter.getAttribute('aria-label')).not.toMatch(/\bChecking\b/)
  })

  it('the dependency map draws a prerequisite from another view by the stage its ref carries', () => {
    const after = tasks.find((t) => t.id === AFTER)!
    expect(after.prerequisites?.[0]).toMatchObject({ id: LANDING, stage: truth.get(LANDING)!.stage })
    // Only the dependent on the map: its prerequisite is drawn from the ref the route gave.
    const { container } = render(<DependencyMapView tasks={[{ ...after, spec_document_id: null }]} documents={[]} onOpenTask={() => {}} onOpenDocument={() => {}} />)
    const node = Array.from(container.querySelectorAll<HTMLElement>('.aw-st-node')).find((n) => n.textContent?.includes(titleOf.get(LANDING)!))!
    expect(node).toBeTruthy()
    expectWords(node, LANDING)
  })
})

describe('never colour alone (FR-12): every stage and every check state is named', () => {
  const STATES = ['waiting', 'running', 'passed', 'failed', 'could_not_run'] as const
  const KINDS = ['pre_review', 'landing'] as const
  for (const stage of Object.keys(STAGE_LABELS)) {
    it(`words ${stage} with each check state, on the shared stage word and on a map node`, () => {
      const glyphs = new Set<string>()
      for (const kind of KINDS)
        for (const state of STATES) {
          const check = { kind, state }
          for (const glyphOnly of [false, true]) {
            const { container, unmount } = render(<TaskStageWord stage={stage} check={check} glyphOnly={glyphOnly} />)
            expect(container.querySelector('.aw-stage-word-text')?.textContent).toBe(stageVisual(stage).word)
            expect(container.querySelector('.aw-stage-word svg')).not.toBeNull()
            const marker = container.querySelector('.aw-check-marker')
            if (state === 'passed') expect(marker).toBeNull()
            else {
              expect(marker?.getAttribute('aria-label')).toBe(checkMarker(check, stage)!.title)
              expect(marker?.querySelector('svg')).not.toBeNull()
              if (!glyphOnly) expect(marker?.textContent).toBe(checkMarker(check, stage)!.text)
              else glyphs.add(`${state}:${checkMarker(check, stage)!.glyph}`)
            }
            unmount()
          }
          const map = render(
            <DependencyMapView tasks={[{ ...tasks[0]!, id: 'x', title: 'X', prerequisites: [], stage, check_state: check, spec_document_id: null }]} documents={[]} onOpenTask={() => {}} onOpenDocument={() => {}} />,
          )
          expect(map.container.querySelector('.aw-st-node-stage-word')?.textContent).toBe(stageVisual(stage).word)
          map.unmount()
        }
      // On the dense surfaces each shown check state has one glyph of its own, whatever its kind.
      const byState = new Map([...glyphs].map((g) => g.split(':') as [string, string]))
      expect(byState.size).toBe(STATES.length - 1)
      expect(new Set(byState.values()).size).toBe(STATES.length - 1)
      expect(glyphs.size).toBe(STATES.length - 1)
    })
  }
})
