import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { VaultContradiction, VaultEntry, VaultFactUse, VaultReport, VaultTextHit } from '@/api/vault'
import { VaultLibrary, type VaultLibraryProps } from '@/components/vault/VaultLibrary'
import type { TextSearch } from '@/components/vault/VaultOverview'
import { VaultScreen } from '@/components/vault/VaultScreen'
import { formatDateTime, formatDay } from '@/lib/format'
import { useConfigStore } from '@/store/configStore'

/** `a-vault-page-that-says-what-it-holds`, task vault-page-wired. The map is newest first, as
 *  `GET /vault/map` sorts it (vault.py: created_at, id, reversed); the facts' uses come in the
 *  order the route builds them, document by document; text hits newest source first. */

const NOW = new Date('2026-11-23T12:00:00Z')

function source(id: string, name: string, type: string, created: string, extra: Partial<VaultEntry> = {}): VaultEntry {
  return {
    id, name, type, visibility: 'tracked', created_at: created, holder: null, available: true,
    opening: `${name}, as it was written.`, kind: 'source', fetches: 0, ...extra,
  }
}

function fact(id: string, claim: string, sources: string[], created: string, extra: Partial<VaultEntry> = {}): VaultEntry {
  return {
    id, name: claim, type: 'note', visibility: 'tracked', created_at: created, holder: null, available: true,
    opening: claim, kind: 'fact', sources, fetches: 0, ...extra,
  }
}

/** Newest first, as the map route returns. */
const mapOrder = (entries: VaultEntry[]) =>
  [...entries].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id))

function library(props: Partial<VaultLibraryProps> & { entries: VaultEntry[] }) {
  const onSelect = vi.fn()
  const all: VaultLibraryProps = {
    settings: { private_location: null, effective_private_location: '', default_visibility: 'tracked' },
    selectedId: null,
    onSelect,
    page: null,
    facts: [],
    contradictions: [],
    reports: [],
    onAdd: () => undefined,
    onExtractFacts: () => undefined,
    onResolve: async () => undefined,
    onSaveSettings: () => undefined,
    uses: { state: 'ready', uses: [] },
    now: NOW,
    ...props,
  }
  const view = render(<VaultLibrary {...all} />)
  return { ...view, onSelect, rerender: (next: Partial<VaultLibraryProps>) => view.rerender(<VaultLibrary {...all} {...next} />) }
}

const region = (name: string) => screen.getByRole('region', { name })
const listCount = () => document.querySelector('.vault-list-count')?.textContent
const radio = (name: RegExp) => screen.getByRole('radio', { name })
const factRows = (scope: HTMLElement) => within(scope).queryAllByRole('button', { name: /^Open fact: / })

