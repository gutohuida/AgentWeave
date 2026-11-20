import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { RoadmapSliceRow, SpecDocumentRecord } from '@/api/spec'
import { documentView, type SpecPayload } from '@/components/spec/page/adapt'
import { SpecDocumentBody } from '@/components/spec/page/SpecDocumentBody'
import { SpecDocList } from '@/components/spec/page/SpecDocList'
import { DEFAULT_LIST_PREFERENCES, NO_DOCUMENT_FILTERS, type SpecListEntry } from '@/components/spec/page/model'

/**
 * `a-roadmap-that-is-recognisably-a-roadmap`, FR-2, FR-3, FR-4, FR-7..FR-13: the roadmap page's
 * header, cards, offers, edits, done state and retrospective link; the list's progress row; the
 * numbered problem and the evidence section. Fed the route's rows through `documentView`.
 */
const move = vi.fn()
const remove = vi.fn()
const converse = vi.fn()
const take = vi.fn()
const archive = vi.fn()
let spec: { slices: RoadmapSliceRow[] } | undefined

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [{ name: 'Architect' }, { name: 'Developer' }] }) }))
vi.mock('@/api/nextSlice', () => ({
  useNextSliceOffers: () => ({ data: [{ roadmap: 'spec/changes/rm/spec.json', next_slice: { key: 's3' }, agent: 'Architect' }] }),
  useTakeNextSliceOffer: () => ({ mutate: take, isPending: false, error: null }),
  useDeclineNextSliceOffer: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}))
vi.mock('@/api/roadmapEdits', () => ({
  useMoveSlice: () => ({ mutate: move, isPending: false, error: null }),
  useRemoveSlice: () => ({ mutate: remove, isPending: false, error: null }),
  useStartSliceConversation: () => ({ mutate: converse, isPending: false, error: null }),
}))
vi.mock('@/api/specTidy', () => ({ useArchiveBatch: () => ({ mutate: archive, isPending: false, error: null }) }))
vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return { ...actual, useSpec: () => ({ data: spec }) }
})

const RM = 'spec/changes/rm/spec.json'
const row = (key: string, extra: Partial<RoadmapSliceRow> = {}): RoadmapSliceRow => ({
  key,
  title: `Slice ${key}`,
  intent: 'Intent',
  done: 'Done when',
  builds_after: [],
  state: 'Not drafted',
  document: null,
  document_title: null,
  tasks_on_main: 0,
  tasks_total: 0,
  cost_usd: null,
  unpriced_turns: 0,
  built_at: null,
  started_at: null,
  waits_for: [],
  offers_drafting: false,
  retrospective: null,
  warning: null,
  added_after_approval: false,
  added_by: null,
  ...extra,
})

const SPEC_VISUALS: RoadmapSliceRow[] = [
  row('s1', { state: 'Built', document: 'spec/changes/a/spec.json', document_title: 'Doc A', tasks_on_main: 4, tasks_total: 4, cost_usd: 11.96, built_at: '2026-11-16T00:30:34Z', retrospective: { document: 'a', at: 't', vault_source: null } }),
  row('s2', { state: 'Built', document: 'spec/changes/b/spec.json', document_title: 'Doc B', tasks_on_main: 5, tasks_total: 5, cost_usd: 24.42, built_at: '2026-11-16T16:22:44Z', builds_after: ['s1'] }),
  row('s3', { builds_after: ['s1'], offers_drafting: true }),
  row('s4', { builds_after: ['s3'], waits_for: ['s3'] }),
  row('s5', { offers_drafting: true, unpriced_turns: 2 }),
]

function view(rows: RoadmapSliceRow[], extra: Partial<SpecPayload> = {}, phase = 'approved') {
  const record = { id: 'rm', path: RM, title: 'Roadmap', kind: 'roadmap', phase, updated_at: '2026-11-16T10:00:00Z' } as SpecDocumentRecord
  return documentView({
    record,
    payload: { title: 'Roadmap', kind: 'roadmap', problem: 'p', slices: rows.map((r) => ({ key: r.key, title: r.title ?? r.key, intent: r.intent ?? '', done: r.done ?? '', builds_after: r.builds_after })), ...extra },
    updatedAt: '2026-11-16T10:00:00Z',
    coverage: [],
    tasks: [],
    builds: [],
    entries: [],
    checkedClean: false,
    sliceDocuments: Object.fromEntries(rows.filter((r) => r.document).map((r) => [r.key, r.document!])),
    sliceRows: rows,
    progress: { built: rows.filter((r) => r.state === 'Built').length, total: rows.length, cost_usd: 36.38, unpriced_turns: rows.reduce((n, r) => n + r.unpriced_turns, 0) },
  })
}

