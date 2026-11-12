import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { chooseMenuOption } from './support/menuSelect'
import type { Job, LoopSummary } from '@/api/jobs'
import type { ProjectBuildRow } from '@/api/projectBuilds'
import { RunningTab } from '@/components/panel/RunningTab'
import { groupItems, matchesFilter, runningItems, type RunningItem } from '@/components/panel/runningModel'

/* The side panel's Running tab (`the-side-panel-s-running-tab`): the model over fixtures written in
 * the order the routes return them (builds newest first, as `GET /project/builds` does; loops and
 * jobs as their list routes do), and the component drawing the rows it derives. */

afterEach(cleanup)

const NOW = new Date('2026-11-12T12:00:00Z')
const ago = (hours: number) => new Date(NOW.getTime() - hours * 3600_000).toISOString()
const inMinutes = (m: number) => new Date(NOW.getTime() + m * 60_000).toISOString()

function build(key: string, overrides: Partial<ProjectBuildRow> = {}): ProjectBuildRow {
  return {
    id: `build-${key}`,
    document_id: `spdoc-${key}`,
    document_title: `Document ${key}`,
    state: 'running',
    driver: 'flow',
    level: 'reviewed',
    lead: null,
    loop_id: null,
    loop: null,
    tasks_total: 0,
    tasks_done: 0,
    spent_usd: null,
    stop_reason: null,
    created_at: ago(1),
    stopped_at: null,
    open_questions: 0,
    question: null,
    ...overrides,
  }
}

function loop(key: string, overrides: Partial<LoopSummary> = {}): LoopSummary {
  return {
    id: `loop-${key}`,
    label: `Loop ${key}`,
    purpose: '',
    stop_when_queue_empties: true,
    ending_state: null,
    queue: {},
    open_questions: 0,
    firing_active: false,
    ...overrides,
  } as LoopSummary
}

function job(key: string, overrides: Partial<Job> = {}): Job {
  return {
    id: `job-${key}`,
    project_id: 'p',
    name: `Job ${key}`,
    agent: 'dev',
    message: 'm',
    cron: '*/10 * * * *',
    session_mode: 'new',
    enabled: true,
    source: 'hub',
    created_at: ago(100),
    run_count: 0,
    ...overrides,
  } as Job
}

/** A flow build (with its loop and the loop's job), a lead build, an ended build, a plain loop
 *  and a plain job: five pieces of work, eight records. */
function fiveThings() {
  const flowLoop = loop('flow', { queue: { approved: 1, pending: 1 } })
  const plainLoop = loop('plain')
  return {
    builds: [
      build('flow', { loop_id: flowLoop.id, tasks_total: 2, tasks_done: 1 }),
      build('lead', { driver: 'lead', lead: 'arch' }),
      build('done', { state: 'finished', stopped_at: ago(24) }),
    ],
    loops: [flowLoop, plainLoop],
    jobs: [job('flowjob', { loop: flowLoop }), job('plainloopjob', { loop: plainLoop }), job('plain')],
    now: NOW,
  }
}

function renderTab(items: RunningItem[], handlers: { onOpen?: (i: RunningItem) => void; onAttend?: (i: RunningItem) => void } = {}) {
  return render(<RunningTab items={items} colorIndexOf={() => 0} onOpen={handlers.onOpen ?? vi.fn()} onAttend={handlers.onAttend ?? vi.fn()} />)
}

const rows = () => Array.from(document.querySelectorAll<HTMLElement>('[data-slot="running-row"]'))
const headings = () => screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
const showAll = () => fireEvent.click(screen.getByRole('radio', { name: /^All/ }))

