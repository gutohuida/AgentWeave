import * as React from 'react'
import type { VaultContradiction, VaultEntry, VaultEntryPage, VaultFactUse, VaultSettings, VaultTextHit } from '@/api/vault'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/lib/toast'
import { VaultLibrary } from '@/components/vault/VaultLibrary'
import { VaultDistillationStatus } from '@/components/vault/VaultDistillationStatus'
import type { FactUses, TextSearch } from '@/components/vault/VaultOverview'
import type { VaultFact } from '@/components/vault/VaultReader'
import replicaMapJson from '../fixtures/vault_map.json'
import replicaEntriesJson from '../fixtures/vault_entries.json'
import settingsJson from '../fixtures/vault_settings.json'
import projectMapJson from '../fixtures/vault_project_map.json'
import factUsesJson from '../fixtures/vault_fact_uses.json'
import textsJson from '../fixtures/vault_texts.json'
import citationsJson from '../fixtures/vault_fact_citations.json'
import type { ScreenProps } from '../routes'

/**
 * The Vault page (spec a-vault-page-that-says-what-it-holds), fed this repository's own vault as
 * `mock/record_vault.py` recorded it read-only: the map with its read counts, the facts the specs
 * name, each source's text and each fact's citations. `?data=replica` shows the Terra replica's
 * small vault instead, as the page was mocked before.
 *
 * `?state=` simulates what the recording cannot show (`// mock state`):
 *   uses-loading | uses-error   the facts' uses by specs not read yet, or failed
 *   search-slow | search-error  the search inside documents still running, or failed
 *   no-uses                     no spec names any fact, and nothing was opened by an agent
 */

const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
const STATE = query.get('state') ?? ''
const REPLICA = query.get('data') === 'replica'

// mock state: the recording is of 2026-11-23; the mock's clock sits just after it, not at the
// replica's October clock, so "last opened 3 days ago" reads as it will.
const PROJECT_NOW = new Date('2026-11-23T21:00:00Z')

const settings = settingsJson as unknown as VaultSettings
const texts = textsJson as unknown as Record<string, string>
const citations = citationsJson as unknown as Record<string, Pick<VaultEntryPage, 'claim' | 'citations'>>

function projectEntries(): VaultEntry[] {
  const entries = (projectMapJson as unknown as { entries: VaultEntry[] }).entries
  if (STATE !== 'no-uses') return entries
  return entries.map((e) => (e.kind === 'fact' ? { ...e, fetches: 0, readers: [] } : e))
}

function projectUses(): FactUses {
  if (STATE === 'uses-loading') return { state: 'loading' }
  if (STATE === 'uses-error') return { state: 'error', message: 'Could not read which facts the specs name. The Hub answered 500.' }
  if (STATE === 'no-uses') return { state: 'ready', uses: [] }
  return { state: 'ready', uses: (factUsesJson as unknown as { uses: VaultFactUse[] }).uses }
}

/** What the proposed `GET /vault/search?q=` would answer, worked out here from the recorded texts:
 *  each source whose text holds the word, its first three matching lines and how many there are. */
function searchTexts(q: string): VaultTextHit[] {
  const needle = q.trim().toLowerCase()
  if (!needle) return []
  const hits: VaultTextHit[] = []
  for (const [source, text] of Object.entries(texts)) {
    const lines = text.split('\n')
    const found: Array<{ line: number; text: string }> = []
    let total = 0
    lines.forEach((line, i) => {
      if (line.toLowerCase().includes(needle)) {
        total += 1
        if (found.length < 3) found.push({ line: i + 1, text: line })
      }
    })
    if (total) hits.push({ source, total, lines: found })
  }
  return hits.sort((a, b) => b.total - a.total)
}

export default function Vault(props: ScreenProps) {
  return REPLICA ? <ReplicaVault {...props} /> : <ProjectVault />
}