function renderBody(doc: ReturnType<typeof view>, onOpenDocument = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecDocumentBody doc={doc} filters={NO_DOCUMENT_FILTERS} onFiltersChange={vi.fn()} findings={[]} builds={null} parts={['document']} flash={null} onJump={vi.fn()} onCopyLink={vi.fn()} onOpenDocument={onOpenDocument} hideFilterBar />
    </QueryClientProvider>,
  )
}

const slice = (key: string) => document.getElementById(`slice-${key}`)!

beforeEach(() => {
  vi.clearAllMocks()
})

describe('a roadmap page', () => {
  it('reads 2 of 5 built, $36.38 and 2 unpriced turns in its header (ac-header)', () => {
    renderBody(view(SPEC_VISUALS))
    expect(screen.getByText('2 of 5 built')).toBeInTheDocument()
    expect(screen.getByText(/\$36\.38 so far/)).toBeInTheDocument()
    expect(screen.getByTestId('rm-unpriced')).toHaveTextContent('2 unpriced turns')
  })

  it('shows a built slice with its document, tasks on main, cost and built date (ac-facts)', async () => {
    const open = vi.fn()
    renderBody(view(SPEC_VISUALS), open)
    expect(within(slice('s1')).getByText('4 of 4 tasks on main')).toBeInTheDocument()
    expect(within(slice('s1')).getByText('$11.96')).toBeInTheDocument()
    expect(within(slice('s1')).getByText(/^built /)).toBeInTheDocument()
    await userEvent.click(within(slice('s1')).getByText('Doc A'))
    expect(open).toHaveBeenCalledWith('spec/changes/a/spec.json')
  })

  it('offers drafting on slices 3 and 5, and says slice 4 waits for slice 3 (ac-two-ready)', () => {
    renderBody(view(SPEC_VISUALS))
    const drafts = (key: string) => within(slice(key)).queryAllByRole('button', { name: /Draft this slice/ })
    expect(drafts('s3')).toHaveLength(1)
    expect(drafts('s5')).toHaveLength(1)
    expect(drafts('s4')).toHaveLength(0)
    expect(within(slice('s4')).getByText(/Waits for Slice s3/)).toBeInTheDocument()
  })

  it('takes a draft with the roadmap author preselected', async () => {
    renderBody(view(SPEC_VISUALS))
    await userEvent.click(within(slice('s3')).getByRole('button', { name: /Draft this slice/ }))
    expect(screen.getByLabelText('Agent that drafts this slice')).toHaveValue('Architect')
    await userEvent.click(screen.getByRole('button', { name: 'Draft' }))
    expect(take).toHaveBeenCalledWith({ roadmap: RM, slice: 's3', agent: 'Architect' }, expect.anything())
  })

  it('opens the slice document the take created (take-from-every-surface: roadmap page)', async () => {
    const open = vi.fn()
    take.mockImplementationOnce((_args, options) => options.onSuccess({ state: 'queued', agent: 'Architect', conversation_id: 'c1', entry_id: 'e1', document: 'spec/changes/s3/spec.json' }))
    renderBody(view(SPEC_VISUALS), open)
    await userEvent.click(within(slice('s3')).getByRole('button', { name: /Draft this slice/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Draft' }))
    expect(open).toHaveBeenCalledWith('spec/changes/s3/spec.json')
  })

  it('links a written retrospective and says none exists for the other (ac-retro)', () => {
    const rows = SPEC_VISUALS.map((r) => (r.key === 's2' ? { ...r, retrospective: null } : r))
    renderBody(view(rows))
    expect(within(slice('s1')).getByTestId('rm-retro')).toBeInTheDocument()
    expect(within(slice('s2')).getByTestId('rm-no-retro')).toHaveTextContent('No retrospective has been written yet')
  })

  it('moves and removes only in Edit slices, and warns on a slice listed ahead of its prerequisite (ac-move, ac-move-warn, ac-remove)', async () => {
    const rows = SPEC_VISUALS.map((r) => (r.key === 's4' ? { ...r, warning: 'Builds after s3, which comes later in the roadmap' } : r))
    renderBody(view(rows))
    expect(within(slice('s4')).getByTestId('rm-warning')).toHaveTextContent('s3')
    expect(screen.queryByRole('button', { name: /Move up/ })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: /Edit slices/ }))
    // A Built slice offers neither a move nor a remove.
    expect(within(slice('s1')).queryByRole('button', { name: /Move up/ })).toBeNull()
    expect(within(slice('s1')).queryByRole('button', { name: /Remove/ })).toBeNull()
    await userEvent.click(within(slice('s5')).getByRole('button', { name: 'Move up' }))
    expect(move).toHaveBeenCalledWith({ roadmap: RM, slice: 's5', position: 4 })
    await userEvent.click(within(slice('s5')).getByRole('button', { name: /Remove Slice s5/ }))
    expect(remove).toHaveBeenCalledWith({ roadmap: RM, slice: 's5' }, expect.anything())
  })

  it('adds a slice only through an agent conversation, marking one an agent added (ac-add)', async () => {
    const rows = [...SPEC_VISUALS.slice(0, 4), row('s5', { added_after_approval: true, added_by: 'Architect' })]
    renderBody(view(rows))
    expect(screen.getByTestId('rm-added')).toHaveTextContent('Added after approval by Architect')
    await userEvent.click(screen.getByRole('button', { name: /Edit slices/ }))
    expect(screen.queryByRole('textbox')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: /Add a slice with an agent/ }))
    expect(screen.getByLabelText('Agent to add the slice with')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Start the conversation' }))
    expect(converse).toHaveBeenCalledWith({ roadmap: RM, agent: undefined }, expect.anything())
  })

  it('says it is done and archives nothing until confirmed (ac-done)', async () => {
    const built = ['a', 'b', 'c', 'd'].map((k) =>
      row(k, { state: 'Built', document: `spec/changes/${k}/spec.json`, document_title: `Doc ${k}`, tasks_on_main: 1, tasks_total: 1, built_at: '2026-11-16T10:00:00Z' }),
    )
    const doc = view(built)
    // Two of the four documents are archived already; two are still approved.
    doc.slices![0]!.document!.archived = true
    doc.slices![1]!.document!.archived = true
    const paths = [RM, 'spec/changes/c/spec.json', 'spec/changes/d/spec.json']
    // The Hub's check: the roadmap archives plainly, the two approved slices state they change no capability.
    archive.mockImplementation((args: { check_only?: boolean }, options?: { onSuccess?: (r: unknown) => void }) => {
      if (args.check_only) {
        options?.onSuccess?.({
          archived: [],
          refused: [],
          plan: [
            { path: paths[0], will: 'archive' },
            { path: paths[1], will: 'archive_no_capability_change' },
            { path: paths[2], will: 'archive_no_capability_change' },
          ],
        })
      }
    })
    renderBody(doc)
    expect(screen.getByTestId('rm-done')).toHaveTextContent('This roadmap is done')
    await userEvent.click(screen.getByRole('button', { name: /Archive the roadmap and its slices/ }))
    const dialog = screen.getByTestId('rm-archive-confirm')
    // Only the check has gone out: nothing is archived before the confirmation.
    expect(archive).toHaveBeenCalledTimes(1)
    expect(archive).toHaveBeenCalledWith({ paths, check_only: true, no_capability_change: true }, expect.anything())
    const items = within(dialog).getAllByRole('listitem').map((li) => li.textContent ?? '')
    expect(items).toHaveLength(3)
    expect(items[0]).toContain('Roadmap')
    expect(items[0]).toContain('will be archived')
    expect(items[1]).toContain('Doc c')
    expect(items[1]).toContain('changes none')
    expect(items[2]).toContain('Doc d')
    expect(items[2]).toContain('changes none')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Archive' }))
    expect(archive).toHaveBeenCalledTimes(2)
    expect(archive).toHaveBeenLastCalledWith({ paths, all_or_none: true, no_capability_change: true }, expect.anything())
  })

  it('does not offer to archive while the Hub would refuse a document', async () => {
    const built = ['a', 'b'].map((k) => row(k, { state: 'Built', document: `spec/changes/${k}/spec.json`, document_title: `Doc ${k}`, tasks_on_main: 1, tasks_total: 1, built_at: '2026-11-16T10:00:00Z' }))
    archive.mockImplementation((args: { check_only?: boolean }, options?: { onSuccess?: (r: unknown) => void }) => {
      if (args.check_only)
        options?.onSuccess?.({ archived: [], refused: [], plan: [{ path: RM, will: 'archive' }, { path: 'spec/changes/a/spec.json', will: 'refuse', reason: 'open tasks' }, { path: 'spec/changes/b/spec.json', will: 'archive' }] })
    })
    renderBody(view(built))
    await userEvent.click(screen.getByRole('button', { name: /Archive the roadmap and its slices/ }))
    const dialog = screen.getByTestId('rm-archive-confirm')
    expect(dialog).toHaveTextContent('cannot be archived: open tasks')
    expect(within(dialog).getByRole('button', { name: 'Archive' })).toBeDisabled()
  })

  it('follows the slices with Problem, Scope, questions and evidence', () => {
    renderBody(view(SPEC_VISUALS, { problem: 'Lead line.\n1. a\n2. b', scope: { in_scope: ['x'], non_goals: [] }, open_questions: [{ question: 'Q?', resolved: true }], evidence: { checked: ['file:1'], limits: ['not run'] } }))
    const order = ['slices', 'problem', 'scope', 'questions', 'evidence'].map((id) => document.getElementById(`section-${id}`))
    expect(order.every(Boolean)).toBe(true)
    for (let i = 1; i < order.length; i++) expect(order[i - 1]!.compareDocumentPosition(order[i]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('every document page', () => {
  const record = { id: 'c', path: 'spec/changes/c/spec.json', title: 'C', kind: 'change-spec', phase: 'approved', updated_at: 't' } as SpecDocumentRecord
  const change = (payload: SpecPayload) => documentView({ record, payload, updatedAt: 't', coverage: [], tasks: [], builds: [], entries: [], checkedClean: false })

  it('shows a lead and a seven-item numbered list, and the evidence with its limit (ac-numbered)', () => {
    const lines = Array.from({ length: 7 }, (_, i) => `${i + 1}. point ${i + 1}`).join('\n')
    renderBody(change({ title: 'C', kind: 'change-spec', problem: `Operator said:\n${lines}`, evidence: { checked: ['one.py:1', 'two.py:2'], limits: ['UI not run'] } }))
    expect(screen.getByText('Operator said:')).toBeInTheDocument()
    expect(within(screen.getByTestId('problem-list')).getAllByRole('listitem')).toHaveLength(7)
    const evidence = screen.getByTestId('document-evidence')
    expect(within(evidence).getByText('one.py:1')).toBeInTheDocument()
    expect(within(evidence).getByText('UI not run')).toBeInTheDocument()
  })

  it('keeps a plain problem as one paragraph and shows no evidence section when there is none', () => {
    renderBody(change({ title: 'C', kind: 'change-spec', problem: 'Just a sentence.' }))
    expect(screen.queryByTestId('problem-list')).toBeNull()
    expect(screen.queryByTestId('document-evidence')).toBeNull()
  })
})

describe('the spec list', () => {
  it('shows five marks and 2/5 on the roadmap row, and each slice row its state (ac-list)', () => {
    spec = { slices: SPEC_VISUALS }
    const entry = (path: string, title: string, extra: Partial<SpecListEntry> = {}): SpecListEntry =>
      ({ id: path, path, title, kind: 'change-spec', phase: 'approved', state: 'approved', shown: 'approved', updatedAt: '2026-11-16T00:00:00Z', building: false, ...extra }) as SpecListEntry
    const entries = [
      entry(RM, 'Spec visuals', { kind: 'roadmap' }),
      entry('spec/changes/a/spec.json', 'Doc A', { roadmap: { path: RM, order: 1 } }),
      entry('spec/changes/b/spec.json', 'Doc B', { roadmap: { path: RM, order: 2 } }),
    ]
    render(
      <SpecDocList entries={entries} active={null} prefs={{ ...DEFAULT_LIST_PREFERENCES, order: 'roadmap' }} onPrefsChange={vi.fn()} onOpen={vi.fn()} onNew={vi.fn()} now={new Date('2026-11-17T00:00:00Z')} />,
    )
    const roadmapRow = screen.getByTitle(/^Spec visuals/)
    expect(roadmapRow.querySelectorAll('.aw-rm-progress-cell')).toHaveLength(5)
    expect(within(roadmapRow).getByText('2/5')).toBeInTheDocument()
    expect(within(screen.getByTitle(/^Doc A/)).getByText('Built')).toBeInTheDocument()
  })
})
