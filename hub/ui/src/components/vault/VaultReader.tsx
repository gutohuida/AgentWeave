import * as React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { VaultCitation, VaultContradiction, VaultEntry, VaultEntryPage } from '@/api/vault'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { toast } from '@/lib/toast'
import { formatAgo, formatDateTime, formatDay } from '@/lib/format'
import { baseName, canExtract, fileLabel, folderOf, hasTrackedFile, kindOf, parseTranscript } from './vaultKinds'
import { ContradictionCard, type VaultActionResult } from './VaultReview'

/** One entry, read. The text is rendered for what it is: a document as Markdown, a transcript as
 *  speaker turns, a rule or decision as a statement. Metadata is a quiet row of label/value pairs;
 *  the entry's id is behind a copy button, never in a sentence. "Extract facts" (was "Distil") reads
 *  the source and writes down each fact it states, with the lines it rests on. */

type ReaderTab = 'text' | 'facts' | 'used'

/** A fact as the map lists it, with its claim and citations once its record has been read. */
export type VaultFact = VaultEntry & Partial<Pick<VaultEntryPage, 'claim' | 'citations'>>

/** A PDF or image source's file, as an object URL fetched with the key. */
export interface VaultFilePreview {
  kind: 'pdf' | 'image'
  url: string
}

