import type { VaultContradiction, VaultEntry, VaultFactUse, VaultReport, VaultTextHit } from '@/api/vault'
import { VAULT_KINDS, kindOf } from './vaultKinds'

/** The Vault overview's rules (spec a-vault-page-that-says-what-it-holds): what the vault holds,
 *  which facts matter and why, what agents read, what arrived last, and what a search finds. Pure,
 *  so the overview, the Facts view and the search results count the same things. */

export interface VaultSummary {
  sources: number
  facts: number
  /** Kinds in the library's order, then any a newer Hub wrote; only those with sources. */
  byKind: Array<{ type: string; plural: string; count: number }>
  /** Private sources whose text is on another machine. */
  elsewhere: number
  /** Text sources here with no fact drawn from them yet. */
  undistilled: number
  openContradictions: number
  referredReports: number
}

const isFact = (e: VaultEntry) => e.kind === 'fact'

export function summarize(entries: VaultEntry[], contradictions: VaultContradiction[], reports: VaultReport[]): VaultSummary {
  const sources = entries.filter((e) => !isFact(e))
  const cited = new Set(entries.filter(isFact).flatMap((f) => f.sources ?? []))
  const counts = new Map<string, number>()
  for (const s of sources) counts.set(s.type, (counts.get(s.type) ?? 0) + 1)
  const known = VAULT_KINDS.map((k) => k.type)
  const order = [...known, ...[...counts.keys()].filter((t) => !known.includes(t))]
  return {
    sources: sources.length,
    facts: entries.length - sources.length,
    byKind: order.filter((t) => counts.get(t)).map((t) => ({ type: t, plural: kindOf(t).plural, count: counts.get(t) ?? 0 })),
    elsewhere: sources.filter((s) => !s.available).length,
    undistilled: sources.filter((s) => s.available && !cited.has(s.id)).length,
    openContradictions: contradictions.filter((c) => c.status === 'open').length,
    referredReports: reports.filter((r) => r.status === 'referred').length,
  }
}

/** The newest sources first, by when they were added. */
export function latestSources(entries: VaultEntry[], limit = 5): VaultEntry[] {
  return entries
    .filter((e) => !isFact(e))
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, limit)
}

/** Sources agents opened, most opened first, then most recently. Never-read sources are left out:
 *  zero reads is not a rank. */
export function mostReadSources(entries: VaultEntry[], limit = 5): VaultEntry[] {
  return entries
    .filter((e) => !isFact(e) && (e.fetches ?? 0) > 0)
    .sort((a, b) => (b.fetches ?? 0) - (a.fetches ?? 0) || (b.last_fetched_at ?? '').localeCompare(a.last_fetched_at ?? ''))
    .slice(0, limit)
}

/** Why a fact is important. Each reason is its own list, never a blended score, so the page can
 *  always say why a fact is there. */
export type ImportantBy = 'conflicts' | 'citations' | 'reads'

export interface ImportantFact {
  fact: VaultEntry
  /** The first of its sources that is in the map; null when none is. */
  source: VaultEntry | null
  use: VaultFactUse | null
}

/** Distinct documents, so one spec with three contradicted requirements counts once in the rank. */
function documentCount(refs: Array<{ document: string }>): number {
  return new Set(refs.map((r) => r.document)).size
}

export function importantFacts(entries: VaultEntry[], uses: VaultFactUse[], by: ImportantBy, limit?: number): ImportantFact[] {
  const byId = new Map(entries.map((e) => [e.id, e]))
  const useOf = new Map(uses.map((u) => [u.fact, u]))
  const score = (f: VaultEntry): number => {
    if (by === 'reads') return f.fetches ?? 0
    const use = useOf.get(f.id)
    return use ? documentCount(by === 'conflicts' ? use.conflicts : use.citations) : 0
  }
  const ranked = entries
    .filter(isFact)
    .map((f) => ({ f, n: score(f) }))
    .filter(({ n }) => n > 0)
    .sort((a, b) => b.n - a.n || b.f.created_at.localeCompare(a.f.created_at))
    .map(({ f }) => f)
  return (limit ? ranked.slice(0, limit) : ranked).map((f) => ({
    fact: f,
    source: (f.sources ?? []).map((s) => byId.get(s)).find((s) => s !== undefined && !isFact(s)) ?? null,
    use: useOf.get(f.id) ?? null,
  }))
}

