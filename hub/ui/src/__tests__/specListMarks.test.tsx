import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecDocList } from '@/components/spec/page/SpecDocList'
import { SpecOpenPicker } from '@/components/spec/page/SpecOpenPicker'
import { SpecListFooter } from '@/components/spec/SpecListFooter'
import { listEntries } from '@/components/spec/page/adapt'
import { DEFAULT_LIST_PREFERENCES, type ListPreferences } from '@/components/spec/page/model'
import type { SpecDocumentRecord, SpecEntry } from '@/api/spec'

/**
 * `the-spec-header-redesigned`, FR-8, FR-10, FR-11: every list of specs marks a state with its own
 * icon (set 2), the 'What needs you' order groups by the route's waiting reasons, and the defects
 * report starts folded. Fed `GET /documents` payloads through `listEntries`, as the page is.
 */
vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDefects: () => ({
      data: {
        changes: [
          {
            document_id: 'd1',
            path: 'spec/changes/x/spec.json',
            title: 'X',
            phase: 'approved',
            defects: [
              { caught_by: 'review', summary: 'a' },
              { caught_by: 'drive', summary: 'b' },
            ],
            by_step: { review: 1, drive: 1 },
          },
        ],
      },
      error: null,
    }),
    useRecordDefect: () => ({ mutate: vi.fn(), isPending: false }),
    useProjectJourney: () => ({ data: { steps: [], diagnostics: [] }, error: null }),
  }
})

const NOW = new Date('2026-11-02T13:00:00Z')
const CAP = 'spec/capabilities/cap/spec.json'
const path = (name: string) => `spec/changes/${name}/spec.json`
const entry = (name: string, kind = 'change-spec', p = path(name)): SpecEntry =>
  ({ path: p, phase: 'approved', document_id: `id-${name}`, kind, title: name }) as SpecEntry
const rec = (name: string, extra: Partial<SpecDocumentRecord> = {}, p = path(name)) =>
  ({ id: `id-${name}`, path: p, title: name, kind: 'change-spec', phase: 'approved', display_phase: 'approved', updated_at: '2026-11-02T12:00:00Z', ...extra }) as SpecDocumentRecord

// One document in each state, carrying the reasons the route gives for waiting on the operator.
const DOCS: Array<{ name: string; record: Partial<SpecDocumentRecord> }> = [
  { name: 'ready-doc', record: { phase: 'exploring', waiting: ['ready_to_approve'] } },
  { name: 'amended', record: { waiting: ['amendments_to_review'], amendments: { total: 2, unreviewed: 2 } } },
  { name: 'unstarted', record: { waiting: ['ready_to_build'] } },
  { name: 'finished', record: { display_phase: 'done', waiting: ['ready_to_fold'] } },
  { name: 'gap-doc', record: { phase: 'exploring' } },
  { name: 'building-doc', record: { display_phase: 'building', build: { id: 'b', done: 1, total: 3 } } },
  { name: 'archived-doc', record: { phase: 'archived' } },
]

function build() {
  const specs = [...DOCS.map((d) => entry(d.name)), entry('cap', 'capability', CAP)]
  const records = [
    ...DOCS.map((d) => rec(d.name, d.record)),
    rec('cap', { phase: 'current', display_phase: 'current', kind: 'capability' }, CAP),
  ]
  // The list route never says `ready` itself (a clean exploring document waits as ready_to_approve), but a ready state still gets its own mark.
  return listEntries(specs, records).map((e) => (e.path === path('ready-doc') ? { ...e, state: 'ready' as const, shown: 'ready' as const } : e))
}

const prefs = (over: Partial<ListPreferences> = {}): ListPreferences => ({ ...DEFAULT_LIST_PREFERENCES, ...over })
const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>)
const list = (over: Partial<ListPreferences> = {}) =>
  wrap(<SpecDocList entries={build()} active={null} prefs={prefs(over)} onPrefsChange={vi.fn()} onOpen={vi.fn()} onNew={vi.fn()} now={NOW} />)
const picker = (over: Partial<ListPreferences> = {}) =>
  wrap(
    <SpecOpenPicker
      entries={build()}
      prefs={prefs(over)}
      onPrefsChange={vi.fn()}
      onOpen={vi.fn()}
      onNew={vi.fn()}
      now={NOW}
      attachedPath={path('ready-doc')}
      recent={[path('amended')]}
    />,
  )