function ProjectVault() {
  const [entries] = React.useState<VaultEntry[]>(projectEntries)
  const uses = React.useMemo(projectUses, [])
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [focusFactId, setFocusFactId] = React.useState<string | null>(null)
  const [textSearch, setTextSearch] = React.useState<TextSearch | undefined>(undefined)
  const timer = React.useRef<number | undefined>(undefined)

  const open = (id: string | null) => {
    const fact = id ? entries.find((e) => e.id === id && e.kind === 'fact') : undefined
    const source = fact ? (fact.sources ?? []).find((s) => entries.some((e) => e.id === s && e.kind !== 'fact')) : undefined
    setSelectedId(source ?? id)
    setFocusFactId(source ? (fact?.id ?? null) : null)
  }

  const onQueryChange = (q: string) => {
    window.clearTimeout(timer.current)
    if (!q.trim()) return setTextSearch(undefined)
    if (STATE === 'search-error') return setTextSearch({ state: 'error', message: 'Could not search inside documents. The Hub answered 500.' })
    setTextSearch({ state: 'searching' })
    // mock state: the Hub's search takes a moment; slower under ?state=search-slow.
    timer.current = window.setTimeout(() => setTextSearch({ state: 'ready', hits: searchTexts(q) }), STATE === 'search-slow' ? 4000 : 250)
  }

  const selected = entries.find((e) => e.id === selectedId) ?? null
  const facts: VaultFact[] = selected
    ? entries.filter((e) => e.kind === 'fact' && (e.sources ?? []).includes(selected.id)).map((f) => ({ ...f, ...(citations[f.id] ?? {}) }))
    : []
  const page: VaultEntryPage | null = selected
    ? { ...selected, content: texts[selected.id] ?? null, next_offset: null, note: texts[selected.id] ? null : 'This mock recorded no text for it.' }
    : null

  return (
    <div className="relative h-full">
      <VaultLibrary
        entries={entries}
        settings={settings}
        selectedId={selectedId}
        onSelect={open}
        page={page}
        facts={facts}
        contradictions={[]}
        reports={[]}
        uses={uses}
        textSearch={textSearch}
        onQueryChange={onQueryChange}
        onAdd={() => toast({ title: 'Added', tone: 'success', description: 'Agents see it in their next turn.' })}
        onExtractFacts={() => toast({ title: 'Extracting facts in the background' })}
        onResolve={async () => undefined}
        onSaveSettings={() => toast({ title: 'Vault storage saved', tone: 'success' })}
        reader={{ focusFactId }}
        status={<VaultDistillationStatus />}
        now={PROJECT_NOW}
      />
    </div>
  )
}

// ── The replica's small vault, as the page was mocked before (?data=replica) ──────────────────

const KICKOFF = 'src-781b3c5db472'
const CONTRACT = 'src-f38c61882b99'

// mock state: the replica's agents have read nothing yet; show what a read entry looks like.
const recorded = (replicaMapJson as unknown as { entries: VaultEntry[] }).entries.map((e) =>
  e.id === CONTRACT ? { ...e, fetches: 3, last_fetched_at: '2026-10-17T11:02:00Z' } : e,
)
const pages = replicaEntriesJson as unknown as Record<string, VaultEntryPage>

