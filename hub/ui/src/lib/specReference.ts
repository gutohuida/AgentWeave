// The text form of a boxed spec reference (`reference-a-spec-in-a-sentence-from-the-composer`,
// design D1): `[spec: <title at send time>](<document id>)`. A reference is stored, drafted, sent and
// copied as this text, so history, drafts and every runner keep working; the composer and the
// timeline draw it as a box. It names the kind so an agent knows which tool opens it, carries the
// document id because the path changes on rename (D2), and never begins with `@`, which the Claude
// CLI would expand into a file attachment (F409). This module is the only place the form is defined.

export interface SpecReference {
  id: string
  title: string
}

export type ReferenceSegment = { kind: 'text'; text: string } | { kind: 'spec'; id: string; title: string }

export interface FoundReference extends SpecReference {
  start: number
  end: number
}

// The id is the Hub's document id (`spdoc-` + hex); a title escapes `\` and `]` with a backslash.
const REFERENCE_RE = /\[spec: ((?:[^\]\\\n]|\\[\\\]])*)\]\((spdoc-[A-Za-z0-9]+)\)/g

/** A title as it can stand inside the brackets: one line, with `\` and `]` escaped. */
function escapeTitle(title: string): string {
  return title.replace(/\s+/g, ' ').trim().replace(/[\\\]]/g, (c) => '\\' + c)
}

function unescapeTitle(title: string): string {
  return title.replace(/\\([\\\]])/g, '$1')
}

export function formatSpecReference(reference: SpecReference): string {
  return `[spec: ${escapeTitle(reference.title) || reference.id}](${reference.id})`
}

/** Every reference in `text`, in order, with its `[start, end)` range. */
export function findSpecReferences(text: string): FoundReference[] {
  const found: FoundReference[] = []
  for (const match of text.matchAll(REFERENCE_RE)) {
    const start = match.index ?? 0
    found.push({ id: match[2], title: unescapeTitle(match[1]), start, end: start + match[0].length })
  }
  return found
}

/** `text` split into plain runs and references, in order; adjacent text is never split. */
export function parseSpecReferences(text: string): ReferenceSegment[] {
  const segments: ReferenceSegment[] = []
  let at = 0
  for (const reference of findSpecReferences(text)) {
    if (reference.start > at) segments.push({ kind: 'text', text: text.slice(at, reference.start) })
    segments.push({ kind: 'spec', id: reference.id, title: reference.title })
    at = reference.end
  }
  if (at < text.length) segments.push({ kind: 'text', text: text.slice(at) })
  return segments
}
