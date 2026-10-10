import { useEffect, useRef, useState } from 'react'
import { readableApiError } from '@/api/client'
import {
  VAULT_TYPES,
  isFact,
  isNoVault,
  useDistilVaultSource,
  useResolveContradiction,
  useUpdateVaultSettings,
  useUploadVaultSource,
  useVaultContradictions,
  useVaultEntry,
  useVaultMap,
  useVaultSettings,
  type VaultContradiction,
  type VaultEntry,
  type VaultSettings,
  type VaultType,
  type VaultVisibility,
} from '@/api/vault'
import { Badge } from '@/components/common/Badge'
import { Button } from '@/components/ui/button'
import { Input, Select, Textarea } from '@/components/ui/input'
import { hubDate } from '@/lib/hubTime'

/**
 * The project's knowledge vault (`a-vault-the-operator-fills-with-text-and-agents-can-read`).
 *
 * The entries on the left, newest first; the chosen entry's text, or the upload form, on the
 * right; where entries go, below. Agents read the same entries through `vault_map` and
 * `vault_read`, and nothing they can call writes here.
 *
 * A Hub that predates the vault answers its routes 404. The bundle reaches the operator's app on
 * reload, possibly before their server restarts, so that reads as a state rather than an error.
 *
 * Facts (`the-manager-distils-vault-sources-into-cited-facts`) are listed under the source they
 * cite, not as rows of their own; a fact whose source is not in the map is listed as a row. After
 * an upload or a Distil, the map is re-read for a few minutes, because the manager writes facts in
 * the background.
 *
 * Contradictions (`sources-that-disagree-are-pointed-out`) are listed above the entries, open
 * first, each with a form that records the operator's decision. A Hub that predates them answers
 * 404, which reads as no section; the facts they dispute carry a mark where they are listed.
 */
const WATCH_MS = 3 * 60 * 1000
const WATCH_EVERY_MS = 3000
// A cited line, and the fact it is cited for: the same tint, so the eye pairs them.
const CITED = 'color-mix(in srgb, var(--blue) 16%, transparent)'

export function VaultPage() {
  const [watching, setWatching] = useState(0)
  const map = useVaultMap(watching ? WATCH_EVERY_MS : false)
  const settings = useVaultSettings()
  // The check runs after a distillation, so the list is re-read while facts may still be arriving.
  const contradictions = useVaultContradictions(watching ? WATCH_EVERY_MS : false)
  const [selected, setSelected] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  // Each watch restarts the clock: a later Distil gets its own few minutes.
  useEffect(() => {
    if (!watching) return
    const timer = setTimeout(() => setWatching(0), WATCH_MS)
    return () => clearTimeout(timer)
  }, [watching])
  const watch = () => setWatching((count) => count + 1)

  if (isNoVault(map.error) || isNoVault(settings.error)) {
    return (
      <p data-testid="vault-none" className="p-6 text-sm" style={{ color: 'var(--text-3)' }}>
        This Hub has no vault yet. It arrives when the Hub is restarted on a version that has one.
      </p>
    )
  }

  const entries = map.data ?? []
  const current = entries.find((entry) => entry.id === selected) ?? null
  const sourceIds = new Set(entries.filter((entry) => !isFact(entry)).map((entry) => entry.id))
  const factsOf = (id: string) => entries.filter((entry) => isFact(entry) && (entry.sources ?? []).includes(id))
  // A fact is listed under each source it cites that is here; one citing none of them is a row.
  const rows = entries.filter(
    (entry) => !isFact(entry) || !(entry.sources ?? []).some((source) => sourceIds.has(source)),
  )

  return (
    <div className="flex flex-col gap-6 p-6" data-testid="vault-page">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">Vault</h2>
          <p className="mt-1 max-w-2xl text-xs" style={{ color: 'var(--text-3)' }}>
            What the business has told this project: meeting transcripts, rules, documents and
            examples. Every agent turn mentions the vault in one line, and agents read entries by id.
          </p>
        </div>
        <Button
          size="sm"
          data-testid="vault-upload-open"
          onClick={() => {
            setAdding(true)
            setSelected(null)
          }}
        >
          Add a source
        </Button>
      </header>

      <ContradictionSection contradictions={contradictions.data ?? []} error={contradictions.error} />

      <div className="grid min-h-[320px] grid-cols-[minmax(220px,320px)_1fr] gap-6">
        <section aria-label="Vault entries" className="flex flex-col gap-1">
          {map.error ? (
            <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
              {readableApiError(map.error, "Could not read this project's vault.")}
            </p>
          ) : !map.data ? (
            <div aria-label="Loading the vault" className="skeleton h-[120px] w-full" />
          ) : entries.length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--text-3)' }}>
              Nothing yet. Add a transcript, a rule or a document, and agents can read it.
            </p>
          ) : (
            rows.map((entry) => (
              <EntryRow
                key={entry.id}
                entry={entry}
                factCount={isFact(entry) ? 0 : factsOf(entry.id).length}
                active={entry.id === selected}
                onOpen={() => {
                  setSelected(entry.id)
                  setAdding(false)
                }}
              />
            ))
          )}
        </section>

        <section aria-label="Vault entry" className="min-w-0">
          {adding ? (
            <UploadForm
              settings={settings.data}
              onDone={(id) => {
                setAdding(false)
                setSelected(id)
                watch()
              }}
              onCancel={() => setAdding(false)}
            />
          ) : current ? (
            <EntryView key={current.id} entry={current} facts={factsOf(current.id)} onDistilling={watch} />
          ) : (
            <p className="text-xs" style={{ color: 'var(--text-3)' }}>
              Choose an entry to read it.
            </p>
          )}
        </section>
      </div>

      <SettingsForm settings={settings.data} error={settings.error} />
    </div>
  )
}

