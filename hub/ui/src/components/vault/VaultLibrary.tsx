import * as React from 'react'
import type { VaultContradiction, VaultEntry, VaultEntryPage, VaultReport, VaultSettings, VaultVisibility } from '@/api/vault'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { DropZone } from '@/components/ui/dropzone'
import { usePageDrop } from '@/hooks/usePageDrop'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { formatDateTime, formatDay } from '@/lib/format'
import { VaultAddDialog, type VaultAddInput, type VaultAddResult } from './VaultAddDialog'
import { VaultReader, type VaultFact, type VaultFilePreview } from './VaultReader'
import { ContradictionCard, ReportCard, type VaultActionResult } from './VaultReview'
import { VaultStorageDialog } from './VaultStorageDialog'
import {
  VAULT_KINDS,
  baseName,
  canExtract,
  distinguishing,
  fileLabel,
  folderOf,
  kindOf,
  matchesQuery,
  plainOpening,
  withoutText,
} from './vaultKinds'
import '@/styles/vault.css'

/** The knowledge vault as a library: find, read, add.
 *
 *  Left: search, the kinds with counts, and folders. Middle: the entries, grouped by kind (flat
 *  once a filter narrows them), each row a kind mark, the whole name and a quiet meta line. Right:
 *  the reader, once an entry is open; until then the list has the room, with each entry's opening
 *  line. Files dropped anywhere on the library open the Add dialog with them. */

export interface VaultLibraryProps {
  /** `GET /vault/map` entries, in its order. A fact is listed under the source it cites; one citing
   *  no source in the map is a row of its own. */
  entries: VaultEntry[]
  settings: VaultSettings
  /** Why the settings could not be read; the storage dialog says so. */
  settingsError?: string | null
  selectedId: string | null
  /** Called with a source's id, or a fact's (a report's corrected fact): the container opens it. */
  onSelect: (id: string | null) => void
  /** The open entry's text (`GET /vault/entries/{id}`); null while it loads. */
  page: VaultEntryPage | null
  /** Facts citing the open entry, with claims and citations as far as they have been read. */
  facts: VaultFact[]
  /** Every contradiction (`GET /vault/contradictions`), open first; the reader shows those about
   *  its facts. */
  contradictions: VaultContradiction[]
  /** Every report (`GET /vault/reports`), open first. */
  reports?: VaultReport[]
  /** Reads that failed (contradictions, reports): shown above the list. */
  notices?: string[]
  extractingId?: string | null
  /** Answers `{ error, keep }` when some or all of the input was refused; the dialog stays open. */
  onAdd: (input: VaultAddInput) => Promise<VaultAddResult | void> | void
  onExtractFacts: (id: string) => void
  onResolve: (contradictionId: string, stands: string | null, note: string) => VaultActionResult
  onCloseReport?: (reportId: string, note: string) => VaultActionResult
  /** Absent where the Hub has no route to remove an entry. */
  onDelete?: (id: string) => void
  onSaveSettings: (next: { default_visibility: VaultVisibility; private_location: string | null }) => VaultActionResult | void
  /** The open entry's reading state, past its first page. */
  reader?: {
    hasMore?: boolean
    loadingMore?: boolean
    onLoadMore?: () => void
    error?: string | null
    file?: VaultFilePreview | null
    fileError?: string | null
    focusFactId?: string | null
  }
  now: Date
}

type Filter =
  | { kind: 'all' }
  | { kind: 'type'; type: string }
  | { kind: 'folder'; folder: string }
  | { kind: 'contradictions' }
  | { kind: 'reports' }