describe('Overview counts (overview-counts-agree)', () => {
  const T1 = source('src-t1', 'Kickoff call', 'transcript', '2026-11-20T10:00:00Z')
  const T2 = source('src-t2', 'Colleague call', 'transcript', '2026-11-19T10:00:00Z', {
    visibility: 'private', available: false, holder: 'colleague-laptop', opening: null,
  })
  const R1 = source('src-r1', 'Refund rules', 'rules', '2026-11-18T10:00:00Z')
  const D1 = source('src-d1', 'Pick Postgres', 'decision', '2026-11-17T10:00:00Z')
  const F1 = fact('fct-1', 'The call was on Monday.', ['src-t1'], '2026-11-21T10:00:00Z')
  const F2 = fact('fct-2', 'Acme wants a demo.', ['src-t1'], '2026-11-21T10:01:00Z')
  // Its source is not in the map: counted under Facts, not under All sources or its type.
  const ORPHAN = fact('fct-3', 'A fact from a source since removed.', ['src-gone'], '2026-11-21T10:02:00Z')
  const ARCHIVED = source('src-arch', 'Old kickoff', 'transcript', '2026-11-01T10:00:00Z', { archived_at: '2026-11-02T10:00:00Z' } as Partial<VaultEntry>)
  const CONTRADICTION: VaultContradiction = {
    id: 'ctr-1', facts: ['fct-1', 'fct-2'], presumed: 'fct-2', explanation: 'They disagree.', status: 'open', resolution: null,
    sides: [
      { id: 'fct-1', claim: F1.opening!, source: 'Kickoff call', date: null, presumed: false },
      { id: 'fct-2', claim: F2.opening!, source: 'Kickoff call', date: null, presumed: true },
    ],
  }
  const REPORT: VaultReport = {
    id: 'rpt-1', entry: 'fct-1', entry_kind: 'fact', entry_name: F1.opening!, message: 'Looks wrong.',
    reporter: { agent: 'Architect', run_id: null }, status: 'referred', answer: 'Over to you.',
    replaced_by: null, replaced_by_claim: null, close: null,
  }

  it('says what each view lists', () => {
    library({
      entries: mapOrder([T1, T2, R1, D1, F1, F2, ORPHAN]),
      archived: [ARCHIVED],
      contradictions: [CONTRADICTION],
      reports: [REPORT],
    })
    const lead = region('In the vault')
    expect(lead).toHaveTextContent('4 sources and 3 facts drawn from them.')
    expect(within(lead).getByText(/1 disagreement between facts/)).toBeInTheDocument()
    expect(within(lead).getByText(/1 report referred to you/)).toBeInTheDocument()
    expect(within(lead).getByText(/2 sources have no facts drawn from them yet/)).toBeInTheDocument()
    expect(within(lead).getByText(/1 private source is held on another machine/)).toBeInTheDocument()

    // The rail agrees with every figure.
    expect(screen.getByTestId('vault-side-facts')).toHaveTextContent('3')
    expect(screen.getByRole('button', { name: /^All sources/ })).toHaveTextContent('4')
    expect(screen.getByRole('button', { name: /^Transcripts/, pressed: false })).toHaveTextContent('2')
    expect(screen.getByTestId('vault-review-contradictions')).toHaveTextContent('1')
    expect(screen.getByTestId('vault-review-reports')).toHaveTextContent('1')

    // And so does each view it opens.
    fireEvent.click(within(lead).getByRole('button', { name: 'Transcripts: 2' }))
    expect(listCount()).toBe('2')
    expect(screen.queryByTestId('vault-entry-src-arch')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^Overview/ }))
    fireEvent.click(within(region('In the vault')).getByRole('button', { name: /3 facts/ }))
    expect(listCount()).toBe('3')
    expect(factRows(screen.getByTestId('vault-fact-list'))).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: /^All sources/ }))
    expect(listCount()).toBe('4')
    expect(screen.queryByTestId('vault-entry-fct-3')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^Overview/ }))
    fireEvent.click(screen.getByRole('button', { name: /1 disagreement between facts/ }))
    expect(listCount()).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: /^Overview/ }))
    fireEvent.click(screen.getByRole('button', { name: /1 report referred to you/ }))
    expect(listCount()).toBe('1')
  })
})