function EntryRow({
  entry,
  factCount,
  active,
  onOpen,
}: {
  entry: VaultEntry
  factCount: number
  active: boolean
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      data-testid={`vault-entry-${entry.id}`}
      data-active={active ? 'true' : 'false'}
      onClick={onOpen}
      className="row-item flex w-full flex-col items-start gap-1 rounded-md px-3 py-2 text-left"
    >
      <span className="flex w-full items-center gap-2">
        <span className="truncate text-sm font-medium">{entry.name}</span>
        <Badge variant="default">{entry.type}</Badge>
        {entry.visibility === 'private' && <Badge variant="warning">private</Badge>}
      </span>
      <span className="line-clamp-2 text-xs" style={{ color: 'var(--text-3)' }}>
        {entry.available ? entry.opening : `Held on ${entry.holder ?? 'another machine'}`}
      </span>
      {factCount > 0 && (
        <span className="text-xs" style={{ color: 'var(--text-2)' }}>
          {factCount === 1 ? '1 fact' : `${factCount} facts`}
        </span>
      )}
    </button>
  )
}

function EntryView({
  entry,
  facts,
  onDistilling,
}: {
  entry: VaultEntry
  facts: VaultEntry[]
  onDistilling: () => void
}) {
  const pages = useVaultEntry(entry.id)
  const loaded = pages.data?.pages ?? []
  const first = loaded[0]
  const text = loaded.map((page) => page.content ?? '').join('')
  // The fact whose citation is shown: its card carries the lines, found by the Hub.
  const [citing, setCiting] = useState<string | null>(null)
  const card = useVaultEntry(citing)
  const ranges = (card.data?.pages[0]?.citations ?? [])
    .filter((citation) => citation.source === entry.id)
    .map((citation) => [citation.line_start, citation.line_end] as const)
  const source = !isFact(entry)

  return (
    <article className="flex flex-col gap-3">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{entry.name}</h3>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
            {entry.type} · {entry.visibility === 'private' ? `private, held on ${entry.holder ?? 'another machine'}` : 'tracked in the repository'}
            {' · '}
            {entry.dated ? `said ${entry.dated} · ` : ''}
            {hubDate(entry.created_at).toLocaleString()} · <code>{entry.id}</code>
          </p>
        </div>
        {source && <DistilButton entry={entry} onDistilling={onDistilling} />}
      </header>
      {source && facts.length > 0 && (
        <FactList facts={facts} citing={citing} onCite={setCiting} />
      )}
      {card.error ? (
        <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {readableApiError(card.error, 'Could not read where this fact says so.')}
        </p>
      ) : null}
      {pages.error ? (
        <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {readableApiError(pages.error, 'Could not read this entry.')}
        </p>
      ) : !first ? (
        <div aria-label="Loading the entry" className="skeleton h-[160px] w-full" />
      ) : first.content === null ? (
        <p className="text-xs" style={{ color: 'var(--text-3)' }}>{first.note}</p>
      ) : (
        <>
          <SourceText text={text} ranges={ranges} />
          {pages.hasNextPage && (
            <Button
              size="sm"
              variant="ghost"
              disabled={pages.isFetchingNextPage}
              onClick={() => void pages.fetchNextPage()}
            >
              Show more
            </Button>
          )}
        </>
      )}
    </article>
  )
}