const marks = (root: ParentNode = document) => Array.from(root.querySelectorAll<HTMLElement>('.aw-sp-list-mark'))
const iconOf = (mark: HTMLElement) => mark.querySelector('svg')?.outerHTML ?? ''
const rows = () => Array.from(document.querySelectorAll<HTMLElement>('[data-slot="spec-row"]'))

describe('the state marks (FR-10)', () => {
  it('gives every state its own icon in the Spec tab list, with no old dot', () => {
    list()
    const byState = new Map(rows().map((r) => [r.getAttribute('data-state')!, marks(r)[0]]))
    expect([...byState.keys()].sort()).toEqual(['approved', 'archived', 'building', 'current', 'done', 'ready', 'writing'])
    const icons = [...byState.values()].map(iconOf)
    expect(icons.every(Boolean)).toBe(true)
    expect(new Set(icons).size).toBe(7)
    expect(document.querySelector('.aw-sp-list-dot, .aw-sp-list-pill, [data-marker]')).toBeNull()
  })

  it('marks done as the solid disc', () => {
    list()
    const done = marks().find((m) => m.getAttribute('data-state') === 'done')
    expect(done).toBeDefined()
    expect(done!.getAttribute('data-set')).toBeNull()
  })

  it('marks the picker cards and its All specs the same way', () => {
    picker()
    const cards = Array.from(document.querySelectorAll<HTMLElement>('[data-slot="open-card"]'))
    expect(cards).toHaveLength(3) // This conversation, Building now, Recently opened
    for (const card of cards) expect(marks(card)).toHaveLength(1)
    const ready = marks(cards[0])[0]
    const building = marks(cards[1])[0]
    const approved = marks(cards[2])[0]
    expect(ready.getAttribute('data-state')).toBe('ready')
    expect(approved.getAttribute('data-state')).toBe('approved')
    expect(building.getAttribute('data-state')).toBe('building')
    expect(new Set([ready, building, approved].map(iconOf)).size).toBe(3)
    expect(marks()).toHaveLength(cards.length + rows().length)
    expect(document.querySelector('.aw-sp-list-dot')).toBeNull()
  })
})

describe('What needs you (FR-11)', () => {
  const groupsOf = () =>
    Array.from(document.querySelectorAll('.aw-sp-list-group')).map((g) => ({
      label: g.querySelector('.aw-sp-list-label')?.textContent,
      rows: Array.from(g.querySelectorAll('[data-slot="spec-row"] .aw-sp-list-name')).map((n) => n.textContent),
    }))

  const expected = [
    { label: 'Waiting on you', rows: ['ready-doc', 'amended', 'unstarted', 'finished'] },
    { label: 'In progress', rows: ['gap-doc', 'building-doc'] },
    { label: 'Finished', rows: ['archived-doc'] },
    { label: 'Capabilities', rows: ['cap'] },
  ]
  // The order inside a group is most recently changed first, and every fixture changed together.
  const sorted = (groups: ReturnType<typeof groupsOf>) => groups.map((g) => ({ ...g, rows: [...g.rows].sort() }))

  it('groups the Spec tab list by what waits on the operator', () => {
    list({ order: 'attention' })
    expect(sorted(groupsOf())).toEqual(sorted(expected))
  })

  it('groups the panel Open a spec screen the same', () => {
    picker({ order: 'attention' })
    expect(sorted(groupsOf())).toEqual(sorted(expected))
  })

  it('says why beside each waiting document', () => {
    list({ order: 'attention' })
    const reason = (name: string) => screen.getByText(name).closest('button')!.querySelector('.aw-sp-list-waiting')?.textContent
    expect(reason('ready-doc')).toBe('Ready to approve')
    expect(reason('amended')).toBe('2 amendments to review')
    expect(reason('unstarted')).toBe('Ready to build')
    expect(reason('finished')).toBe('Ready to fold')
    expect(reason('gap-doc')).toBeUndefined()
  })
})

describe('the folded defects report (FR-8)', () => {
  it('shows Evidence and one Defects by step line with the count, and no change row', async () => {
    wrap(<SpecListFooter onOpenEvidence={vi.fn()} evidenceOpen={false} evidenceCount={3} evidenceError={false} currentPath={null} onSelect={vi.fn()} />)
    expect(screen.getByTestId('spec-list-evidence')).toHaveTextContent('Evidence')
    const line = screen.getByRole('button', { name: /Defects by step/ })
    expect(within(line).getByTestId('spec-defects-count')).toHaveTextContent('2')
    expect(line).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('spec-defects-row')).toBeNull()
    await userEvent.click(line)
    expect(screen.getByTestId('spec-defects-row')).toHaveTextContent('X')
  })
})
