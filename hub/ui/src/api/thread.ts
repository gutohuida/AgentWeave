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
}

/** One level of the thread, oldest first. `hasBefore`/`hasAfter` say whether more lies beyond. */
export interface ThreadLevelData {
  knots: ThreadKnot[]
  hasBefore: boolean
  hasAfter: boolean
}

/** The surface level is keyed by this in a map of levels. */
export const SURFACE = 'surface'