function DistilButton({ entry, onDistilling }: { entry: VaultEntry; onDistilling: () => void }) {
  const distil = useDistilVaultSource()
  return (
    <div className="flex max-w-xs flex-col items-end gap-1">
      <Button
        size="sm"
        variant="ghost"
        data-testid="vault-distil"
        disabled={distil.isPending || !entry.available}
        title="Ask the manager to read this source and write the facts it states"
        onClick={() => distil.mutate(entry.id, { onSuccess: onDistilling })}
      >
        Distil
      </Button>
      {distil.error ? (
        <p className="text-right text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {readableApiError(distil.error, 'Could not distil this source.')}
        </p>
      ) : distil.isSuccess ? (
        <p className="text-right text-xs" style={{ color: 'var(--text-3)' }}>
          Distilling in the background. Its facts appear here when it finishes.
        </p>
      ) : null}
    </div>
  )
}

function FactList({
  facts,
  citing,
  onCite,
}: {
  facts: VaultEntry[]
  citing: string | null
  onCite: (id: string) => void
}) {
  return (
    <section aria-label="Facts from this source" className="flex flex-col gap-1">
      <h4 className="settings-group-heading">Facts</h4>
      <ul className="flex flex-col gap-1">
        {facts.map((fact) => (
          <li
            key={fact.id}
            data-testid={`vault-fact-${fact.id}`}
            data-disputed={fact.disputed ? 'true' : 'false'}
            data-superseded={fact.superseded_by ? 'true' : 'false'}
            className="flex items-start justify-between gap-3 rounded-md px-3 py-2 text-sm"
            style={{
              background: fact.id === citing ? CITED : 'var(--surface-2)',
              border: '1px solid var(--border)',
            }}
          >
            <span className="min-w-0">
              {fact.available ? fact.opening : `A private fact, held on ${fact.holder ?? 'another machine'}`}
              {fact.visibility === 'private' && (
                <>
                  {' '}
                  <Badge variant="warning">private</Badge>
                </>
              )}
              {fact.disputed && (
                <>
                  {' '}
                  <Badge variant="warning">{fact.presumed ? 'disputed, presumed to hold' : 'disputed'}</Badge>
                </>
              )}
              {fact.superseded_by && (
                <>
                  {' '}
                  <Badge variant="default">superseded by a decision</Badge>
                </>
              )}
            </span>
            {fact.available && (
              <button
                type="button"
                data-testid={`vault-fact-link-${fact.id}`}
                className="shrink-0 text-xs underline"
                style={{ color: 'var(--blue)' }}
                onClick={() => onCite(fact.id)}
              >
                Where it says so
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** A source's text a line at a time, so a fact's citation can mark the lines it rests on. */
function SourceText({ text, ranges }: { text: string; ranges: ReadonlyArray<readonly [number, number]> }) {
  const lines = (text.endsWith('\n') ? text.slice(0, -1) : text).split('\n')
  const firstLit = ranges.length ? Math.min(...ranges.map(([start]) => start)) : null
  const firstLitRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    // Not in jsdom, which has no layout.
    firstLitRef.current?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  }, [firstLit])

  return (
    <div
      data-testid="vault-entry-text"
      className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md py-4 text-sm"
      style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
    >
      {lines.map((line, index) => {
        const number = index + 1
        const lit = ranges.some(([start, end]) => number >= start && number <= end)
        return (
          <div
            key={number}
            ref={number === firstLit ? firstLitRef : undefined}
            data-testid={`vault-line-${number}`}
            data-highlighted={lit ? 'true' : 'false'}
            className="px-4"
            style={
              lit
                ? { background: CITED, boxShadow: 'inset 3px 0 0 var(--blue)' }
                : undefined
            }
          >
            {line || ' '}
          </div>
        )
      })}
    </div>
  )
}

function UploadForm({
  settings,
  onDone,
  onCancel,
}: {
  settings: VaultSettings | undefined
  onDone: (id: string) => void
  onCancel: () => void
}) {
  const upload = useUploadVaultSource()
  const [name, setName] = useState('')
  const [type, setType] = useState<VaultType>('transcript')
  const [visibility, setVisibility] = useState<VaultVisibility>(settings?.default_visibility ?? 'tracked')
  const [content, setContent] = useState('')
  const [dated, setDated] = useState('')
  const [fileError, setFileError] = useState<string | null>(null)

  const readFile = async (file: File | undefined) => {
    if (!file) return
    try {
      setContent(await file.text())
      setFileError(null)
      if (!name) setName(file.name.replace(/\.[^.]+$/, ''))
    } catch {
      setFileError(`Could not read ${file.name} as text.`)
    }
  }

  return (
    <form
      className="flex flex-col gap-3"
      aria-label="Add a source"
      onSubmit={(event) => {
        event.preventDefault()
        upload.mutate(
          { name, type, content, visibility, ...(dated ? { dated } : {}) },
          { onSuccess: (entry) => onDone(entry.id) },
        )
      }}
    >
      <h3 className="text-sm font-semibold">Add a source</h3>
      <label className="flex flex-col gap-1 text-xs">
        Name
        <Input data-testid="vault-upload-name" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <div className="flex gap-3">
        <label className="flex flex-col gap-1 text-xs">
          Type
          <Select
            data-testid="vault-upload-type"
            value={type}
            onChange={(e) => setType(e.target.value as VaultType)}
            wrapperClassName="w-40"
            className="px-2 py-1.5 text-xs"
          >
            {VAULT_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Where it goes
          <Select
            data-testid="vault-upload-visibility"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value as VaultVisibility)}
            wrapperClassName="w-56"
            className="px-2 py-1.5 text-xs"
          >
            <option value="tracked">Tracked: in the repository</option>
            <option value="private">Private: this machine only</option>
          </Select>
        </label>
      </div>
      <label className="flex w-40 flex-col gap-1 text-xs">
        When it was said (optional)
        <Input
          type="date"
          data-testid="vault-upload-dated"
          value={dated}
          onChange={(e) => setDated(e.target.value)}
          title="If two sources disagree, the later one is presumed to hold"
        />
      </label>
      {visibility === 'private' && (
        <p className="text-xs" style={{ color: 'var(--text-3)' }}>
          The text stays on this machine. Its name, type and this machine's name are still listed
          in the repository, so colleagues know it exists.
        </p>
      )}
      <label className="flex flex-col gap-1 text-xs">
        Text
        <Textarea
          data-testid="vault-upload-content"
          rows={12}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Paste a transcript, a rule or a document, or choose a text file below."
        />
      </label>
      <input
        type="file"
        aria-label="Read the text from a file"
        data-testid="vault-upload-file"
        accept=".txt,.md,.markdown,.vtt,.srt,.csv,.json,text/*"
        className="text-xs"
        onChange={(e) => void readFile(e.target.files?.[0])}
      />
      {(fileError || upload.error) && (
        <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {fileError ?? readableApiError(upload.error, 'Could not add that source.')}
        </p>
      )}
      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          data-testid="vault-upload-submit"
          disabled={upload.isPending || !name.trim() || !content}
        >
          Add
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function SettingsForm({ settings, error }: { settings: VaultSettings | undefined; error: unknown }) {
  const update = useUpdateVaultSettings()
  const [location, setLocation] = useState('')
  useEffect(() => setLocation(settings?.private_location ?? ''), [settings?.private_location])

  return (
    <section aria-label="Where entries go" className="flex flex-col gap-3 border-t pt-4" style={{ borderColor: 'var(--border)' }}>
      <h3 className="settings-group-heading">Where entries go</h3>
      {error ? (
        <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {readableApiError(error, "Could not read the vault's settings.")}
        </p>
      ) : !settings ? (
        <div aria-label="Loading the vault's settings" className="skeleton h-[60px] w-full" />
      ) : (
        <>
          <label className="flex items-center gap-3 text-xs">
            New sources are
            <Select
              data-testid="vault-settings-default"
              value={settings.default_visibility}
              onChange={(e) => update.mutate({ default_visibility: e.target.value as VaultVisibility })}
              wrapperClassName="w-56"
              className="px-2 py-1.5 text-xs"
            >
              <option value="tracked">tracked in the repository</option>
              <option value="private">private to this machine</option>
            </Select>
          </label>
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              update.mutate({ private_location: location.trim() || null })
            }}
          >
            <label className="flex min-w-[320px] flex-1 flex-col gap-1 text-xs">
              Private entries are kept in (outside the repository)
              <Input
                data-testid="vault-settings-location"
                value={location}
                placeholder={settings.effective_private_location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </label>
            <Button type="submit" size="sm" data-testid="vault-settings-save" disabled={update.isPending}>
              Save
            </Button>
          </form>
          {update.error && (
            <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
              {readableApiError(update.error, 'Could not save that change.')}
            </p>
          )}
        </>
      )}
    </section>
  )
}

function ContradictionSection({ contradictions, error }: { contradictions: VaultContradiction[]; error: unknown }) {
  // An old Hub has no route: no section, not an error.
  if (isNoVault(error)) return null
  if (error) {
    return (
      <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
        {readableApiError(error, "Could not read this project's contradictions.")}
      </p>
    )
  }
  if (contradictions.length === 0) return null
  const open = contradictions.filter((item) => item.status !== 'resolved').length
  return (
    <section aria-label="Contradictions" data-testid="vault-contradictions" className="flex flex-col gap-2">
      <h3 className="settings-group-heading">
        Contradictions{open > 0 ? ` (${open} open)` : ''}
      </h3>
      <p className="max-w-2xl text-xs" style={{ color: 'var(--text-3)' }}>
        Two sources state different things. Until you decide, agents are told both are disputed and
        that the later-dated one is presumed to hold.
      </p>
      {contradictions.map((item) => <ContradictionCard key={item.id} contradiction={item} />)}
    </section>
  )
}

function ContradictionCard({ contradiction }: { contradiction: VaultContradiction }) {
  const { id, sides, status } = contradiction
  return (
    <article
      data-testid={`vault-contradiction-${id}`}
      data-status={status ?? 'elsewhere'}
      className="flex flex-col gap-2 rounded-md px-3 py-3 text-sm"
      style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
    >
      {contradiction.explanation && <p>{contradiction.explanation}</p>}
      <ul className="flex flex-col gap-1">
        {sides.map((side) => (
          <li key={side.id} data-testid={`vault-contradiction-side-${side.id}`} className="text-xs">
            {side.claim ?? `A private fact, held on ${contradiction.holder ?? 'another machine'}`}
            {side.date && <span style={{ color: 'var(--text-3)' }}> · {side.date}</span>}
            {side.presumed && (
              <>
                {' '}
                <Badge variant="default">presumed</Badge>
              </>
            )}
          </li>
        ))}
      </ul>
      {status === 'resolved' ? (
        <p className="text-xs" style={{ color: 'var(--text-2)' }}>
          Resolved:{' '}
          {contradiction.resolution?.stands
            ? `${sides.find((side) => side.id === contradiction.resolution?.stands)?.claim ?? 'one fact'} stands`
            : 'neither fact stands'}
          . {contradiction.resolution?.note}
        </p>
      ) : status === 'open' ? (
        <ResolveForm contradiction={contradiction} />
      ) : (
        <p className="text-xs" style={{ color: 'var(--text-3)' }}>
          Held on {contradiction.holder ?? 'another machine'}; it can be resolved there.
        </p>
      )}
    </article>
  )
}

function ResolveForm({ contradiction }: { contradiction: VaultContradiction }) {
  const { id, sides } = contradiction
  const resolve = useResolveContradiction()
  const [stands, setStands] = useState(contradiction.presumed ?? sides[0]?.id ?? '')
  const [note, setNote] = useState('')
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      aria-label="Resolve this contradiction"
      onSubmit={(event) => {
        event.preventDefault()
        resolve.mutate({ id, stands: stands || null, note: note.trim() })
      }}
    >
      <label className="flex min-w-[220px] flex-col gap-1 text-xs">
        What holds
        <Select
          data-testid={`vault-resolve-${id}-stands`}
          value={stands}
          onChange={(e) => setStands(e.target.value)}
          className="px-2 py-1.5 text-xs"
        >
          {sides.map((side) => (
            <option key={side.id} value={side.id}>
              {(side.claim ?? side.id).slice(0, 80)}
            </option>
          ))}
          <option value="">Neither stands</option>
        </Select>
      </label>
      <label className="flex min-w-[260px] flex-1 flex-col gap-1 text-xs">
        Why
        <Input data-testid={`vault-resolve-${id}-note`} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <Button type="submit" size="sm" data-testid={`vault-resolve-${id}-submit`} disabled={resolve.isPending || !note.trim()}>
        Resolve
      </Button>
      {resolve.error && (
        <p className="w-full text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {readableApiError(resolve.error, 'Could not record that decision.')}
        </p>
      )}
    </form>
  )
}
