import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SpecHome } from '@/components/spec/home/SpecHome'
import { homeBuilds, homeCapabilities, latestFinished } from '@/components/spec/home/homeModel'
import { CapabilityTouchedList } from '@/components/spec/CapabilityTouchedList'
import type { ProjectBuildRow } from '@/api/projectBuilds'
import type { SpecDocumentRecord } from '@/api/spec'

const doc = (n: string) => `spec/changes/${n}/spec.json`
const cap = (n: string) => `spec/capabilities/${n}/spec.json`
const NOW = new Date('2026-11-17T12:00:00Z')

/** A row as `GET /project/builds` returns it. */
function row(id: string, name: string, state: ProjectBuildRow['state'], over: Partial<ProjectBuildRow> = {}): ProjectBuildRow {
  return {
    id,
    document_id: `spdoc-${name}`,
    document_title: `${name} change`,
    document_path: doc(name),
    finished_at: state === 'finished' ? '2026-11-17T10:00:00Z' : null,
    roadmap: null,
    capabilities: [],
    state,
    driver: 'flow',
    level: 'reviewed',
    lead: null,
    loop_id: null,
    loop: null,
    tasks_total: 3,
    tasks_done: 1,
    tasks_landing: 0,
    landings: [],
    spent_usd: 1.5,
    stop_reason: null,
    created_at: '2026-11-17T09:00:00Z',
    stopped_at: null,
    open_questions: 0,
    question: null,
    ...over,
  } as ProjectBuildRow
}

/** Newest build first, as the route returns them. Twelve older finished builds follow. */
const ROUTE_ORDER: ProjectBuildRow[] = [
  row('b9', 'zulu', 'running', { created_at: '2026-11-17T11:30:00Z', tasks_landing: 2 }),
  row('b8', 'yankee', 'running', { created_at: '2026-11-17T11:00:00Z' }),
  row('b7', 'xray', 'finished', {
    finished_at: '2026-11-17T10:50:00Z',
    spent_usd: null,
    roadmap: { path: doc('rho'), title: 'Rho roadmap', slice: { key: 's2', title: 'Slice two' } },
    capabilities: [{ path: cap('cobalt'), title: 'Cobalt cap' }],
  }),
  row('b6', 'whiskey', 'stopped', { finished_at: null, stopped_at: '2026-11-17T10:40:00Z' }),
  row('b5', 'xray', 'finished', { finished_at: '2026-11-17T10:00:00Z' }),
  ...Array.from({ length: 12 }, (_, i) => row(`o${i}`, `old${i}`, 'finished', { finished_at: `2026-11-${String(16 - i).padStart(2, '0')}T08:00:00Z` })),
]

function show(builds = homeBuilds(ROUTE_ORDER)) {
  const onOpen = vi.fn()
  render(
    <SpecHome
      builds={builds}
      capabilities={[
        { path: cap('cobalt'), title: 'Cobalt cap', waiting: 2 },
        { path: cap('ember'), title: 'Ember cap', waiting: 0 },
      ]}
      now={NOW}
      onOpen={onOpen}
    />,
  )
  return onOpen
}

