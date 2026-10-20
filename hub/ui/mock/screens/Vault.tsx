import * as React from 'react'
import type { VaultContradiction, VaultEntry, VaultEntryPage, VaultSettings } from '@/api/vault'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/lib/toast'
import { VaultLibrary } from '@/components/vault/VaultLibrary'
import mapJson from '../fixtures/vault_map.json'
import entriesJson from '../fixtures/vault_entries.json'
import settingsJson from '../fixtures/vault_settings.json'
import type { ScreenProps } from '../routes'

const KICKOFF = 'src-781b3c5db472'
const CONTRACT = 'src-f38c61882b99'

// mock state: the replica's agents have read nothing yet; show what a read entry looks like.
const recorded = (mapJson as unknown as { entries: VaultEntry[] }).entries.map((e) =>
  e.id === CONTRACT ? { ...e, fetches: 3, last_fetched_at: '2026-10-17T11:02:00Z' } : e,
)
const pages = entriesJson as unknown as Record<string, VaultEntryPage>
const settings = settingsJson as unknown as VaultSettings

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

export default function Vault({ now }: ScreenProps) {
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
