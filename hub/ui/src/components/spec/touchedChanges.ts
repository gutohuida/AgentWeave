import type { SpecDocumentRecord } from '@/api/spec'

export interface TouchedChange {
  path: string
  title: string
  state: 'waiting' | 'folded'
  /** When it was folded (folded) or first approved (waiting). */
  at: string | null
  /** Waiting only: whether the change's build finished. */
  built?: boolean
  phase?: string
}

/** Every change that touched a capability, newest first: the waiting ones dated by their first
 *  approval, the folded ones by their fold. The Hub returns each group in its own order, so the
 *  groups are merged here by date; a change with no date follows those with one. */
export function touchedChanges(record: SpecDocumentRecord): TouchedChange[] {
  const waiting: TouchedChange[] = (record.waiting_changes ?? []).map((c) => ({
    path: c.path,
    title: c.title,
    state: 'waiting',
    at: c.first_approved_at,
    built: c.built,
    phase: c.phase,
  }))
  const folded: TouchedChange[] = (record.folded_changes ?? []).map((c) => ({ path: c.path, title: c.title, state: 'folded', at: c.folded_at }))
  const seen = new Set<string>()
  return [...waiting, ...folded]
    .map((c, i) => ({ c, i }))
    .sort((a, b) => {
      if (a.c.at && b.c.at) return a.c.at < b.c.at ? 1 : a.c.at > b.c.at ? -1 : a.i - b.i
      if (a.c.at || b.c.at) return a.c.at ? -1 : 1
      return a.i - b.i
    })
    .map(({ c }) => c)
    .filter((c) => (seen.has(c.path) ? false : (seen.add(c.path), true)))
}