describe('Important facts', () => {
  const S = source('src-s', 'Pricing call', 'transcript', '2026-11-10T10:00:00Z')
  const A = fact('fct-a', 'Refunds over 437 euros need approval.', ['src-s'], '2026-11-11T10:00:00Z')
  const B = fact('fct-b', 'Invoices are sent monthly.', ['src-s'], '2026-11-12T10:00:00Z')
  const C = fact('fct-c', 'Support answers within a day.', ['src-s'], '2026-11-13T10:00:00Z')
  const D = fact('fct-d', 'The API is versioned.', ['src-s'], '2026-11-14T10:00:00Z', {
    fetches: 3, last_fetched_at: '2026-11-22T09:00:00Z', readers: [{ agent: 'Architect', count: 3, last_read_at: '2026-11-22T09:00:00Z' }],
  })
  const ref = (document: string, title: string, requirement: string) => ({ document, title, requirement, statement: `${requirement} says so.` })
  // In the order the route builds them: document by document, sorted by path.
  const USES: VaultFactUse[] = [
    { fact: 'fct-b', citations: [], conflicts: [{ ...ref('spec/changes/billing/spec.json', 'Billing', 'FR-2'), explanation: 'Says weekly.' }] },
    {
      fact: 'fct-a',
      citations: [],
      conflicts: [
        { ...ref('spec/changes/billing/spec.json', 'Billing', 'FR-1'), explanation: 'Says 500.' },
        { ...ref('spec/changes/refunds/spec.json', 'Refunds', 'FR-4'), explanation: 'Says none.' },
      ],
    },
    { fact: 'fct-c', citations: [ref('spec/changes/support/spec.json', 'Support', 'FR-7')], conflicts: [] },
  ]

  it('lists each reason with its count and why each fact is there (important-three-lists)', () => {
    const { onSelect } = library({ entries: mapOrder([S, A, B, C, D]), uses: { state: 'ready', uses: USES } })
    const important = region('Important facts')
    expect(radio(/^Contradicted a spec/)).toHaveAttribute('aria-checked', 'true')
    expect(radio(/^Contradicted a spec/)).toHaveTextContent('2')
    expect(radio(/^Cited by a spec/)).toHaveTextContent('1')
    expect(radio(/^Opened by profiles/)).toHaveTextContent('1')

    const conflicts = factRows(important)
    expect(conflicts.map((r) => r.getAttribute('data-testid'))).toEqual(['vault-fact-fct-a', 'vault-fact-fct-b'])
    expect(conflicts[0]).toHaveTextContent('Contradicts FR-1 of Billing and 1 more spec')
    expect(conflicts[1]).toHaveTextContent('Contradicts FR-2 of Billing')
    fireEvent.click(conflicts[0]!)
    expect(onSelect).toHaveBeenCalledWith('fct-a')

    fireEvent.click(radio(/^Cited by a spec/))
    const cited = factRows(important)
    expect(cited.map((r) => r.getAttribute('data-testid'))).toEqual(['vault-fact-fct-c'])
    expect(cited[0]).toHaveTextContent('Cited by FR-7 of Support')

    fireEvent.click(radio(/^Opened by profiles/))
    const opened = factRows(important)
    expect(opened.map((r) => r.getAttribute('data-testid'))).toEqual(['vault-fact-fct-d'])
    expect(opened[0]).toHaveTextContent('Opened 3× by Architect')
  })

  it('says why each list is empty (important-empty-lists)', () => {
    library({ entries: mapOrder([S, A, B, C, { ...D, fetches: 0, readers: [], last_fetched_at: null }]), uses: { state: 'ready', uses: [] } })
    const important = region('Important facts')
    const sentences: Array<[RegExp, string]> = [
      [/^Contradicted a spec/, 'No spec check has found a conflict with a fact yet.'],
      [/^Cited by a spec/, 'No spec requirement lists a fact yet.'],
      [/^Opened by profiles/, 'No profile has opened a fact yet.'],
    ]
    for (const [name, sentence] of sentences) {
      expect(radio(name)).toHaveTextContent('0')
      fireEvent.click(radio(name))
      expect(within(important).getByTestId('vault-important-none')).toHaveTextContent(sentence)
      expect(factRows(important)).toHaveLength(0)
    }
  })
})

describe('What profiles open (agents-open-list)', () => {
  const opened = (id: string, n: number, at: string, agents: string[]) =>
    source(id, `Source ${id}`, 'document', '2026-11-01T10:00:00Z', {
      fetches: n, last_fetched_at: at, readers: agents.map((agent) => ({ agent, count: 1, last_read_at: at })),
    })
  const SOURCES = mapOrder([
    opened('src-a', 24, '2026-11-20T10:00:00Z', ['Architect', 'Developer']),
    opened('src-b', 5, '2026-11-19T10:00:00Z', ['QA']),
    // Three opened three times: most recently opened first.
    opened('src-c', 3, '2026-11-10T10:00:00Z', ['QA']),
    opened('src-d', 3, '2026-11-22T10:00:00Z', ['Developer']),
    opened('src-e', 3, '2026-11-15T10:00:00Z', ['Architect']),
    opened('src-f', 1, '2026-11-21T10:00:00Z', ['QA']),
    source('src-g', 'Never opened', 'document', '2026-11-02T10:00:00Z'),
  ])

  it('lists the five most opened, with when and by whom', () => {
    library({ entries: SOURCES })
    const section = region('What profiles open')
    expect(section).toHaveTextContent('Every run also lists each fact, and that is not counted.')
    const rows = within(section).getAllByRole('button')
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual([
      'Open document: Source src-a', 'Open document: Source src-b', 'Open document: Source src-d',
      'Open document: Source src-e', 'Open document: Source src-c',
    ])
    expect(rows[0]).toHaveTextContent('Opened 24×')
    expect(rows[0]).toHaveTextContent('by Architect, Developer')
    expect(within(rows[0]!).getByTitle(`Last opened ${formatDateTime('2026-11-20T10:00:00Z', NOW)}`)).toBeInTheDocument()
    expect(rows[1]).toHaveTextContent('Opened 5×')
    expect(rows[4]).toHaveTextContent('Opened 3×')
  })

  it('says when no source was ever opened', () => {
    library({ entries: [source('src-g', 'Never opened', 'document', '2026-11-02T10:00:00Z')] })
    expect(region('What profiles open')).toHaveTextContent('No profile has opened a source yet.')
  })
})