export function VaultLibrary(props: VaultLibraryProps) {
  const { entries, settings, selectedId, onSelect, now } = props
  const contradictions = props.contradictions
  const reports = props.reports ?? []
  // Sources, plus any fact whose source is not in the map (it would otherwise be unreachable).
  const { sources, factCounts } = React.useMemo(() => {
    const sourceIds = new Set(entries.filter((e) => e.kind !== 'fact').map((e) => e.id))
    const counts: Record<string, number> = {}
    const rows: VaultEntry[] = []
    for (const e of entries) {
      if (e.kind !== 'fact') {
        rows.push(e)
        continue
      }
      const cited = (e.sources ?? []).filter((s) => sourceIds.has(s))
      if (!cited.length) rows.push(e)
      for (const s of cited) counts[s] = (counts[s] ?? 0) + 1
    }
    return { sources: rows, factCounts: counts }
  }, [entries])
  const openContradictions = contradictions.filter((c) => c.status === 'open').length
  const referredReports = reports.filter((r) => r.status === 'referred').length
  const [query, setQuery] = React.useState('')
  const [filter, setFilter] = React.useState<Filter>({ kind: 'all' })
  const [adding, setAdding] = React.useState(false)
  const [addMode, setAddMode] = React.useState<'files' | 'text'>('files')
  const [dropped, setDropped] = React.useState<File[] | undefined>(undefined)
  const [storageOpen, setStorageOpen] = React.useState(false)
  const search = React.useRef<HTMLInputElement>(null)

  const { dragging, bind } = usePageDrop((files) => {
    setDropped(files)
    setAdding(true)
  })

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        search.current?.focus()
      }
      if (e.key === 'Escape' && selectedId && document.activeElement?.tagName !== 'INPUT') onSelect(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedId, onSelect])

  const counts = React.useMemo(() => {
    const c: Record<string, number> = {}
    for (const e of sources) c[e.type] = (c[e.type] ?? 0) + 1
    return c
  }, [sources])
  const folders = React.useMemo(() => {
    const c = new Map<string, number>()
    for (const e of sources) {
      const f = folderOf(e)
      if (f) c.set(f, (c.get(f) ?? 0) + 1)
    }
    return [...c.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [sources])

  const duplicates = React.useMemo(() => {
    const seen = new Map<string, number>()
    for (const e of sources) seen.set(e.name, (seen.get(e.name) ?? 0) + 1)
    return new Set([...seen].filter(([, n]) => n > 1).map(([name]) => name))
  }, [sources])

  const reviewing = filter.kind === 'contradictions' || filter.kind === 'reports'
  const visible = sources.filter(
    (e) =>
      matchesQuery(e, query) &&
      (filter.kind === 'all' ||
        (filter.kind === 'type' ? e.type === filter.type : filter.kind === 'folder' ? folderOf(e) === filter.folder : false)),
  )
  const grouped = filter.kind === 'all' && !query.trim()
  const selected = reviewing ? null : (sources.find((e) => e.id === selectedId) ?? null)
  const factIds = new Set(props.facts.map((f) => f.id))
  const readerContradictions = contradictions.filter((c) => c.status !== 'resolved' && c.facts.some((f) => factIds.has(f)))
  const openEntry = (id: string) => {
    if (reviewing) setFilter({ kind: 'all' })
    onSelect(id)
  }

  const openAdd = (mode: 'files' | 'text' = 'files') => {
    setDropped(undefined)
    setAddMode(mode)
    setAdding(true)
  }

  if (sources.length === 0 && contradictions.length === 0 && reports.length === 0) {
    return (
      <div className="vault-library" data-empty="true" data-testid="vault-page" {...bind}>
        <VaultEmptyState onAdd={() => openAdd('text')} onFiles={(files) => { setDropped(files); setAdding(true) }} />
        <VaultAddDialog open={adding} onOpenChange={setAdding} defaultVisibility={settings.default_visibility} initialFiles={dropped} initialMode={addMode} onAdd={props.onAdd} />
        {dragging ? <DropOverlay /> : null}
      </div>
    )
  }

  const filterTitle =
    filter.kind === 'all'
      ? 'All entries'
      : filter.kind === 'type'
        ? kindOf(filter.type).plural
        : filter.kind === 'folder'
          ? `${filter.folder}/`
          : filter.kind === 'contradictions'
            ? 'Disagreements'
            : 'Reports'

  return (
    <div className="vault-library" data-testid="vault-page" data-reading={selected ? 'true' : 'false'} {...bind}>
      <nav className="vault-side" aria-label="Vault filters">
        <div className="vault-side-head">
          <label className="vault-search">
            <Icon name="search" size={13} />
            <input
              ref={search}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search the vault"
              aria-label="Search the vault"
            />
            {query ? (
              <button data-slot="icon-button" type="button" className="aw-icon-button" aria-label="Clear search" onClick={() => setQuery('')}>
                <Icon name="close" size={12} />
              </button>
            ) : (
              <kbd className="aw-kbd">Ctrl F</kbd>
            )}
          </label>
          <button
            data-slot="icon-button"
            type="button"
            className="aw-icon-button"
            aria-label="Vault storage"
            title="Vault storage"
            onClick={() => setStorageOpen(true)}
          >
            <Icon name="settings" size={14} />
          </button>
        </div>

        <ul className="vault-side-list">
          <SideRow
            icon="vault_all"
            label="All entries"
            count={sources.length}
            active={filter.kind === 'all'}
            onClick={() => setFilter({ kind: 'all' })}
          />
          {VAULT_KINDS.map((k) => (
            <SideRow
              key={k.type}
              icon={k.icon}
              kind={k.type}
              label={k.plural}
              count={counts[k.type] ?? 0}
              active={filter.kind === 'type' && filter.type === k.type}
              onClick={() => setFilter({ kind: 'type', type: k.type })}
            />
          ))}
        </ul>

        {contradictions.length || reports.length ? (
          <>
            <p className="vault-side-heading">Review</p>
            <ul className="vault-side-list">
              {contradictions.length ? (
                <SideRow
                  icon="alert_triangle"
                  label="Disagreements"
                  count={openContradictions}
                  attention={openContradictions > 0}
                  testId="vault-review-contradictions"
                  active={filter.kind === 'contradictions'}
                  onClick={() => setFilter({ kind: 'contradictions' })}
                />
              ) : null}
              {reports.length ? (
                <SideRow
                  icon="flag"
                  label="Reports"
                  count={referredReports}
                  attention={referredReports > 0}
                  testId="vault-review-reports"
                  active={filter.kind === 'reports'}
                  onClick={() => setFilter({ kind: 'reports' })}
                />
              ) : null}
            </ul>
          </>
        ) : null}

        {folders.length ? (
          <>
            <p className="vault-side-heading">Folders</p>
            <ul className="vault-side-list">
              {folders.map(([folder, count]) => (
                <SideRow
                  key={folder}
                  icon="folder"
                  label={folder}
                  count={count}
                  active={filter.kind === 'folder' && filter.folder === folder}
                  onClick={() => setFilter({ kind: 'folder', folder })}
                />
              ))}
            </ul>
          </>
        ) : null}

        <p className="vault-side-hint">
          <Icon name="upload" size={12} />
          Drop files anywhere here to add them.
        </p>
      </nav>

      <section className="vault-list" aria-label={filterTitle}>
        <header className="vault-list-head">
          <h2 className="vault-list-title">
            {filterTitle}
            <span className="vault-list-count">
              {filter.kind === 'contradictions' ? contradictions.length : filter.kind === 'reports' ? reports.length : visible.length}
            </span>
          </h2>
          <Button variant="primary" size="sm" data-testid="vault-upload-open" onClick={() => openAdd()}>
            <Icon name="add" size={14} />
            Add
          </Button>
        </header>

        <div className="vault-list-scroll">
          {props.notices?.map((notice) => (
            <p key={notice} className="vault-note" data-tone="amber" role="alert">
              <Icon name="alert_triangle" size={14} />
              <span>{notice}</span>
            </p>
          ))}
          {filter.kind === 'contradictions' ? (
            <div className="vault-review" data-testid="vault-contradictions">
              <p className="vault-review-intro">
                Two sources state different things. Until you decide, agents are told both are disputed and that the
                later-dated one is presumed to hold.
              </p>
              {contradictions.map((c) => (
                <ContradictionCard key={c.id} contradiction={c} onResolve={props.onResolve} now={now} />
              ))}
            </div>
          ) : filter.kind === 'reports' ? (
            <div className="vault-review" data-testid="vault-reports">
              <p className="vault-review-intro">
                Agents tell the manager when an entry looks wrong. It corrects the entry when the source shows the error, and
                refers the rest to you.
              </p>
              {reports.map((r) => (
                <ReportCard
                  key={r.id}
                  report={r}
                  onOpenEntry={openEntry}
                  onClose={props.onCloseReport ?? (async () => undefined)}
                />
              ))}
            </div>
          ) : visible.length === 0 ? (
            <div className="vault-list-none">
              <p>Nothing matches “{query || filterTitle}”.</p>
              <Button variant="ghost" size="xs" onClick={() => { setQuery(''); setFilter({ kind: 'all' }) }}>
                Show everything
              </Button>
            </div>
          ) : grouped ? (
            VAULT_KINDS.concat(
              [...new Set(visible.map((e) => e.type))]
                .filter((t) => !VAULT_KINDS.some((k) => k.type === t))
                .map((t) => kindOf(t)),
            ).map((k) => {
              const rows = visible.filter((e) => e.type === k.type)
              if (!rows.length) return null
              return (
                <div key={k.type} className="vault-group">
                  <p className="vault-group-head">
                    {k.plural}
                    <span>{rows.length}</span>
                  </p>
                  {rows.map((e) => (
                    <EntryRow key={e.id} entry={e} factCount={factCounts[e.id] ?? 0} active={e.id === selectedId} wide={!selected} ambiguous={duplicates.has(e.name)} onOpen={() => onSelect(e.id)} onExtract={props.onExtractFacts} onDelete={props.onDelete} now={now} />
                  ))}
                </div>
              )
            })
          ) : (
            visible.map((e) => (
              <EntryRow key={e.id} entry={e} factCount={factCounts[e.id] ?? 0} active={e.id === selectedId} wide={!selected} ambiguous={duplicates.has(e.name)} onOpen={() => onSelect(e.id)} onExtract={props.onExtractFacts} onDelete={props.onDelete} now={now} />
            ))
          )}
        </div>
      </section>

      {selected ? (
        <VaultReader
          entry={selected}
          page={props.page}
          facts={props.facts}
          contradictions={readerContradictions}
          extracting={props.extractingId === selected.id}
          onExtractFacts={props.onExtractFacts}
          onResolve={props.onResolve}
          onDelete={props.onDelete}
          onClose={() => onSelect(null)}
          {...props.reader}
          now={now}
        />
      ) : null}

      <VaultAddDialog open={adding} onOpenChange={setAdding} defaultVisibility={settings.default_visibility} initialFiles={dropped} initialMode={addMode} onAdd={props.onAdd} />
      <VaultStorageDialog open={storageOpen} onOpenChange={setStorageOpen} settings={settings} error={props.settingsError} onSave={props.onSaveSettings} />
      {dragging ? <DropOverlay /> : null}
    </div>
  )
}

function SideRow({
  icon,
  kind,
  label,
  count,
  active,
  attention,
  testId,
  onClick,
}: {
  icon: string
  kind?: string
  label: string
  count: number
  active: boolean
  /** Something here waits for the operator: the count is amber. */
  attention?: boolean
  testId?: string
  onClick: () => void
}) {
  return (
    <li>
      <button
        data-slot="vault-side-row"
        type="button"
        className="vault-side-row"
        data-testid={testId}
        data-active={active ? 'true' : 'false'}
        data-attention={attention ? 'true' : undefined}
        data-empty={count === 0 && !attention ? 'true' : 'false'}
        aria-pressed={active}
        onClick={onClick}
      >
        <span className="vault-side-icon" data-kind={kind}>
          <Icon name={icon} size={14} />
        </span>
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <span className="vault-side-count">{count}</span>
      </button>
    </li>
  )
}

function EntryRow({
  entry,
  factCount,
  active,
  wide,
  ambiguous,
  onOpen,
  onExtract,
  onDelete,
  now,
}: {
  entry: VaultEntry
  /** Facts that cite this source. */
  factCount: number
  active: boolean
  wide: boolean
  /** Another entry has the same name: show what this one opens with, to tell them apart. */
  ambiguous: boolean
  onOpen: () => void
  onExtract: (id: string) => void
  onDelete?: (id: string) => void
  now: Date
}) {
  const kind = kindOf(entry.type)
  const folder = folderOf(entry)
  const file = fileLabel(entry)
  return (
    <div className="vault-row aw-reveal-host" data-active={active ? 'true' : 'false'}>
      <button
        data-slot="vault-row-main"
        type="button"
        className="vault-row-main"
        data-testid={`vault-entry-${entry.id}`}
        data-active={active ? 'true' : 'false'}
        aria-current={active ? 'true' : undefined}
        onClick={onOpen}
      >
        <span className="vault-kind-mark" data-kind={kind.type} aria-hidden="true">
          <Icon name={kind.icon} size={13} />
        </span>
        <span className="vault-row-text">
          <span className="vault-row-name">
            {folder ? <span className="vault-row-folder">{folder}/</span> : null}
            {baseName(entry)}
            {ambiguous && entry.opening ? <span className="vault-row-folder"> · {distinguishing(entry.opening)}</span> : null}
          </span>
          <span className="vault-row-meta" title={`Added ${formatDateTime(entry.created_at, now)}`}>
            <span>
              {entry.dated ? `Said ${formatDay(entry.dated, now)}` : `Added ${formatDay(entry.created_at, now)}`}
              {entry.added_by ? (
                <span data-testid={`vault-added-by-${entry.id}`} title="An agent added this source by path">
                  {' '}
                  by {entry.added_by}
                </span>
              ) : null}
            </span>
            {file ? <span>{file}</span> : null}
            {entry.visibility === 'private' ? (
              <span className="inline-flex items-center gap-1">
                <Icon name="lock" size={10} /> Private
              </span>
            ) : null}
            {factCount ? <span>{factCount === 1 ? '1 fact' : `${factCount} facts`}</span> : null}
            {entry.fetches ? (
              <span data-testid={`vault-fetches-${entry.id}`} title="Times agents read this entry">
                Read {entry.fetches}×
              </span>
            ) : null}
            {!entry.available ? <span>{withoutText(entry)}</span> : null}
          </span>
          {wide && entry.opening ? <span className="vault-row-opening">{plainOpening(entry.opening)}</span> : null}
        </span>
      </button>
      <span className="vault-row-end">
        <span className="aw-reveal vault-row-actions">
          <Menu>
            <MenuTrigger asChild>
              <Button variant="ghost" size="icon-xs" aria-label={`Actions for ${entry.name}`}>
                <Icon name="more_horiz" size={14} />
              </Button>
            </MenuTrigger>
            <MenuContent>
              <MenuItem icon="sparkles" disabled={!canExtract(entry)} onSelect={() => onExtract(entry.id)}>
                Extract facts
              </MenuItem>
              <MenuItem icon="content_copy" onSelect={() => void navigator.clipboard?.writeText(entry.id)}>
                Copy id for an agent
              </MenuItem>
              {onDelete ? (
                <>
                  <MenuSeparator />
                  <MenuItem icon="delete" destructive onSelect={() => onDelete(entry.id)}>
                    Remove from vault…
                  </MenuItem>
                </>
              ) : null}
            </MenuContent>
          </Menu>
        </span>
      </span>
    </div>
  )
}

function DropOverlay() {
  return (
    <div className="vault-drop-overlay" aria-hidden="true">
      <div className="vault-drop-card">
        <Icon name="upload" size={22} />
        <p>Drop to add to the vault</p>
        <span>Text, Markdown, PDF and images</span>
      </div>
    </div>
  )
}

export function VaultEmptyState({ onAdd, onFiles }: { onAdd: () => void; onFiles: (files: File[]) => void }) {
  return (
    <div className="vault-empty">
      <span className="vault-empty-mark" aria-hidden="true">
        <Icon name="library" size={22} />
      </span>
      <h2 className="vault-empty-title">Give your agents the context your project lives in</h2>
      <p className="vault-empty-text">
        What was said in meetings, the rules that always hold, the decisions already made. Every agent turn lists the vault,
        and agents read what their work needs.
      </p>
      <ul className="vault-empty-kinds">
        {VAULT_KINDS.slice(0, 4).map((k) => (
          <li key={k.type}>
            <span className="vault-kind-mark" data-kind={k.type} aria-hidden="true">
              <Icon name={k.icon} size={13} />
            </span>
            <span>
              <strong>{k.plural}</strong>
              {k.detail}
            </span>
          </li>
        ))}
      </ul>
      <div className="vault-empty-drop">
        <DropZone title="Drop files or a folder" hint="Text, Markdown, PDF and images." onFiles={onFiles} />
      </div>
      <Button variant="ghost" size="sm" onClick={onAdd}>
        <Icon name="edit_note" size={14} />
        Or paste text
      </Button>
    </div>
  )
}