// mock state: the replica has no facts. Three facts from the kickoff transcript, one of which an
// opposing fact (from the design review) disputes, so the Facts view and its contradiction show.
function fact(id: string, claim: string, quote: string, line: number, extra: Partial<VaultEntryPage> = {}): VaultEntryPage {
  return {
    id,
    kind: 'fact',
    name: claim,
    type: 'note',
    visibility: 'tracked',
    created_at: '2026-10-17T09:12:00Z',
    holder: null,
    available: true,
    opening: claim,
    sources: [KICKOFF],
    content: null,
    next_offset: null,
    note: null,
    claim,
    citations: [{ source: KICKOFF, quote, line_start: line, line_end: line }],
    ...extra,
  }
}
const FACTS: Record<string, VaultEntryPage[]> = {
  [KICKOFF]: [
    fact('fct-01', 'The command-line tool ships before any interface work.', 'Yes. The CLI ships alone first.', 3, { disputed: true }),
    fact('fct-02', 'Saved reports are never edited once written.', 'Reports must never be edited after the fact.', 3),
    fact('fct-03', 'The first release supports Windows, macOS and Linux.', 'All three, from day one.', 5),
  ],
}
const CONTRADICTIONS: VaultContradiction[] = [
  {
    id: 'ctr-01',
    facts: ['fct-01', 'fct-09'],
    presumed: 'fct-09',
    explanation: 'One says the CLI ships before any interface work; the later one puts the settings screen in the same release.',
    status: 'open',
    resolution: null,
    sides: [
      { id: 'fct-01', claim: 'The command-line tool ships before any interface work.', source: 'Kickoff call with the operator', date: '2026-10-12', presumed: false },
      { id: 'fct-09', claim: 'The settings screen ships in the same release as the CLI.', source: 'Design review: settings', date: '2026-10-15', presumed: true },
    ],
  },
]

function ReplicaVault({ now }: ScreenProps) {
  const [empty, setEmpty] = React.useState(false)
  const [entries, setEntries] = React.useState<VaultEntry[]>(recorded)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [extractingId, setExtractingId] = React.useState<string | null>(null)
  const [resolved, setResolved] = React.useState<string[]>([])

  const facts = selectedId ? (FACTS[selectedId] ?? []) : []
  const contradictions = CONTRADICTIONS.filter((c) => !resolved.includes(c.id))

  return (
    <div className="relative h-full">
      <VaultLibrary
        status={<VaultDistillationStatus />}
        entries={empty ? [] : entries}
        settings={settings}
        selectedId={selectedId}
        onSelect={setSelectedId}
        page={selectedId ? (pages[selectedId] ?? null) : null}
        facts={facts.map((f) => (resolved.length ? { ...f, disputed: false } : f))}
        contradictions={contradictions}
        extractingId={extractingId}
        onAdd={(input) => {
          const label = input.kind === 'files' ? `${input.files.length} file${input.files.length === 1 ? '' : 's'}` : `“${input.name}”`
          if (input.kind === 'text') {
            const id = `src-mock${Date.now()}`
            setEntries((current) => [
              { id, kind: 'source', name: input.name, type: input.type, visibility: input.visibility, created_at: now.toISOString(), dated: input.dated ?? null, holder: null, available: true, opening: input.content.slice(0, 300), fetches: 0 },
              ...current,
            ])
            setEmpty(false)
          }
          toast({ title: `Added ${label}`, tone: 'success', description: 'Agents see it in their next turn.' })
        }}
        onExtractFacts={(id) => {
          setExtractingId(id)
          window.setTimeout(() => {
            setExtractingId(null)
            toast({ title: 'Facts extracted', description: `${(FACTS[id] ?? []).length || 'No new'} facts, each citing its lines.`, tone: 'success' })
          }, 1400)
        }}
        onResolve={async (_cid, stands) => {
          setResolved((r) => [...r, _cid])
          toast({ title: stands ? 'Recorded which fact holds' : 'Recorded that neither holds', description: 'Saved as a decision in the vault.', tone: 'success' })
        }}
        onDelete={(id) => {
          const removed = entries.find((e) => e.id === id)
          setEntries((current) => current.filter((e) => e.id !== id))
          if (selectedId === id) setSelectedId(null)
          toast({ title: `Removed ${removed?.name ?? 'entry'}`, action: { label: 'Undo', onClick: () => removed && setEntries((c) => [removed, ...c]) } })
        }}
        onSaveSettings={() => toast({ title: 'Vault storage saved', tone: 'success' })}
        now={now}
      />
      {/* mock state: not part of the product. Flips the vault to its empty state for review. */}
      <label className="mock-state-toggle">
        <Switch size="sm" checked={empty} onCheckedChange={setEmpty} aria-label="Mock: empty vault" />
        mock: empty vault
      </label>
    </div>
  )
}