describe('the Spec home', () => {
  it('lists running builds newest first with their facts', () => {
    show()
    const rows = screen.getAllByTestId('spec-home-build-row')
    expect(rows.map((r) => r.getAttribute('data-document'))).toEqual([doc('zulu'), doc('yankee')])
    expect(rows[0]).toHaveTextContent('1 of 3 done')
    expect(rows[0]).toHaveTextContent('2 waiting to land')
    expect(rows[0]).toHaveTextContent('started 30m')
  })

  it('says nothing is being built, and nothing built yet', () => {
    render(<SpecHome builds={[]} capabilities={[]} now={NOW} onOpen={vi.fn()} />)
    expect(screen.getByTestId('spec-home-building')).toHaveTextContent('Nothing is being built')
    expect(screen.getByTestId('spec-home-recent')).toHaveTextContent('Nothing has been built yet')
  })

  it('shows ten finished builds, newest finish first, each document once, no stopped build, unpriced as unpriced', () => {
    show()
    const rows = screen.getAllByTestId('spec-home-recent-row')
    expect(rows).toHaveLength(10)
    const docs = rows.map((r) => r.getAttribute('data-document'))
    expect(new Set(docs).size).toBe(10)
    expect(docs).not.toContain(doc('whiskey'))
    const stamps = rows.map((r) => r.getAttribute('data-finished-at')!)
    expect(stamps).toEqual([...stamps].sort().reverse())
    // xray finished twice: its latest finish (10:50, unpriced) is the one shown
    expect(docs[0]).toBe(doc('xray'))
    expect(stamps[0]).toBe('2026-11-17T10:50:00Z')
    expect(rows[0]).toHaveTextContent('unpriced')
  })

  it('names the roadmap, slice and capabilities as links, or says not in a roadmap', async () => {
    const onOpen = show()
    const first = screen.getAllByTestId('spec-home-recent-row')[0]
    const links = within(first).getAllByTestId('spec-home-link')
    expect(links.map((l) => l.getAttribute('data-rel'))).toEqual(['roadmap', 'slice', 'capability'])
    await userEvent.click(links[1])
    expect(onOpen).toHaveBeenLastCalledWith(doc('rho'), 'slice-s2')
    await userEvent.click(links[2])
    expect(onOpen).toHaveBeenLastCalledWith(cap('cobalt'))
    expect(within(screen.getAllByTestId('spec-home-build-row')[0]).getByText('Not in a roadmap')).toBeInTheDocument()
  })

  it('draws a thread per relation, tells a running build from a finished one, and a capability box opens', async () => {
    const builds = homeBuilds([
      row('x', 'x', 'running', { roadmap: { path: doc('r'), title: 'R roadmap', slice: { key: 's', title: 'S' } }, capabilities: [{ path: cap('c'), title: 'C cap' }] }),
      row('f', 'f', 'finished', { capabilities: [{ path: cap('c'), title: 'C cap' }] }),
    ])
    const onOpen = show(builds)
    const map = screen.getByTestId('spec-home-relations')
    const threads = [...map.querySelectorAll('.aw-map-thread')]
    expect(threads.map((t) => t.getAttribute('data-state'))).toEqual(['running', 'running', 'finished'])
    await userEvent.click(within(map).getByText('C cap'))
    expect(onOpen).toHaveBeenLastCalledWith(cap('c'))
  })

  it('lights what a hovered thing connects to, dims the rest, and clears on leaving', async () => {
    const builds = homeBuilds([
      row('x', 'x', 'running', { roadmap: { path: doc('r'), title: 'R roadmap', slice: { key: 's', title: 'S' } }, capabilities: [{ path: cap('c'), title: 'C cap' }] }),
      row('y', 'y', 'running', { capabilities: [{ path: cap('d'), title: 'D cap' }] }),
    ])
    show(builds)
    expect(document.querySelectorAll('[data-lit]')).toHaveLength(0)
    const box = document.querySelector('.aw-map-node[data-col=capability]') as HTMLElement
    expect(box).toHaveTextContent('C cap')
    await userEvent.hover(box)
    const nodes = [...document.querySelectorAll('.aw-map-node')].map((n) => [n.textContent, n.getAttribute('data-lit')])
    expect(nodes).toEqual([
      ['R roadmap', 'true'],
      ['x change', 'true'],
      ['y change', 'false'],
      ['C cap', 'true'],
      ['D cap', 'false'],
    ])
    const rows = screen.getAllByTestId('spec-home-build-row')
    expect(rows.map((r) => r.getAttribute('data-lit'))).toEqual(['true', 'false'])
    await userEvent.unhover(box)
    expect(document.querySelectorAll('[data-lit]')).toHaveLength(0)
    await userEvent.hover(rows[0])
    expect(screen.getAllByTestId('spec-home-capability-row').length).toBe(2)
    expect(document.querySelector('.aw-map-node[data-col=capability][data-lit=true]')).toHaveTextContent('C cap')
  })

  it('lights the builds and roadmap a hovered Capabilities row connects to, and clears on leaving', async () => {
    const builds = homeBuilds([
      row('x', 'x', 'running', { roadmap: { path: doc('r'), title: 'R roadmap', slice: { key: 's', title: 'S' } }, capabilities: [{ path: cap('c'), title: 'C cap' }] }),
      row('y', 'y', 'running', { capabilities: [{ path: cap('d'), title: 'D cap' }] }),
    ])
    const onOpen = vi.fn()
    render(
      <SpecHome
        builds={builds}
        capabilities={[
          { path: cap('c'), title: 'C cap', waiting: 0 },
          { path: cap('d'), title: 'D cap', waiting: 0 },
        ]}
        now={NOW}
        onOpen={onOpen}
      />,
    )
    const capRows = screen.getAllByTestId('spec-home-capability-row')
    await userEvent.hover(capRows[0])
    expect(screen.getAllByTestId('spec-home-build-row').map((r) => r.getAttribute('data-lit'))).toEqual(['true', 'false'])
    expect([...document.querySelectorAll('.aw-map-node')].map((n) => [n.textContent, n.getAttribute('data-lit')])).toEqual([
      ['R roadmap', 'true'],
      ['x change', 'true'],
      ['y change', 'false'],
      ['C cap', 'true'],
      ['D cap', 'false'],
    ])
    expect(capRows.map((c) => c.getAttribute('data-lit'))).toEqual(['true', 'false'])
    await userEvent.unhover(capRows[0])
    expect(document.querySelectorAll('[data-lit]')).toHaveLength(0)
    await userEvent.tab()
    expect(document.querySelectorAll('[data-lit=true]').length).toBeGreaterThan(0)
  })

  it('lights a capability row in Capabilities when its build is hovered', async () => {
    show()
    await userEvent.hover(screen.getAllByTestId('spec-home-recent-row')[0])
    const caps = screen.getAllByTestId('spec-home-capability-row')
    expect(caps.map((c) => c.getAttribute('data-lit'))).toEqual(['true', 'false'])
  })

  it('lists every capability with its waiting count, the untouched one too, and opens it', async () => {
    const onOpen = show()
    const rows = screen.getAllByTestId('spec-home-capability-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('2 waiting')
    expect(rows[1]).not.toHaveTextContent('waiting')
    await userEvent.click(rows[1])
    expect(onOpen).toHaveBeenLastCalledWith(cap('ember'))
  })

  it('leaves a running build and a stopped one out of what was built', () => {
    const built = homeBuilds(ROUTE_ORDER)
    expect(latestFinished(built, 20).every((b) => b.state === 'finished')).toBe(true)
    expect(built.some((b) => b.document.path === doc('whiskey'))).toBe(false)
  })

  it('takes the current capabilities, with their waiting counts', () => {
    const docs = [
      { kind: 'capability', phase: 'current', path: cap('a'), title: 'A', waiting_count: 3 },
      { kind: 'capability', phase: 'archived', path: cap('b'), title: 'B' },
      { kind: 'change-spec', phase: 'approved', path: doc('c'), title: 'C' },
    ] as SpecDocumentRecord[]
    expect(homeCapabilities(docs)).toEqual([{ path: cap('a'), title: 'A', waiting: 3 }])
  })
})

describe("a capability's touched-by list", () => {
  const record = {
    path: cap('t'),
    kind: 'capability',
    waiting_changes: [{ path: doc('t3'), title: 'T3', phase: 'approved', built: false, first_approved_at: '2026-11-16T00:00:00Z' }],
    // the route's order: newest fold first
    folded_changes: [
      { path: doc('t2'), title: 'T2', folded_at: '2026-11-15T00:00:00Z' },
      { path: doc('t1'), title: 'T1', folded_at: '2026-11-10T00:00:00Z' },
    ],
  } as unknown as SpecDocumentRecord

  it('merges waiting and folded newest first, each marked and linked', async () => {
    const onOpen = vi.fn()
    render(<CapabilityTouchedList record={record} onOpenDocument={onOpen} />)
    const rows = screen.getAllByTestId('capability-touched-row')
    expect(rows.map((r) => [r.getAttribute('data-path'), r.getAttribute('data-state')])).toEqual([
      [doc('t3'), 'waiting'],
      [doc('t2'), 'folded'],
      [doc('t1'), 'folded'],
    ])
    expect(rows[1]).toHaveTextContent('Nov 15')
    for (const r of rows) {
      await userEvent.click(within(r).getByRole('button'))
      expect(onOpen).toHaveBeenLastCalledWith(r.getAttribute('data-path'))
    }
  })
})