describe('Latest added (latest-list)', () => {
  it('lists the five newest, with day, adder and facts', () => {
    const days = ['2026-11-22', '2026-11-21', '2026-11-20', '2026-11-19', '2026-11-18', '2026-11-17', '2026-11-16']
    const sources = days.map((day, i) =>
      source(`src-${i}`, `Added on ${day}`, 'note', `${day}T10:00:00Z`, i === 1 ? { added_by: 'Architect' } : {}),
    )
    const facts = sources.filter((_, i) => i !== 2).map((s, i) => fact(`fct-${i}`, `Fact ${i}`, [s.id], '2026-11-10T10:00:00Z'))
    library({ entries: mapOrder([...sources, ...facts]) })
    const rows = within(region('Latest added')).getAllByRole('button')
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual(days.slice(0, 5).map((d) => `Open note: Added on ${d}`))
    expect(rows[0]).toHaveTextContent(`Added ${formatDay('2026-11-22T10:00:00Z', NOW)}`)
    expect(rows[0]).toHaveTextContent('1 fact')
    expect(rows[0]).not.toHaveTextContent('by ')
    expect(rows[1]).toHaveTextContent('by Architect')
    expect(rows[2]).toHaveTextContent('No facts yet')
  })
})

describe('Search', () => {
  const POLICY = source('src-policy', 'Refund policy', 'rules', '2026-11-20T10:00:00Z', { opening: 'What we pay back.' })
  const CALL = source('src-call', 'Pricing call', 'transcript', '2026-11-21T10:00:00Z', { opening: 'Hello all.' })
  const STANDING = fact('fct-now', 'The refund limit is 437 euros', ['src-call'], '2026-11-21T11:00:00Z')
  // Newer, but superseded: listed after the fact that stands.
  const OLD = fact('fct-old', 'The REFUND limit was 300 euros', ['src-call'], '2026-11-22T11:00:00Z', { superseded_at: '2026-11-22T12:00:00Z' } as Partial<VaultEntry>)
  const ARCHIVED = source('src-arch', 'Refund archive', 'rules', '2026-11-01T10:00:00Z')
  // As the route answers: newest source first, archived sources left out.
  const HITS: VaultTextHit[] = [
    { source: 'src-call', total: 4, lines: [{ line: 4, text: 'The refund is fine.' }, { line: 9, text: 'Refund by card.' }, { line: 12, text: 'No refund after a year.' }] },
  ]
  const entries = mapOrder([POLICY, CALL, STANDING, OLD])

  function search(text: TextSearch, query = 'refund') {
    const view = library({ entries, archived: [ARCHIVED], textSearch: text })
    fireEvent.change(screen.getByRole('textbox', { name: 'Search the vault' }), { target: { value: query } })
    return view
  }

  it('lists every fact holding the word, the standing one first (search-lists-facts)', () => {
    search({ state: 'ready', hits: HITS })
    const section = region('Facts holding refund')
    expect(within(section).getByText('Facts').parentElement).toHaveTextContent('2')
    const rows = factRows(section)
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual(['vault-fact-fct-now', 'vault-fact-fct-old'])
    expect(rows.map((r) => [...r.querySelectorAll('mark')].map((m) => m.textContent))).toEqual([['refund'], ['REFUND']])
    expect(rows[1]).toHaveTextContent('Superseded')
  })

  it('lists the named source, then the one whose text holds it, with its lines (search-lists-documents)', () => {
    search({ state: 'ready', hits: HITS })
    const section = region('Documents holding refund')
    const rows = within(section).getAllByRole('button')
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual(['Open rule: Refund policy', 'Open transcript: Pricing call'])
    expect(rows[1]).toHaveTextContent('Line 4')
    expect(rows[1]).toHaveTextContent('Line 9')
    expect(rows[1]).toHaveTextContent('Line 12')
    expect(rows[1]).toHaveTextContent('and 1 more lines')
    expect(rows[1]).not.toHaveTextContent('Line 30')
    expect(screen.queryByText('Refund archive')).toBeNull()
  })

  it('says it is searching, and what failed, while still listing facts and names (states-honest)', () => {
    const { rerender } = search({ state: 'searching' })
    expect(region('Documents holding refund')).toHaveTextContent('Searching inside documents…')
    expect(factRows(region('Facts holding refund'))).toHaveLength(2)
    expect(screen.queryByText(/No fact or document holds/)).toBeNull()

    rerender({ textSearch: { state: 'error', message: 'Could not search inside documents. The Hub answered 500.' } })
    const documents = region('Documents holding refund')
    expect(within(documents).getByRole('alert')).toHaveTextContent('The Hub answered 500.')
    expect(within(documents).getByRole('button', { name: 'Open rule: Refund policy' })).toBeInTheDocument()
    expect(factRows(region('Facts holding refund'))).toHaveLength(2)
    expect(screen.queryByText(/No fact or document holds/)).toBeNull()
  })

  it('says nothing holds the word, and offers to clear the search (states-honest)', () => {
    search({ state: 'ready', hits: [] }, 'zebra')
    expect(screen.getByText('No fact or document holds “zebra”.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear the search' }))
    expect(screen.getByRole('textbox', { name: 'Search the vault' })).toHaveValue('')
    expect(region('In the vault')).toBeInTheDocument()
  })
})