describe('Running lists each piece of work once (FR-2)', () => {
  it('ac-once: five rows with All selected; a build loop and a loop job are not listed apart', () => {
    const items = runningItems(fiveThings())
    expect(items.map((i) => [i.kind, i.title])).toEqual([
      ['build', 'Document flow'],
      ['build', 'Document lead'],
      ['build', 'Document done'],
      ['loop', 'Loop plain'],
      ['job', 'Job plain'],
    ])
    renderTab(items)
    showAll()
    expect(rows()).toHaveLength(5)
  })

  it('ac-ended-builds: a finished and a stopped-early build appear under Finished and Stopped early with when they ended', () => {
    const items = runningItems({
      builds: [
        build('yesterday', { state: 'finished', stopped_at: ago(24) }),
        build('early', { state: 'stopped', stop_reason: 'stopped by the operator', stopped_at: ago(40) }),
      ],
      loops: [],
      jobs: [],
      now: NOW,
    })
    renderTab(items)
    fireEvent.click(screen.getByRole('radio', { name: /^Finished/ }))
    expect(headings()).toEqual(['Finished1', 'Stopped early1'])
    expect(within(screen.getByRole('region', { name: 'Finished' })).getByText('ended 1d ago')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Stopped early' })).getByText('ended 2d ago')).toBeInTheDocument()
  })
})

describe('Running groups what needs the operator first (FR-3, FR-4)', () => {
  it('ac-order: one item per group reads Needs you to Stopped early, each with count 1', () => {
    const items = runningItems({
      builds: [
        build('stopped', { state: 'stopped', stopped_at: ago(5) }),
        build('finished', { state: 'finished', stopped_at: ago(3) }),
        build('asks', { open_questions: 1, question: { id: 'q1', question: 'Which?', from_agent: 'dev', conversation_id: 'c1', created_at: ago(1) } }),
        build('working', { loop_id: 'loop-working' }),
        build('between', { loop_id: 'loop-between' }),
      ],
      loops: [loop('working', { firing_active: true }), loop('between')],
      jobs: [job('scheduled'), job('paused', { enabled: false })],
      now: NOW,
    })
    renderTab(items)
    showAll()
    expect(headings()).toEqual(['Needs you1', 'Working now1', 'Between steps1', 'Scheduled1', 'Paused1', 'Finished1', 'Stopped early1'])
  })

  it('ac-question: a running build with an open question is under Needs you, saying so, and Answer attends it', () => {
    const onAttend = vi.fn()
    const items = runningItems({
      builds: [build('asks', { open_questions: 1, question: { id: 'q1', question: 'Which database?', from_agent: 'dev', conversation_id: 'conv-9', created_at: ago(1) } })],
      loops: [],
      jobs: [],
      now: NOW,
    })
    renderTab(items, { onAttend })
    const group = screen.getByRole('region', { name: 'Needs you' })
    expect(within(group).getByText('A question is waiting for your answer')).toBeInTheDocument()
    fireEvent.click(within(group).getByRole('button', { name: 'Answer' }))
    expect(onAttend).toHaveBeenCalledWith(expect.objectContaining({ kind: 'build', questionId: 'q1' }))
    expect(onAttend.mock.calls[0][0].attention.kind).toBe('question')
  })

  it('ac-stall: a loop whose next firing the Hub would refuse is under Needs you with the Hub reason and a Look button', () => {
    const onAttend = vi.fn()
    const items = runningItems({
      builds: [],
      loops: [loop('stuck', { stall_reason: 'No agent is free to take the next task' })],
      jobs: [],
      now: NOW,
    })
    renderTab(items, { onAttend })
    const group = screen.getByRole('region', { name: 'Needs you' })
    expect(within(group).getByText('No agent is free to take the next task')).toBeInTheDocument()
    fireEvent.click(within(group).getByRole('button', { name: 'Look' }))
    expect(onAttend).toHaveBeenCalledWith(expect.objectContaining({ kind: 'loop', loopId: 'loop-stuck' }))
  })

  it('a build whose loop would be refused reads the same stall, and an ended build never needs you', () => {
    const items = runningItems({
      builds: [build('flow', { loop_id: 'loop-flow' }), build('over', { state: 'finished', stopped_at: ago(2), open_questions: 1 })],
      loops: [loop('flow', { stall_reason: 'Waiting for a reviewer' })],
      jobs: [],
      now: NOW,
    })
    expect(items.map((i) => [i.title, i.phase, i.attention?.text ?? null])).toEqual([
      ['Document flow', 'needs-you', 'Waiting for a reviewer'],
      ['Document over', 'finished', null],
    ])
  })
})

describe('a row says what is happening (FR-5, FR-6)', () => {
  it('ac-row: title, Build, started, 3/7 tasks, $4.20, two workers and "and 1 more"', () => {
    const current = (n: number, agent: string, capacity: 'working' | 'next', status = 'in_progress') => ({
      id: `t${n}`,
      title: `Task ${n}`,
      status,
      agent,
      agent_capacity: capacity,
    })
    const items = runningItems({
      builds: [build('big', { document_title: 'The big change', loop_id: 'loop-big', tasks_total: 7, tasks_done: 3, spent_usd: 4.2, created_at: ago(2) })],
      loops: [loop('big', { firing_active: true, current_tasks: [current(4, 'dev', 'working'), current(5, 'qa', 'working', 'under_review'), current(6, 'arch', 'next', 'pending')] })],
      jobs: [],
      now: NOW,
    })
    renderTab(items)
    const row = screen.getByTitle('Open The big change')
    const text = row.textContent ?? ''
    expect(text).toContain('The big change')
    expect(text).toContain('Build')
    expect(text).toContain('started 2h ago')
    expect(text).toContain('3/7 tasks')
    expect(text).toContain('$4.20')
    expect(within(row).getByText('Task 4')).toBeInTheDocument()
    expect(within(row).getByText('Task 5')).toBeInTheDocument()
    expect(within(row).queryByText('Task 6')).not.toBeInTheDocument()
    expect(within(row).getByText('and 1 more')).toBeInTheDocument()
  })

  it('ac-words: a paused weekly job reads "On its own schedule, paused", with no cron text or id anywhere', () => {
    const items = runningItems({ builds: [], loops: [], jobs: [job('weekly', { cron: '0 9 * * 1', enabled: false })], now: NOW })
    const { container } = renderTab(items)
    expect(screen.getByText('On its own schedule, paused')).toBeInTheDocument()
    const text = container.textContent ?? ''
    expect(text).not.toMatch(/\d+\s+[\d*/]+\s+[\d*/]+\s+[\d*/]+\s+[\d*/-]+/)
    expect(text).not.toMatch(/\b(job|loop|build|spdoc|task)-[a-z0-9]+/i)
  })

  it('a schedule the app can say reads in words, and a scheduled loop says when it is next', () => {
    const items = runningItems({
      builds: [],
      loops: [loop('plain')],
      jobs: [job('daily', { cron: '30 6 * * *' }), job('l', { loop: loop('plain'), next_run: inMinutes(4) })],
      now: NOW,
    })
    expect(items.find((i) => i.kind === 'job')?.status).toBe('Daily at 06:30 UTC')
    expect(items.find((i) => i.kind === 'loop')?.when).toBe('next in 4m')
  })
})

describe('Running filters (FR-7)', () => {
  it('ac-filter: Finished then Jobs shows only ended jobs, the counts follow the kind filter, and none says nothing has finished', async () => {
    const items = runningItems({
      builds: [build('done', { state: 'finished', stopped_at: ago(5) })],
      loops: [],
      jobs: [job('live'), job('old', { archived_at: ago(30) })],
      now: NOW,
    })
    expect(items.map((i) => i.phase)).toEqual(['finished', 'scheduled', 'finished'])
    renderTab(items)
    fireEvent.click(screen.getByRole('radio', { name: /^Finished/ }))
    expect(rows()).toHaveLength(2)
    await chooseMenuOption(userEvent.setup(), /Kind of work/, /Jobs/)
    expect(rows().map((r) => r.getAttribute('title'))).toEqual(['Open Job old'])
    expect(screen.getByRole('radio', { name: /^Now/ })).toHaveTextContent('1')
    expect(screen.getByRole('radio', { name: /^Finished/ })).toHaveTextContent('1')
  })

  it('says nothing has finished rather than drawing an empty box', () => {
    renderTab(runningItems({ builds: [], loops: [], jobs: [job('live')], now: NOW }))
    fireEvent.click(screen.getByRole('radio', { name: /^Finished/ }))
    expect(screen.getByText('Nothing has finished yet.')).toBeInTheDocument()
    expect(rows()).toHaveLength(0)
  })

  it('defaults to Now: ended work is not listed until Finished or All', () => {
    const items = runningItems(fiveThings())
    const now = items.filter((i) => matchesFilter(i, 'now', 'any'))
    expect(now).toHaveLength(4)
    expect(groupItems(now).map((g) => g.phase)).not.toContain('finished')
    renderTab(items)
    expect(rows()).toHaveLength(4)
  })
})

describe('Running rows open their item (FR-8)', () => {
  it('selecting a row hands the item to the host', () => {
    const onOpen = vi.fn()
    renderTab(runningItems(fiveThings()), { onOpen })
    showAll()
    fireEvent.click(screen.getByTitle('Open Document flow'))
    fireEvent.click(screen.getByTitle('Open Loop plain'))
    fireEvent.click(screen.getByTitle('Open Job plain'))
    expect(onOpen.mock.calls.map(([i]) => [i.kind, i.documentId, i.loopId])).toEqual([
      ['build', 'spdoc-flow', 'loop-flow'],
      ['loop', null, 'loop-plain'],
      ['job', null, null],
    ])
  })
})
