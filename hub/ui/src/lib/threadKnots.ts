import type { KnotKind } from '@/api/thread'

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
