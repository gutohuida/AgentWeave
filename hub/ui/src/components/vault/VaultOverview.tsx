import * as React from 'react'
import type { VaultContradiction, VaultEntry, VaultFactUse, VaultReport } from '@/api/vault'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Segmented } from '@/components/ui/segmented'
import { formatAgo, formatCount, formatDateTime, formatDay, formatWhole } from '@/lib/format'
import { baseName, kindOf, plainOpening } from './vaultKinds'
import {
  aroundMatch,
  importantCounts,
  importantFacts,
  latestSources,
  matchingFacts,
  matchingSources,
  orderedFacts,
  mostReadSources,
  splitMatch,
  summarize,
  type ImportantBy,
  type ImportantFact,
} from './vaultOverviewModel'
import type { VaultTextHit } from '@/api/vault'
import '@/styles/vault.css'

/** The Vault page's overview, its Facts view and its search results (spec
 *  a-vault-page-that-says-what-it-holds). Presentational: the library passes the map, the facts'
 *  uses by specs and the text search's hits, and gets back which entry to open. A fact opens under
 *  its source with its cited lines marked, as the library's `onSelect` already does for a fact id. */

/** Where the facts' uses by specs stand: read, failed, or not read yet. Unknown is never shown as
 *  "no spec uses this fact". */
export type FactUses = { state: 'ready'; uses: VaultFactUse[] } | { state: 'loading' } | { state: 'error'; message: string }

export interface VaultOverviewProps {
  entries: VaultEntry[]
  uses: FactUses
  contradictions: VaultContradiction[]
  reports: VaultReport[]
  onOpen: (id: string) => void
  onShowKind: (type: string) => void
  onShowFacts: () => void
  onShowReview: (which: 'contradictions' | 'reports') => void
  now: Date
}

const IMPORTANT_LIMIT = 8