export function importantCounts(entries: VaultEntry[], uses: VaultFactUse[]): Record<ImportantBy, number> {
  return {
    conflicts: importantFacts(entries, uses, 'conflicts').length,
    citations: importantFacts(entries, uses, 'citations').length,
    reads: importantFacts(entries, uses, 'reads').length,
  }
}

/** The searched word as typed, trimmed and lower-cased. Matching is by the word itself, not its
 *  meaning (operator, 2026-11-23). */
export function normalQuery(query: string): string {
  return query.trim().toLowerCase()
}

const superseded = (e: VaultEntry) => Boolean(e.superseded_by || e.superseded_at)

/** Every fact: those that still stand first, superseded ones last, each newest first. */
export function orderedFacts(entries: VaultEntry[]): VaultEntry[] {
  return entries
    .filter(isFact)
    .sort((a, b) => Number(superseded(a)) - Number(superseded(b)) || b.created_at.localeCompare(a.created_at))
}

/** Facts whose claim holds the word, in `orderedFacts`' order. */
export function matchingFacts(entries: VaultEntry[], query: string): VaultEntry[] {
  const q = normalQuery(query)
  if (!q) return []
  return orderedFacts(entries).filter((e) => (e.opening ?? e.name).toLowerCase().includes(q))
}

export interface SourceMatch {
  source: VaultEntry
  /** Where its text holds the word; null when only its name or opening does, or the text search
   *  has not answered. */
  hit: VaultTextHit | null
}

/** Sources whose name or opening holds the word, in the map's order, then those only their text
 *  holds, in the search's order. */
export function matchingSources(entries: VaultEntry[], query: string, hits: VaultTextHit[] | null): SourceMatch[] {
  const q = normalQuery(query)
  if (!q) return []
  const hitOf = new Map((hits ?? []).map((h) => [h.source, h]))
  const sources = entries.filter((e) => !isFact(e))
  const byId = new Map(sources.map((s) => [s.id, s]))
  const named = sources.filter((s) => s.name.toLowerCase().includes(q) || (s.opening ?? '').toLowerCase().includes(q))
  const seen = new Set(named.map((s) => s.id))
  const inText: VaultEntry[] = []
  for (const h of hits ?? []) {
    const s = byId.get(h.source)
    if (s && !seen.has(s.id)) inText.push(s)
  }
  return [...named, ...inText].map((source) => ({ source, hit: hitOf.get(source.id) ?? null }))
}

/** *text* cut into runs, each saying whether it is the searched word, for highlighting. */
export function splitMatch(text: string, query: string): Array<{ text: string; match: boolean }> {
  const q = normalQuery(query)
  if (!q) return [{ text, match: false }]
  const out: Array<{ text: string; match: boolean }> = []
  const lower = text.toLowerCase()
  let at = 0
  let i = lower.indexOf(q)
  while (i >= 0) {
    if (i > at) out.push({ text: text.slice(at, i), match: false })
    out.push({ text: text.slice(i, i + q.length), match: true })
    at = i + q.length
    i = lower.indexOf(q, at)
  }
  if (at < text.length) out.push({ text: text.slice(at), match: false })
  return out
}

const ELLIPSIS = '\u2026'

/** A long line cut around its first match, so the word is always in view. */
export function aroundMatch(text: string, query: string, room = 150): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  if (flat.length <= room) return flat
  const i = Math.max(0, flat.toLowerCase().indexOf(normalQuery(query)))
  const start = Math.max(0, Math.min(i - Math.floor(room / 3), flat.length - room))
  return (start > 0 ? ELLIPSIS : '') + flat.slice(start, start + room) + (start + room < flat.length ? ELLIPSIS : '')
}