/** The shapes `GET /api/v1/projects/{id}/thread` returns (hub/api/v1/thread.py, `project_thread.face`).
 *  The Thread page's components take these unchanged, so wiring the tab is only the hooks. */

export type KnotKind =
  | 'document'
  | 'phase-change'
  | 'edit'
  | 'task'
  | 'status-change'
  | 'run'
  | 'evidence'
  | 'verdict'
  | 'merge'
  | 'question'
  | 'permission'
  | 'message'
  | 'firing'
  | 'conversation'
  | 'vault-entry'
  | 'fold'
  | 'chapter'
  | 'release'
  | 'commit'

/** Where a knot that stands for a stored object leads. */
export interface KnotLink {
  object: 'document' | 'task' | 'run' | 'evidence' | 'conversation' | 'job-firing' | 'vault-entry'
  id: string
  [extra: string]: string
}

export interface ThreadKnot {
  /** Stable address of the knot; the same string opens the thread at it. */
  key: string
  address: string
  kind: KnotKind
  /** For a fold, the routine kind it gathers, or 'group' for items outside any document. */
  fold_of: KnotKind | 'group' | null
  /** The kind in plain words ("Run", "Runs"). */
  word: string
  title: string
  start: string
  end: string
  actors: string[]
  child_count: number
  descendant_count: number
  link: KnotLink | null
  /** A chapter's plain-language summary; absent on every other kind. */
  summary?: string | null
}

/** One level of the thread, oldest first. `hasBefore`/`hasAfter` say whether more lies beyond. */
export interface ThreadLevelData {
  knots: ThreadKnot[]
  hasBefore: boolean
  hasAfter: boolean
}

/** The surface level is keyed by this in a map of levels. */
export const SURFACE = 'surface'

/** What `GET /thread` returns for one page, as the route spells it. */
export interface ThreadPageResponse {
  knots: ThreadKnot[]
  total: number
  has_before: boolean
  has_after: boolean
  before_cursor: string | null
  after_cursor: string | null
  under: string
  /** True while the chapters job is on: the page offers 'Weave the thread'. Absent on an older Hub. */
  can_weave?: boolean
}

/** One level as the container holds it: the page(s) loaded so far and the cursors to walk on. */
export interface LoadedLevel extends ThreadLevelData {
  beforeCursor: string | null
  afterCursor: string | null
}

export interface ThreadQuery {
  under?: string
  limit?: number
  before?: string
  after?: string
  first?: boolean
  around?: string
}

export function threadUrl(projectId: string, query: ThreadQuery): string {
  const params = new URLSearchParams()
  if (query.under && query.under !== SURFACE) params.set('under', query.under)
  params.set('limit', String(query.limit ?? 40))
  if (query.before) params.set('before', query.before)
  if (query.after) params.set('after', query.after)
  if (query.first) params.set('first', 'true')
  if (query.around) params.set('around', query.around)
  return `/api/v1/projects/${projectId}/thread?${params.toString()}`
}

export function knotUrl(projectId: string, key: string): string {
  return `/api/v1/projects/${projectId}/thread/knot?key=${encodeURIComponent(key)}`
}

export function toLoadedLevel(page: ThreadPageResponse): LoadedLevel {
  return {
    knots: page.knots,
    hasBefore: page.has_before,
    hasAfter: page.has_after,
    beforeCursor: page.before_cursor,
    afterCursor: page.after_cursor,
  }
}