describe('Facts view (facts-view-order)', () => {
  it('lists standing facts newest first, then superseded ones, with their marks', () => {
    const S = source('src-s', 'Pricing call', 'transcript', '2026-11-10T10:00:00Z')
    const entries = mapOrder([
      S,
      fact('fct-1', 'Oldest standing', ['src-s'], '2026-11-11T10:00:00Z'),
      fact('fct-2', 'Disputed standing', ['src-s'], '2026-11-12T10:00:00Z', { disputed: true }),
      fact('fct-3', 'Newest standing, source gone', ['src-gone'], '2026-11-13T10:00:00Z'),
      fact('fct-4', 'Superseded', ['src-s'], '2026-11-14T10:00:00Z', { superseded_by: 'src-decision' }),
    ])
    const { onSelect } = library({ entries })
    fireEvent.click(screen.getByTestId('vault-side-facts'))
    const rows = factRows(screen.getByTestId('vault-fact-list'))
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual(['vault-fact-fct-3', 'vault-fact-fct-2', 'vault-fact-fct-1', 'vault-fact-fct-4'])
    expect(rows[0]).toHaveTextContent('Its source is not in the vault')
    expect(rows[1]).toHaveTextContent('Disputed')
    expect(rows[1]).toHaveTextContent('From Pricing call')
    expect(rows[3]).toHaveTextContent('Superseded')
    fireEvent.click(rows[1]!)
    expect(onSelect).toHaveBeenCalledWith('fct-2')
  })
})

// ── VaultScreen, with the routes stubbed at fetch ───────────────────────────────────────────────

type Answer = { status: number; body: unknown } | Promise<{ status: number; body: unknown }>
let route: (url: string) => Answer | undefined
const asked: string[] = []

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const CALL = source('src-call', 'Pricing call', 'transcript', '2026-11-20T10:00:00Z')
const CALL_TEXT = 'Hello all.\nToday we talk refunds.\nThe refund limit without approval is 437 euros.\nThat is all.\n'
const LINED = fact('fct-lined', 'The refund limit is 437 euros.', ['src-call'], '2026-11-21T10:00:00Z')
const NO_LINES = fact('fct-nolines', 'Refunds are discussed.', ['src-call'], '2026-11-21T10:01:00Z')
const CHANGED = fact('fct-changed', 'Everybody said hello.', ['src-call'], '2026-11-21T10:02:00Z', { stale: true })
const ALONE = fact('fct-alone', 'A fact whose source left.', ['src-gone'], '2026-11-21T10:03:00Z')
const SCREEN_MAP = mapOrder([CALL, LINED, NO_LINES, CHANGED, ALONE])