export function VaultOverview(props: VaultOverviewProps) {
  const { entries, uses, now } = props
  const summary = summarize(entries, props.contradictions, props.reports)
  const known = uses.state === 'ready' ? uses.uses : []
  const counts = importantCounts(entries, known)
  // Open on the first reason that has facts, so a vault with no spec conflicts does not open empty.
  const first: ImportantBy = counts.conflicts ? 'conflicts' : counts.citations ? 'citations' : 'reads'
  const [by, setBy] = React.useState<ImportantBy | null>(null)
  const shown = by ?? first
  const important = importantFacts(entries, known, shown, IMPORTANT_LIMIT)
  const read = mostReadSources(entries)
  const latest = latestSources(entries)
  const factCounts = React.useMemo(() => {
    const c: Record<string, number> = {}
    for (const e of entries) if (e.kind === 'fact') for (const s of e.sources ?? []) c[s] = (c[s] ?? 0) + 1
    return c
  }, [entries])

  return (
    <div className="vault-overview" data-testid="vault-overview">
      <section className="vault-ov-section" aria-label="In the vault">
        <p className="vault-ov-lead">
          <strong className="tabular">{formatWhole(summary.sources)}</strong> {summary.sources === 1 ? 'source' : 'sources'} and{' '}
          <button data-slot="vault-ov-link" type="button" className="vault-ov-link" onClick={props.onShowFacts}>
            <strong className="tabular">{formatWhole(summary.facts)}</strong> {summary.facts === 1 ? 'fact' : 'facts'}
          </button>{' '}
          drawn from them.
        </p>
        <ul className="vault-ov-kinds" aria-label="Sources by kind">
          {summary.byKind.map((k) => (
            <li key={k.type}>
              <button
                data-slot="vault-ov-kind"
                type="button"
                className="vault-ov-kind"
                aria-label={`${k.plural}: ${k.count}`}
                onClick={() => props.onShowKind(k.type)}
              >
                <span className="vault-kind-mark" data-kind={k.type} aria-hidden="true">
                  <Icon name={kindOf(k.type).icon} size={13} />
                </span>
                <span>{k.plural}</span>
                <span className="vault-ov-kind-count tabular">{formatCount(k.count)}</span>
              </button>
            </li>
          ))}
        </ul>
        {summary.openContradictions || summary.referredReports || summary.undistilled || summary.elsewhere ? (
          <ul className="vault-ov-notes">
            {summary.openContradictions ? (
              <li data-tone="amber">
                <Icon name="alert_triangle" size={13} />
                <button data-slot="vault-ov-link" type="button" className="vault-ov-link" onClick={() => props.onShowReview('contradictions')}>
                  {summary.openContradictions === 1 ? '1 disagreement' : `${summary.openContradictions} disagreements`} between facts to decide
                </button>
              </li>
            ) : null}
            {summary.referredReports ? (
              <li data-tone="amber">
                <Icon name="flag" size={13} />
                <button data-slot="vault-ov-link" type="button" className="vault-ov-link" onClick={() => props.onShowReview('reports')}>
                  {summary.referredReports === 1 ? '1 report' : `${summary.referredReports} reports`} referred to you
                </button>
              </li>
            ) : null}
            {summary.undistilled ? (
              <li>
                <Icon name="sparkles" size={13} />
                <span>
                  {summary.undistilled === 1 ? '1 source has' : `${summary.undistilled} sources have`} no facts drawn from {summary.undistilled === 1 ? 'it' : 'them'} yet
                </span>
              </li>
            ) : null}
            {summary.elsewhere ? (
              <li>
                <Icon name="lock" size={13} />
                <span>
                  {summary.elsewhere === 1 ? '1 private source is' : `${summary.elsewhere} private sources are`} held on another machine
                </span>
              </li>
            ) : null}
          </ul>
        ) : null}
      </section>

      <section className="vault-ov-section" aria-label="Important facts">
        <header className="vault-ov-head">
          <h3 className="vault-ov-title">Important facts</h3>
          {uses.state === 'ready' ? (
            <Segmented
              label="Important facts by"
              size="xs"
              value={shown}
              onChange={setBy}
              options={[
                { value: 'conflicts', label: 'Contradicted a spec', count: counts.conflicts },
                { value: 'citations', label: 'Cited by a spec', count: counts.citations },
                { value: 'reads', label: 'Opened by profiles', count: counts.reads },
              ]}
            />
          ) : null}
        </header>
        {uses.state === 'error' ? (
          <p className="vault-note" data-tone="amber" role="alert">
            <Icon name="alert_triangle" size={14} />
            <span>{uses.message}</span>
          </p>
        ) : uses.state === 'loading' ? (
          <p className="vault-ov-quiet aw-delayed">Reading which facts the specs name…</p>
        ) : important.length === 0 ? (
          <p className="vault-ov-quiet" data-testid="vault-important-none">{NONE[shown]}</p>
        ) : (
          <ol className="vault-ov-facts" data-testid={`vault-important-${shown}`}>
            {important.map((item) => (
              <li key={item.fact.id}>
                <FactRow fact={item.fact} source={item.source} why={<ImportantWhy item={item} by={shown} now={now} />} onOpen={props.onOpen} />
              </li>
            ))}
          </ol>
        )}
        <Button variant="ghost" size="xs" className="vault-ov-more" onClick={props.onShowFacts}>
          All {formatWhole(summary.facts)} facts
          <Icon name="arrow_forward" size={12} />
        </Button>
      </section>

      <div className="vault-ov-columns">
        <section className="vault-ov-section" aria-label="What profiles open">
          <h3 className="vault-ov-title">What profiles open</h3>
          <p className="vault-ov-quiet">
            Counted when a profile opens an entry. Every run also lists each fact, and that is not counted.
          </p>
          {read.length === 0 ? (
            <p className="vault-ov-quiet">No profile has opened a source yet.</p>
          ) : (
            <ol className="vault-ov-list">
              {read.map((s) => (
                <li key={s.id}>
                  <SourceLine
                    source={s}
                    onOpen={props.onOpen}
                    meta={
                      <>
                        <span className="tabular" title="Times profiles opened this source">
                          Opened {s.fetches}×
                        </span>
                        {s.last_fetched_at ? (
                          <span title={`Last opened ${formatDateTime(s.last_fetched_at, now)}`}>last {formatAgo(s.last_fetched_at, now)} ago</span>
                        ) : null}
                        {s.readers?.length ? <span>by {s.readers.map((r) => r.agent).join(', ')}</span> : null}
                      </>
                    }
                  />
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="vault-ov-section" aria-label="Latest added">
          <h3 className="vault-ov-title">Latest added</h3>
          <ol className="vault-ov-list">
            {latest.map((s) => (
              <li key={s.id}>
                <SourceLine
                  source={s}
                  onOpen={props.onOpen}
                  meta={
                    <>
                      <span title={`Added ${formatDateTime(s.created_at, now)}`}>Added {formatDay(s.created_at, now)}</span>
                      {s.added_by ? <span>by {s.added_by}</span> : null}
                      <span>{factCounts[s.id] ? (factCounts[s.id] === 1 ? '1 fact' : `${factCounts[s.id]} facts`) : 'No facts yet'}</span>
                    </>
                  }
                />
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  )
}

// Why a reason's list is empty: two of the three start empty on a real project, and an empty list
// that says nothing reads as "nothing matters".
const NONE: Record<ImportantBy, string> = {
  conflicts: 'No spec check has found a conflict with a fact yet. The manager checks a spec against the vault when you press Check on it.',
  citations: 'No spec requirement lists a fact yet. A requirement lists the facts it rests on in its facts.',
  reads: 'No profile has opened a fact yet. Profiles see every fact in the vault list each run; that is not counted.',
}

function ImportantWhy({ item, by, now }: { item: ImportantFact; by: ImportantBy; now: Date }) {
  if (by === 'reads') {
    return (
      <span className="tabular" title={item.fact.last_fetched_at ? `Last opened ${formatDateTime(item.fact.last_fetched_at, now)}` : undefined}>
        Opened {item.fact.fetches}×{item.fact.readers?.length ? ` by ${item.fact.readers.map((r) => r.agent).join(', ')}` : ''}
      </span>
    )
  }
  const refs = by === 'conflicts' ? (item.use?.conflicts ?? []) : (item.use?.citations ?? [])
  const docs = [...new Map(refs.map((r) => [r.document, r])).values()]
  const [lead, ...rest] = docs
  if (!lead) return null
  const verb = by === 'conflicts' ? 'Contradicts' : 'Cited by'
  return (
    <span title={refs.map((r) => `${r.requirement ?? 'A requirement'} of ${r.title}: ${r.statement}`).join('\n')}>
      {verb} {lead.requirement ?? 'a requirement'} of {lead.title}
      {rest.length ? ` and ${rest.length === 1 ? '1 more spec' : `${rest.length} more specs`}` : ''}
    </span>
  )
}

/** One fact as a row: its claim, its marks and its source. Opening it opens the source with the
 *  fact's lines marked. */
export function FactRow({
  fact,
  source,
  why,
  query = '',
  onOpen,
}: {
  fact: VaultEntry
  source: VaultEntry | null
  why?: React.ReactNode
  query?: string
  onOpen: (id: string) => void
}) {
  const claim = fact.opening ?? fact.name
  const gone = Boolean(fact.superseded_by || fact.superseded_at)
  return (
    <button
      data-slot="vault-fact-row"
      type="button"
      className="vault-fact-row"
      data-testid={`vault-fact-${fact.id}`}
      data-superseded={gone ? 'true' : undefined}
      aria-label={`Open fact: ${claim}`}
      title={fact.id}
      onClick={() => onOpen(fact.id)}
    >
      <span className="vault-fact-row-claim">
        <Highlighted text={claim} query={query} />
      </span>
      <span className="vault-row-meta">
        {fact.disputed ? <span className="vault-chip" data-tone="amber">Disputed</span> : null}
        {gone ? <span className="vault-chip">Superseded</span> : null}
        {fact.stale ? <span className="vault-chip">Source changed</span> : null}
        {why}
        <span>{source ? `From ${baseName(source)}` : 'Its source is not in the vault'}</span>
      </span>
    </button>
  )
}

function SourceLine({ source, meta, onOpen }: { source: VaultEntry; meta: React.ReactNode; onOpen: (id: string) => void }) {
  const kind = kindOf(source.type)
  return (
    <button
      data-slot="vault-ov-source"
      type="button"
      className="vault-ov-source"
      aria-label={`Open ${kind.label.toLowerCase()}: ${source.name}`}
      onClick={() => onOpen(source.id)}
    >
      <span className="vault-kind-mark" data-kind={kind.type} aria-hidden="true">
        <Icon name={kind.icon} size={13} />
      </span>
      <span className="vault-row-text">
        <span className="vault-row-name">{baseName(source)}</span>
        <span className="vault-row-meta">{meta}</span>
      </span>
    </button>
  )
}

function Highlighted({ text, query }: { text: string; query: string }) {
  return (
    <>
      {splitMatch(text, query).map((run, i) => (run.match ? <mark key={i} className="vault-match">{run.text}</mark> : <React.Fragment key={i}>{run.text}</React.Fragment>))}
    </>
  )
}

/** Every fact, newest first and superseded last, narrowed by the search when there is one. */
export function VaultFactList({ entries, query, onOpen }: { entries: VaultEntry[]; query: string; onOpen: (id: string) => void }) {
  const byId = React.useMemo(() => new Map(entries.map((e) => [e.id, e])), [entries])
  const facts = React.useMemo(
    () => (query.trim() ? matchingFacts(entries, query) : orderedFacts(entries)),
    [entries, query],
  )
  const [limit, setLimit] = React.useState(PAGE)
  React.useEffect(() => setLimit(PAGE), [query])
  if (!facts.length) return null
  return (
    <ol className="vault-ov-facts" data-testid="vault-fact-list">
      {facts.slice(0, limit).map((f) => (
        <li key={f.id}>
          <FactRow fact={f} source={(f.sources ?? []).map((s) => byId.get(s)).find((s) => s && s.kind !== 'fact') ?? null} query={query} onOpen={onOpen} />
        </li>
      ))}
      {facts.length > limit ? (
        <li>
          <Button variant="ghost" size="xs" onClick={() => setLimit((n) => n + PAGE)}>
            Show {formatCount(Math.min(PAGE, facts.length - limit))} more of {formatCount(facts.length - limit)}
          </Button>
        </li>
      ) : null}
    </ol>
  )
}

const PAGE = 100

/** Where the search inside documents stands. Unknown is never shown as "no document holds it". */
export type TextSearch = { state: 'ready'; hits: VaultTextHit[] } | { state: 'searching' } | { state: 'error'; message: string }

/** What a search finds: the facts whose claim holds the word, then the sources whose name, opening
 *  or text does, each text match showing its first lines. */
export function VaultSearchResults({
  entries,
  query,
  text,
  onOpen,
  onClear,
}: {
  entries: VaultEntry[]
  query: string
  text: TextSearch
  onOpen: (id: string) => void
  onClear: () => void
}) {
  const facts = matchingFacts(entries, query)
  const sources = matchingSources(entries, query, text.state === 'ready' ? text.hits : null)
  const [factLimit, setFactLimit] = React.useState(20)
  React.useEffect(() => setFactLimit(20), [query])
  const byId = React.useMemo(() => new Map(entries.map((e) => [e.id, e])), [entries])
  const nothing = !facts.length && !sources.length && text.state === 'ready'
  return (
    <div className="vault-results" data-testid="vault-search-results">
      {nothing ? (
        <div className="vault-list-none">
          <p>No fact or document holds “{query.trim()}”.</p>
          <Button variant="ghost" size="xs" onClick={onClear}>
            Clear the search
          </Button>
        </div>
      ) : null}
      {facts.length ? (
        <section aria-label={`Facts holding ${query.trim()}`} className="vault-group">
          <p className="vault-group-head">
            Facts
            <span className="tabular">{formatCount(facts.length)}</span>
          </p>
          <ol className="vault-ov-facts">
            {facts.slice(0, factLimit).map((f) => (
              <li key={f.id}>
                <FactRow fact={f} source={(f.sources ?? []).map((s) => byId.get(s)).find((s) => s && s.kind !== 'fact') ?? null} query={query} onOpen={onOpen} />
              </li>
            ))}
          </ol>
          {facts.length > factLimit ? (
            <Button variant="ghost" size="xs" onClick={() => setFactLimit(facts.length)}>
              Show all {formatCount(facts.length)} facts
            </Button>
          ) : null}
        </section>
      ) : null}
      {sources.length || text.state !== 'ready' ? (
        <section aria-label={`Documents holding ${query.trim()}`} className="vault-group">
          <p className="vault-group-head">
            Documents
            {text.state === 'ready' ? <span className="tabular">{formatCount(sources.length)}</span> : null}
          </p>
          {text.state === 'searching' ? <p className="vault-ov-quiet aw-delayed">Searching inside documents…</p> : null}
          {text.state === 'error' ? (
            <p className="vault-note" data-tone="amber" role="alert">
              <Icon name="alert_triangle" size={14} />
              <span>{text.message} Names and openings are still searched.</span>
            </p>
          ) : null}
          {sources.map(({ source, hit }) => (
            <button
              key={source.id}
              data-slot="vault-result-source"
              type="button"
              className="vault-result-source"
              data-testid={`vault-result-${source.id}`}
              aria-label={`Open ${kindOf(source.type).label.toLowerCase()}: ${source.name}`}
              onClick={() => onOpen(source.id)}
            >
              <span className="vault-kind-mark" data-kind={kindOf(source.type).type} aria-hidden="true">
                <Icon name={kindOf(source.type).icon} size={13} />
              </span>
              <span className="vault-row-text">
                <span className="vault-row-name">
                  <Highlighted text={baseName(source)} query={query} />
                </span>
                {hit ? (
                  <span className="vault-result-lines">
                    {hit.lines.map((l) => (
                      <span key={l.line} className="vault-result-line">
                        <span className="vault-result-lineno tabular">Line {l.line}</span>
                        <span>
                          <Highlighted text={aroundMatch(plainOpening(l.text), query)} query={query} />
                        </span>
                      </span>
                    ))}
                    {hit.total > hit.lines.length ? (
                      <span className="vault-row-meta">and {formatCount(hit.total - hit.lines.length)} more lines</span>
                    ) : null}
                  </span>
                ) : null}
              </span>
            </button>
          ))}
        </section>
      ) : null}
    </div>
  )
}