export function VaultReader({
  entry,
  page,
  facts,
  contradictions,
  extracting,
  onExtractFacts,
  onResolve,
  onDelete,
  onClose,
  hasMore,
  loadingMore,
  onLoadMore,
  error,
  file,
  fileError,
  focusFactId,
  now,
}: {
  entry: VaultEntry
  /** The entry's text, every page read so far joined; null while it loads. */
  page: VaultEntryPage | null
  /** Facts that cite this source, in the map's order. */
  facts: VaultFact[]
  /** Contradictions that involve one of `facts`. */
  contradictions: VaultContradiction[]
  extracting?: boolean
  onExtractFacts: (id: string) => void
  onResolve: (contradictionId: string, stands: string | null, note: string) => VaultActionResult
  /** Absent where the Hub has no route to remove an entry: no Remove action is offered. */
  onDelete?: (id: string) => void
  onClose: () => void
  /** The text continues past what is loaded. */
  hasMore?: boolean
  loadingMore?: boolean
  onLoadMore?: () => void
  /** Why the text could not be read. */
  error?: string | null
  /** A PDF or image source's file, shown above its transcription. */
  file?: VaultFilePreview | null
  /** Why the file could not be fetched; the transcription below still shows. */
  fileError?: string | null
  /** Open on the Facts view with this fact marked (a report's corrected fact). */
  focusFactId?: string | null
  now: Date
}) {
  const [tab, setTab] = React.useState<ReaderTab>('text')
  // The fact whose citation is shown in the text: its cited lines are marked.
  const [citing, setCiting] = React.useState<string | null>(null)
  React.useEffect(() => {
    setTab(focusFactId ? 'facts' : 'text')
    setCiting(null)
  }, [entry.id, focusFactId])
  const kind = kindOf(entry.type)
  const folder = folderOf(entry)
  const fileKind = fileLabel(entry)
  const ranges = (facts.find((f) => f.id === citing)?.citations ?? [])
    .filter((c: VaultCitation) => c.source === entry.id)
    .map((c) => [c.line_start, c.line_end] as const)

  return (
    <article className="vault-reader" aria-label={entry.name}>
      <header className="vault-reader-head">
        <div className="vault-reader-titlebar">
          <span className="vault-kind-mark" data-kind={kind.type} aria-hidden="true">
            <Icon name={kind.icon} size={15} />
          </span>
          <div className="min-w-0 flex-1">
            {folder ? <p className="vault-reader-folder">{folder}/</p> : null}
            <h1 className="vault-reader-title">{baseName(entry)}</h1>
          </div>
          <div className="vault-reader-actions">
            <Button
              variant="outline"
              size="sm"
              data-testid="vault-distil"
              disabled={extracting || !canExtract(entry)}
              title="Reads this source and writes down each fact it states, citing the lines it rests on. Agents then cite facts instead of re-reading the whole source."
              onClick={() => onExtractFacts(entry.id)}
            >
              <Icon name="sparkles" size={14} />
              {extracting ? 'Extracting…' : facts.length ? 'Extract again' : 'Extract facts'}
            </Button>
            <Menu>
              <MenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="More actions">
                  <Icon name="more_horiz" size={15} />
                </Button>
              </MenuTrigger>
              <MenuContent>
                <MenuItem
                  icon="content_copy"
                  onSelect={() => {
                    void navigator.clipboard?.writeText(entry.id)
                    toast({ title: 'Id copied', description: entry.id })
                  }}
                >
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
            <Button variant="ghost" size="icon-sm" aria-label="Close" title="Close (Esc)" onClick={onClose}>
              <Icon name="close" size={15} />
            </Button>
          </div>
        </div>

        <dl className="vault-meta">
          <div>
            <dt>Kind</dt>
            <dd>{fileKind ? `${kind.label}, ${fileKind}` : kind.label}</dd>
          </div>
          {entry.dated ? (
            <div>
              <dt>Said</dt>
              <dd>{formatDay(entry.dated, now)}</dd>
            </div>
          ) : null}
          <div>
            <dt>Added</dt>
            <dd title={formatDateTime(entry.created_at, now)}>
              {formatDay(entry.created_at, now)}
              {entry.added_by ? <span title="An agent added this source by path"> by {entry.added_by}</span> : null}
            </dd>
          </div>
          <div>
            <dt>Storage</dt>
            <dd>
              {entry.visibility === 'private' ? (
                <span className="inline-flex items-center gap-1" title={entry.holder ? `Held on ${entry.holder}` : undefined}>
                  <Icon name="lock" size={11} /> Private, this machine
                </span>
              ) : (
                'In the repository'
              )}
            </dd>
          </div>
          {entry.fetches !== undefined ? (
            <div>
              <dt>Read by agents</dt>
              <dd data-testid="vault-entry-fetches" title={entry.last_fetched_at ? `Last read ${formatDateTime(entry.last_fetched_at, now)}` : undefined}>
                {entry.fetches ? `${entry.fetches} ${entry.fetches === 1 ? 'time' : 'times'}` : 'Not yet'}
              </dd>
            </div>
          ) : null}
        </dl>

        <Segmented
          label="Entry view"
          size="xs"
          className="self-start"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'text', label: 'Text' },
            { value: 'facts', label: 'Facts', count: facts.length },
            { value: 'used', label: 'Used by' },
          ]}
        />
      </header>

      <div className="vault-reader-body">
        {tab === 'text' ? (
          <>
            {file ? <FileView entry={entry} file={file} /> : null}
            {fileError ? (
              <p className="vault-note" role="alert" data-tone="amber">
                <Icon name="alert_triangle" size={14} />
                <span>{fileError}</span>
              </p>
            ) : null}
            {error ? (
              <p className="vault-note" role="alert" data-tone="amber">
                <Icon name="alert_triangle" size={14} />
                <span>{error}</span>
              </p>
            ) : (
              <EntryText entry={entry} page={page} ranges={ranges} onShowFormatted={() => setCiting(null)} />
            )}
            {hasMore && !error ? (
              <Button variant="ghost" size="sm" className="self-start" disabled={loadingMore} onClick={onLoadMore}>
                {loadingMore ? 'Loading…' : 'Show more'}
              </Button>
            ) : null}
          </>
        ) : null}
        {tab === 'facts' ? (
          <FactsView
            facts={facts}
            contradictions={contradictions}
            extracting={extracting}
            extractable={canExtract(entry)}
            focusFactId={focusFactId ?? null}
            onExtract={() => onExtractFacts(entry.id)}
            onResolve={onResolve}
            onCite={(id) => {
              setCiting(id)
              setTab('text')
            }}
            now={now}
          />
        ) : null}
        {tab === 'used' ? <UsedBy entry={entry} now={now} /> : null}
      </div>
    </article>
  )
}