function page(entry: VaultEntry, extra: Record<string, unknown> = {}) {
  return { ...entry, content: null, next_offset: null, note: null, ...extra }
}

const RECORDS: Record<string, unknown> = {
  'src-call': page(CALL, { content: CALL_TEXT }),
  'fct-lined': page(LINED, { claim: LINED.opening, citations: [{ source: 'src-call', quote: 'limit without approval is 437 euros', line_start: 3, line_end: 3 }] }),
  'fct-nolines': page(NO_LINES, { claim: NO_LINES.opening, citations: [] }),
  'fct-changed': page(CHANGED, { claim: CHANGED.opening, citations: [{ source: 'src-call', quote: 'Hello all.', line_start: 1, line_end: 1 }] }),
  'fct-alone': page(ALONE, { claim: ALONE.opening, citations: [] }),
}

beforeEach(() => {
  asked.length = 0
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a' })
  route = (url) => {
    if (url.endsWith('/vault/map')) return { status: 200, body: { entries: SCREEN_MAP } }
    if (url.endsWith('/vault/settings')) return { status: 200, body: { private_location: null, effective_private_location: '', default_visibility: 'tracked' } }
    if (url.endsWith('/vault/fact-uses')) return { status: 200, body: { uses: [], unreadable: [] } }
    const entry = url.match(/\/vault\/entries\/([^?]+)\?offset=0$/)
    if (entry && RECORDS[entry[1]!]) return { status: 200, body: RECORDS[entry[1]!] }
    return undefined
  }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    asked.push(url)
    const answer = await (route(url) ?? { status: 404, body: { detail: 'Not Found' } })
    return new Response(JSON.stringify(answer.body), { status: answer.status })
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function openFactsView() {
  render(<VaultScreen />, { wrapper })
  fireEvent.click(await screen.findByTestId('vault-side-facts'))
  return screen.getByTestId('vault-fact-list')
}

describe('VaultScreen opens facts (facts-view-order, facts-open-unusual)', () => {
  it('opens a fact under its source, on the Facts tab, focused, with its lines marked', async () => {
    const list = await openFactsView()
    fireEvent.click(within(list).getByRole('button', { name: `Open fact: ${LINED.opening}` }))
    const reader = await screen.findByRole('article', { name: 'Pricing call' })
    expect(within(reader).getByRole('radio', { name: /^Facts/ })).toHaveAttribute('aria-checked', 'true')
    await waitFor(() => expect(within(reader).getByTestId('vault-fact-fct-lined')).toHaveAttribute('data-focused', 'true'))
    await waitFor(() => expect(within(reader).getByTestId('vault-line-3')).toHaveAttribute('data-highlighted', 'true'))
    expect([...reader.querySelectorAll('[data-highlighted=true]')].map((e) => e.getAttribute('data-testid'))).toEqual(['vault-line-3'])
  })

  it('opens a fact citing no lines with no line marked', async () => {
    const list = await openFactsView()
    fireEvent.click(within(list).getByRole('button', { name: `Open fact: ${NO_LINES.opening}` }))
    const reader = await screen.findByRole('article', { name: 'Pricing call' })
    await waitFor(() => expect(within(reader).getByTestId('vault-fact-fct-nolines')).toHaveAttribute('data-focused', 'true'))
    expect(reader.querySelectorAll('[data-highlighted=true]')).toHaveLength(0)
    expect(within(reader).queryByRole('alert')).toBeNull()
  })

  it('opens a fact whose source changed focused, still marked', async () => {
    const list = await openFactsView()
    expect(within(list).getByRole('button', { name: `Open fact: ${CHANGED.opening}` })).toHaveTextContent('Source changed')
    fireEvent.click(within(list).getByRole('button', { name: `Open fact: ${CHANGED.opening}` }))
    const reader = await screen.findByRole('article', { name: 'Pricing call' })
    await waitFor(() => expect(within(reader).getByTestId('vault-fact-fct-changed')).toHaveAttribute('data-focused', 'true'))
    expect(within(reader).getByTestId('vault-stale-fct-changed')).toHaveTextContent(/source changed/i)
  })

  it('opens a fact whose source is not in the vault on its own, with no error', async () => {
    const list = await openFactsView()
    fireEvent.click(within(list).getByRole('button', { name: `Open fact: ${ALONE.opening}` }))
    const reader = await screen.findByRole('article', { name: ALONE.name })
    expect(await within(reader).findByTestId('vault-fact-alone')).toHaveTextContent('Its source is not in the vault')
    expect(within(reader).getByTestId('vault-fact-alone')).toHaveTextContent(ALONE.opening!)
    expect(within(reader).queryByRole('alert')).toBeNull()
  })
})

describe('VaultScreen states (states-honest)', () => {
  it('says it is reading the uses, then what failed, never that no spec uses a fact', async () => {
    let fail: (answer: { status: number; body: unknown }) => void = () => undefined
    const base = route
    route = (url) =>
      url.endsWith('/vault/fact-uses') ? new Promise((resolve) => { fail = resolve }) : base(url)
    render(<VaultScreen />, { wrapper })
    const important = await screen.findByRole('region', { name: 'Important facts' })
    expect(important).toHaveTextContent('Reading which facts the specs name…')
    // The hook retries twice; each attempt fails the same way.
    route = (url) => (url.endsWith('/vault/fact-uses') ? { status: 500, body: { detail: 'The event log could not be read.' } } : base(url))
    fail({ status: 500, body: { detail: 'The event log could not be read.' } })
    const alert = await within(important).findByRole('alert', {}, { timeout: 8000 })
    expect(alert).toHaveTextContent('The event log could not be read.')
    expect(within(important).queryByTestId('vault-important-none')).toBeNull()
    expect(within(important).queryByRole('radio')).toBeNull()
  }, 15000)

  it('shows the library as it was on a Hub that predates the uses', async () => {
    const base = route
    route = (url) => (url.endsWith('/vault/fact-uses') ? undefined : base(url))
    render(<VaultScreen />, { wrapper })
    const all = await screen.findByRole('button', { name: /^All entries/ })
    await waitFor(() => expect(all).toHaveAttribute('aria-pressed', 'true'))
    expect(screen.queryByTestId('vault-overview')).toBeNull()
    expect(screen.queryByTestId('vault-side-facts')).toBeNull()
  })
})

describe('VaultScreen search (search-current-text)', () => {
  it('keeps the current text’s documents when an earlier word answers last', async () => {
    const pending: Record<string, (answer: { status: number; body: unknown }) => void> = {}
    const base = route
    route = (url) => {
      const q = url.match(/\/vault\/search\?q=([^&]+)$/)
      if (!q) return base(url)
      return new Promise((resolve) => { pending[decodeURIComponent(q[1]!)] = resolve })
    }
    render(<VaultScreen />, { wrapper })
    const box = await screen.findByRole('textbox', { name: 'Search the vault' })
    fireEvent.change(box, { target: { value: 'ref' } })
    await waitFor(() => expect(pending.ref).toBeDefined())
    fireEvent.change(box, { target: { value: 'refund' } })
    await waitFor(() => expect(pending.refund).toBeDefined())
    expect(region('Documents holding refund')).toHaveTextContent('Searching inside documents…')

    pending.refund!({ status: 200, body: { hits: [{ source: 'src-call', total: 1, lines: [{ line: 3, text: 'The refund limit without approval is 437 euros.' }] }] } })
    const documents = () => region('Documents holding refund')
    await waitFor(() => expect(documents()).toHaveTextContent('Line 3'))
    pending.ref!({ status: 200, body: { hits: [{ source: 'src-call', total: 1, lines: [{ line: 2, text: 'Today we talk refunds.' }] }] } })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(documents()).toHaveTextContent('Line 3')
    expect(documents()).not.toHaveTextContent('Line 2')
    expect(asked.filter((u) => u.includes('/vault/search?q='))).toEqual([
      'http://hub/api/v1/projects/proj-a/vault/search?q=ref',
      'http://hub/api/v1/projects/proj-a/vault/search?q=refund',
    ])
  })
})
