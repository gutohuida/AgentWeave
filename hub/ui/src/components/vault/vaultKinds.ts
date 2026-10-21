import { fileKindOf, type VaultEntry } from '@/api/vault'

/** How each kind of vault entry is named, drawn and explained. One table, so the filter list, the
 *  entry rows, the reader and the Add dialog never disagree. `decision` is what the Hub writes when
 *  a contradiction is resolved, and what an operator records by hand. */
export interface VaultKind {
  type: string
  label: string
  plural: string
  icon: string
  /** One line for the Add dialog's menu and the empty state. */
  detail: string
}

export const VAULT_KINDS: readonly VaultKind[] = [
  { type: 'transcript', label: 'Transcript', plural: 'Transcripts', icon: 'vault_transcript', detail: 'A meeting or call, as it was said.' },
  { type: 'rules', label: 'Rule', plural: 'Rules', icon: 'vault_rules', detail: 'Something that must always hold.' },
  { type: 'decision', label: 'Decision', plural: 'Decisions', icon: 'vault_decision', detail: 'A choice made, and why.' },
  { type: 'document', label: 'Document', plural: 'Documents', icon: 'vault_document', detail: 'A spec, a README, a PDF: reference material.' },
  { type: 'note', label: 'Note', plural: 'Notes', icon: 'vault_note', detail: 'A short working note or checklist.' },
  { type: 'example', label: 'Example', plural: 'Examples', icon: 'vault_example', detail: 'A sample of what good looks like.' },
]

const FALLBACK: VaultKind = { type: 'other', label: 'Entry', plural: 'Other', icon: 'description', detail: '' }

export function kindOf(type: string): VaultKind {
  return VAULT_KINDS.find((k) => k.type === type) ?? { ...FALLBACK, type }
}

/** The entry's folder path, when its name carries one (`docs/plugin-contract.md` → `docs`). */
export function folderOf(entry: Pick<VaultEntry, 'name'>): string | null {
  const at = entry.name.lastIndexOf('/')
  return at > 0 ? entry.name.slice(0, at) : null
}

/** The entry's own name without its folder. */
export function baseName(entry: Pick<VaultEntry, 'name'>): string {
  const at = entry.name.lastIndexOf('/')
  return at >= 0 ? entry.name.slice(at + 1) : entry.name
}

export function matchesQuery(entry: VaultEntry, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return entry.name.toLowerCase().includes(q) || (entry.opening ?? '').toLowerCase().includes(q)
}

/** An entry's opening line as plain prose for a preview: Markdown marks (#, `, **, links, fences,
 *  list bullets) dropped, whitespace collapsed. The reader renders the real thing. */
export function plainOpening(opening: string | null | undefined): string {
  if (!opening) return ''
  return opening
    .replace(/```[a-z]*/gi, ' ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/(^|\s)#{1,6}\s+/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/(^|\s)[-*]\s+/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

/** A short phrase from the opening (at most ~32 characters, cut at a word), used to tell apart
 *  entries that share a name. The Hub's `opening` arrives with its line breaks flattened, so a
 *  heading cannot be told from the paragraph after it; a short cut is the honest best. */
export function distinguishing(opening: string | null | undefined): string {
  const plain = plainOpening(opening)
  if (plain.length <= 32) return plain
  const cut = plain.lastIndexOf(' ', 32)
  return `${plain.slice(0, cut > 12 ? cut : 32)}…`
}

const TURN = /^([A-Z][\w .'-]{0,28}):\s+(.*)$/

/** "Operator: …" lines become labelled turns; a line without a speaker continues the last turn. */
export function parseTranscript(text: string): Array<{ speaker: string | null; text: string }> {
  const turns: Array<{ speaker: string | null; text: string }> = []
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    const m = TURN.exec(line)
    if (m) turns.push({ speaker: m[1]!, text: m[2]! })
    else if (turns.length) turns[turns.length - 1]!.text += `\n${line}`
    else turns.push({ speaker: null, text: line })
  }
  return turns
}

/** A tracked PDF or image: its file is in the repository whether or not its text has been read,
 *  so it can be previewed and have its facts extracted before it has a transcription (F616). */
export function hasTrackedFile(entry: Pick<VaultEntry, 'media_type' | 'visibility'>): boolean {
  return Boolean(fileKindOf(entry.media_type)) && entry.visibility === 'tracked'
}

/** Whether "Extract facts" can run here: the text is on this machine, or the file is tracked. */
export function canExtract(entry: VaultEntry): boolean {
  return entry.kind !== 'fact' && (entry.available || hasTrackedFile(entry))
}

/** What a row says for an entry with no text here. A tracked file is in the repository, so its
 *  text is missing because it has not been read yet or reading it failed, not because another
 *  machine holds it (F591). */
export function withoutText(entry: VaultEntry): string {
  if (hasTrackedFile(entry)) return 'No text yet'
  return `Held on ${entry.holder ?? 'another machine'}`
}

/** "PDF" or "Image" for a file source; null for text. */
export function fileLabel(entry: Pick<VaultEntry, 'media_type'>): string | null {
  const kind = fileKindOf(entry.media_type)
  return kind === 'pdf' ? 'PDF' : kind === 'image' ? 'Image' : null
}
