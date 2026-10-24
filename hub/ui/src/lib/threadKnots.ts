import type { KnotKind, KnotLink, LoadedLevel, ThreadKnot } from '@/api/thread'

/** A knot's glyph: one per kind, so kinds are told apart by shape and word and never by colour. */
export const KNOT_GLYPH: Record<KnotKind, string> = {
  document: 'article',
  'phase-change': 'flag',
  edit: 'edit',
  task: 'task_alt',
  'status-change': 'arrow_forward',
  run: 'play_arrow',
  evidence: 'fact_check',
  verdict: 'check_circle',
  merge: 'call_split',
  question: 'help',
  permission: 'lock',
  message: 'chat',
  firing: 'event_note',
  conversation: 'forum',
  'vault-entry': 'archive',
  fold: 'more_horiz',
  chapter: 'menu_book',
  release: 'tag',
  commit: 'file_vcs',
}

/** What following a knot's link is called, in the words of the place it leads. */
export const LINK_LABEL: Record<string, string> = {
  document: 'Open the document',
  task: 'Open the task',
  run: 'Open the transcript',
  evidence: 'Open the evidence',
  conversation: 'Open the conversation',
  'job-firing': 'Open the firing',
  'vault-entry': 'Open the vault entry',
}

const byTime = (a: ThreadKnot, b: ThreadKnot): number =>
  a.start < b.start ? -1 : a.start > b.start ? 1 : a.key < b.key ? -1 : a.key > b.key ? 1 : 0

/** `more` joined onto the side of `level` it lies beyond. A knot already held is replaced by the
 *  fresher copy, so a page fetched twice never draws a knot twice. */
export function joinPage(level: LoadedLevel, more: LoadedLevel, side: 'before' | 'after'): LoadedLevel {
  const fresh = new Set(more.knots.map((k) => k.key))
  const knots = [...level.knots.filter((k) => !fresh.has(k.key)), ...more.knots].sort(byTime)
  return side === 'before'
    ? { ...level, knots, hasBefore: more.hasBefore, beforeCursor: more.beforeCursor }
    : { ...level, knots, hasAfter: more.hasAfter, afterCursor: more.afterCursor }
}

/** The newest page folded into a level that already reaches the present end: what the page covers
 *  is replaced (a knot may have changed), what lies before it is kept as the reader left it. */
export function refreshEnd(level: LoadedLevel, newest: LoadedLevel): LoadedLevel {
  const first = newest.knots[0]
  const kept = first ? level.knots.filter((k) => byTime(k, first) < 0) : level.knots
  if (kept.length === 0) return newest
  return {
    knots: [...kept, ...newest.knots],
    hasBefore: level.hasBefore,
    beforeCursor: level.beforeCursor,
    hasAfter: newest.hasAfter,
    afterCursor: newest.afterCursor,
  }
}

/** Where following a knot's link leads. Null for an object the app has no view of. */
export function linkTarget(
  link: KnotLink,
):
  | { to: 'spec'; path: string }
  | { to: 'task'; id: string }
  | { to: 'conversation'; agent: string; conversation: string | null }
  | { to: 'evidence'; focus: string | null }
  | { to: 'tab'; tab: 'jobs' | 'vault' }
  | null {
  switch (link.object) {
    case 'document':
      return link.path ? { to: 'spec', path: link.path } : null
    case 'task':
      return { to: 'task', id: link.id }
    case 'run':
      // A run's transcript is the conversation it ran in.
      return link.agent ? { to: 'conversation', agent: link.agent, conversation: link.conversation ?? null } : null
    case 'conversation':
      return link.agent ? { to: 'conversation', agent: link.agent, conversation: link.id } : null
    case 'evidence':
      return { to: 'evidence', focus: link.requirement ?? null }
    case 'job-firing':
      return { to: 'tab', tab: 'jobs' }
    case 'vault-entry':
      return { to: 'tab', tab: 'vault' }
    default:
      return null
  }
}