function EntryText({
  entry,
  page,
  ranges,
  onShowFormatted,
}: {
  entry: VaultEntry
  page: VaultEntryPage | null
  /** Lines a fact cites, marked in a numbered view of the text. */
  ranges: ReadonlyArray<readonly [number, number]>
  onShowFormatted: () => void
}) {
  const heldElsewhere = !entry.available && !hasTrackedFile(entry)
  if (!page) {
    if (heldElsewhere) return <PrivateNote entry={entry} />
    return <div className="skeleton aw-delayed h-[180px] w-full max-w-[72ch]" aria-label="Loading the entry" />
  }
  if (page.content === null) {
    // The Hub says why there is no text: held on another machine, or not read yet.
    return page.note ? (
      <div className="vault-note">
        <Icon name={heldElsewhere ? 'lock' : 'info'} size={14} />
        <span>{page.note}</span>
      </div>
    ) : (
      <PrivateNote entry={entry} />
    )
  }
  const text = page.content
  if (ranges.length) return <SourceLines text={text} ranges={ranges} onShowFormatted={onShowFormatted} />
  let body: React.ReactNode
  if (entry.type === 'transcript') body = <Transcript text={text} />
  else if (entry.type === 'rules' || entry.type === 'decision') {
    body = (
      <blockquote className="vault-statement" data-kind={entry.type}>
        {text}
      </blockquote>
    )
  } else {
    body = (
      <div className="file-preview-markdown vault-markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    )
  }
  return <div data-testid="vault-entry-text">{body}</div>
}

function PrivateNote({ entry }: { entry: VaultEntry }) {
  return (
    <div className="vault-note">
      <Icon name="lock" size={14} />
      <span>This entry is private to {entry.holder ?? 'another machine'}. Its text is not on this one.</span>
    </div>
  )
}

/** The text a line at a time, numbered, with the lines a fact rests on marked and the first of
 *  them scrolled into view. */
function SourceLines({
  text,
  ranges,
  onShowFormatted,
}: {
  text: string
  ranges: ReadonlyArray<readonly [number, number]>
  onShowFormatted: () => void
}) {
  const lines = (text.endsWith('\n') ? text.slice(0, -1) : text).split('\n')
  const firstLit = Math.min(...ranges.map(([start]) => start))
  const firstLitRef = React.useRef<HTMLDivElement | null>(null)
  React.useEffect(() => {
    // Not in jsdom, which has no layout.
    firstLitRef.current?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  }, [firstLit])
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="vault-lines-label">
          <Icon name="sparkles" size={12} />
          The marked {ranges.length === 1 && ranges[0]![0] === ranges[0]![1] ? 'line is' : 'lines are'} where it says so
        </span>
        <Button variant="ghost" size="xs" onClick={onShowFormatted}>
          Show formatted
        </Button>
      </div>
      <div className="vault-lines" data-testid="vault-entry-text">
        {lines.map((line, index) => {
          const number = index + 1
          const lit = ranges.some(([start, end]) => number >= start && number <= end)
          return (
            <div
              key={number}
              ref={number === firstLit ? firstLitRef : undefined}
              className="vault-line"
              data-testid={`vault-line-${number}`}
              data-highlighted={lit ? 'true' : 'false'}
            >
              <span className="vault-line-number" aria-hidden="true">
                {number}
              </span>
              <span className="vault-line-text">{line || ' '}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** A PDF in the browser's viewer, or an image, above the transcription. */
function FileView({ entry, file }: { entry: VaultEntry; file: VaultFilePreview }) {
  return file.kind === 'pdf' ? (
    <iframe data-testid="vault-file-pdf" src={file.url} title={entry.name} className="vault-file vault-file-pdf" />
  ) : (
    <img data-testid="vault-file-image" src={file.url} alt={entry.name} className="vault-file vault-file-image" />
  )
}

function Transcript({ text }: { text: string }) {
  const turns = parseTranscript(text)
  return (
    <ol className="vault-transcript">
      {turns.map((turn, i) => {
        const continues = i > 0 && turns[i - 1]!.speaker === turn.speaker
        return (
          <li key={i} className="vault-turn" data-continues={continues ? 'true' : 'false'} data-operator={turn.speaker === 'Operator' ? 'true' : 'false'}>
            <span className="vault-turn-speaker">{continues ? '' : turn.speaker}</span>
            <p className="vault-turn-text">{turn.text}</p>
          </li>
        )
      })}
    </ol>
  )
}

function FactsView({
  facts,
  contradictions,
  extracting,
  extractable,
  focusFactId,
  onExtract,
  onResolve,
  onCite,
  now,
}: {
  facts: VaultFact[]
  contradictions: VaultContradiction[]
  extracting?: boolean
  extractable: boolean
  focusFactId: string | null
  onExtract: () => void
  onResolve: (contradictionId: string, stands: string | null, note: string) => VaultActionResult
  onCite: (factId: string) => void
  now: Date
}) {
  if (!facts.length) {
    return (
      <div className="vault-tab-empty">
        <Icon name="sparkles" size={18} />
        <p className="vault-tab-empty-title">No facts yet</p>
        <p className="vault-tab-empty-text">
          Extracting reads this source and lists each fact it states, with the lines it rests on. Agents cite a fact instead
          of re-reading the whole source.
        </p>
        <Button variant="outline" size="sm" disabled={extracting || !extractable} onClick={onExtract}>
          {extracting ? 'Extracting…' : 'Extract facts'}
        </Button>
      </div>
    )
  }
  return (
    <div className="flex max-w-[78ch] flex-col gap-3">
      {contradictions.map((c) => (
        <ContradictionCard key={c.id} contradiction={c} onResolve={onResolve} now={now} />
      ))}
      <ul className="vault-facts" aria-label="Facts from this source">
        {facts.map((fact) => (
          <li
            key={fact.id}
            className="vault-fact"
            data-testid={`vault-fact-${fact.id}`}
            data-disputed={fact.disputed ? 'true' : 'false'}
            data-superseded={fact.superseded_by ? 'true' : 'false'}
            data-focused={fact.id === focusFactId ? 'true' : 'false'}
          >
            <p className="vault-fact-claim">
              {fact.available ? (fact.claim ?? fact.opening) : `A private fact, held on ${fact.holder ?? 'another machine'}`}
              {fact.visibility === 'private' ? (
                <span className="vault-chip">
                  <Icon name="lock" size={10} /> Private
                </span>
              ) : null}
              {fact.disputed ? (
                <span className="vault-chip" data-tone="amber">
                  {fact.presumed ? 'Disputed, presumed to hold' : 'Disputed'}
                </span>
              ) : null}
              {fact.superseded_by ? (
                <span className="vault-chip">
                  {fact.superseded_by.startsWith('fct-') ? 'Superseded by a corrected fact' : 'Superseded by a decision'}
                </span>
              ) : null}
            </p>
            {fact.citations?.map((c, i) => (
              <p key={i} className="vault-fact-cite">
                <span className="vault-fact-lines">
                  {c.line_start === c.line_end ? `Line ${c.line_start}` : `Lines ${c.line_start}–${c.line_end}`}
                </span>
                <q>{c.quote}</q>
              </p>
            ))}
            <p className="vault-fact-foot">
              {fact.available ? (
                <Button variant="ghost" size="xs" data-testid={`vault-fact-link-${fact.id}`} onClick={() => onCite(fact.id)}>
                  Show in the source
                </Button>
              ) : null}
              {(fact.fetches ?? 0) > 0 ? (
                <span data-testid={`vault-fetches-${fact.id}`} title="Times agents read this fact">
                  Read {fact.fetches}×
                </span>
              ) : null}
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}

function UsedBy({ entry, now }: { entry: VaultEntry; now: Date }) {
  if (!entry.fetches) {
    return (
      <div className="vault-tab-empty">
        <Icon name="visibility" size={18} />
        <p className="vault-tab-empty-title">No agent has read this yet</p>
        <p className="vault-tab-empty-text">
          Every agent turn mentions the vault in one line, and agents read an entry when their work needs it. Reads show up
          here.
        </p>
      </div>
    )
  }
  const readers = entry.readers ?? []
  const unnamed = Math.max(0, entry.fetches - readers.reduce((sum, reader) => sum + reader.count, 0))
  return (
    <div className="vault-used">
      <p className="vault-used-count">
        Read {entry.fetches} {entry.fetches === 1 ? 'time' : 'times'}
      </p>
      {entry.last_fetched_at ? (
        <p className="vault-used-last">Last read {formatDateTime(entry.last_fetched_at, now)}</p>
      ) : null}
      {readers.length > 0 ? (
        <ul className="vault-readers" data-testid="vault-readers">
          {readers.map((reader) => (
            <li key={reader.agent} className="vault-reader" data-testid={`vault-reader-${reader.agent}`}>
              <span className="vault-reader-name">{reader.agent}</span>
              <span className="vault-reader-count">
                {reader.count} {reader.count === 1 ? 'time' : 'times'}
              </span>
              <span className="vault-reader-last" title={formatDateTime(reader.last_read_at, now)}>
                {formatAgo(reader.last_read_at, now)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {/* Reads from before the Hub recorded who read (migration 0139) are counted but unnamed. */}
      {unnamed > 0 ? (
        <p className="vault-used-last" data-testid="vault-readers-unnamed">
          {unnamed} earlier {unnamed === 1 ? 'read was' : 'reads were'} recorded before the Hub kept who read.
        </p>
      ) : null}
    </div>
  )
}
