// The composer's editable field as text (`reference-a-spec-in-a-sentence-from-the-composer`, D5).
// The field is a contenteditable element whose content is plain text plus spec boxes; its value is
// a string in which each box is its reference's text form (`specReference.ts`). Every offset here
// is an offset into that string, so a box counts as its whole token and the caret is never inside
// one. Chromium makes a `contenteditable="false"` box one character for Backspace, Delete and the
// arrows natively (spike RSSC-1, testbed/composer-box-spike/NOTES.md), so nothing here handles keys.

import { formatSpecReference, parseSpecReferences, type SpecReference } from './specReference'

export const SPEC_BOX_CLASS = 'composer-spec-box'

const TEXT_NODE = 3
const ELEMENT_NODE = 1

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

/** A box as markup, for `insertHTML` (which keeps the browser's undo stack) and for rendering.
 *  The icon is an empty span the stylesheet draws (`.composer-spec-box-icon`, lucide's FileText as
 *  a mask), and the title is bare text after it: Chromium's `insertHTML` reports failure, and leaves
 *  the caret before the box, for a box whose last child is an element (an `<svg>`, a `<span>`). */
export function specBoxHtml(reference: SpecReference): string {
  const title = escapeHtml(reference.title)
  return (
    `<span class="${SPEC_BOX_CLASS}" contenteditable="false" data-spec-box="" data-id="${escapeHtml(reference.id)}" ` +
    `data-title="${title}" title="${title}"><span class="${SPEC_BOX_CLASS}-icon" aria-hidden="true"></span>` +
    `${title}</span>`
  )
}

export function isSpecBox(node: Node | null | undefined): node is HTMLElement {
  return !!node && node.nodeType === ELEMENT_NODE && (node as HTMLElement).dataset?.specBox !== undefined
}

/** The box `node` sits in, if any (the box itself counts). */
export function enclosingSpecBox(root: HTMLElement, node: Node | null): HTMLElement | null {
  for (let at: Node | null = node; at && at !== root; at = at.parentNode) {
    if (isSpecBox(at)) return at
  }
  return null
}

function boxReference(box: HTMLElement): SpecReference {
  return { id: box.dataset.id ?? '', title: box.dataset.title ?? box.textContent ?? '' }
}

/** A `<br>` with nothing after it up to the root is the browser's end-of-field filler, not a line. */
function isTrailingBreak(root: HTMLElement, br: Node): boolean {
  for (let at: Node | null = br; at && at !== root; at = at.parentNode) {
    if (at.nextSibling) return false
  }
  return true
}

export interface DomPoint {
  node: Node
  offset: number
}

/**
 * The field's value, and the string offset of each of `points`. A point inside a box reads as
 * just after it. A point the walk never meets (outside the field) comes back as null.
 *
 * Under `white-space: pre-wrap` a `\n` ending the last text draws no line, so Chromium follows a
 * typed final newline with a second one to give the caret its line: that last `\n` is a filler
 * and is not read, as a filler `<br>` is not.
 */
export function readEditor(root: HTMLElement, points: DomPoint[] = []): { text: string; offsets: Array<number | null> } {
  let out = ''
  let endsInTextNewline = false
  const offsets: Array<number | null> = points.map(() => null)
  const markBoundary = (container: Node, index: number) => {
    points.forEach((p, i) => {
      if (offsets[i] === null && p.node === container && p.offset === index) offsets[i] = out.length
    })
  }
  const walk = (container: Node) => {
    const kids = container.childNodes
    for (let i = 0; i <= kids.length; i++) {
      markBoundary(container, i)
      const child = kids[i]
      if (!child) break
      if (child.nodeType === TEXT_NODE) {
        const data = (child as Text).data
        points.forEach((p, k) => {
          if (offsets[k] === null && p.node === child) offsets[k] = out.length + Math.min(p.offset, data.length)
        })
        out += data
        if (data) endsInTextNewline = data.endsWith('\n')
      } else if (isSpecBox(child)) {
        out += formatSpecReference(boxReference(child))
        endsInTextNewline = false
        points.forEach((p, k) => {
          if (offsets[k] === null && child.contains(p.node)) offsets[k] = out.length
        })
      } else if (child.nodeName === 'BR') {
        if (!isTrailingBreak(root, child)) {
          out += '\n'
          endsInTextNewline = false
        }
      } else if (child.nodeName === 'DIV' || child.nodeName === 'P') {
        // A block the browser made for a new line: it starts one, unless it opens the field.
        if (out.length > 0 && !out.endsWith('\n')) {
          out += '\n'
          endsInTextNewline = false
        }
        walk(child)
      } else if (child.nodeType === ELEMENT_NODE) {
        walk(child)
      }
    }
  }
  walk(root)
  if (endsInTextNewline) {
    out = out.slice(0, -1)
    offsets.forEach((offset, i) => {
      if (offset !== null && offset > out.length) offsets[i] = out.length
    })
  }
  return { text: out, offsets }
}

/** The DOM point at string offset `offset` (clamped), never inside a box. */
export function pointAtOffset(root: HTMLElement, offset: number): DomPoint {
  let consumed = 0
  let found: DomPoint | null = null
  const walk = (container: Node): boolean => {
    const kids = container.childNodes
    for (let i = 0; i < kids.length; i++) {
      const child = kids[i]
      if (child.nodeType === TEXT_NODE) {
        const length = (child as Text).data.length
        if (offset <= consumed + length) {
          found = { node: child, offset: offset - consumed }
          return true
        }
        consumed += length
      } else if (isSpecBox(child)) {
        if (offset <= consumed) {
          found = { node: container, offset: i }
          return true
        }
        consumed += formatSpecReference(boxReference(child)).length
        if (offset <= consumed) {
          found = { node: container, offset: i + 1 }
          return true
        }
      } else if (child.nodeName === 'BR') {
        if (isTrailingBreak(root, child)) continue
        if (offset <= consumed) {
          found = { node: container, offset: i }
          return true
        }
        consumed += 1
      } else if (child.nodeType === ELEMENT_NODE) {
        if (walk(child)) return true
      }
    }
    return false
  }
  if (walk(root) && found) return found
  // Past the end: before a trailing filler break, else at the very end.
  const last = root.lastChild
  if (last && last.nodeName === 'BR') return { node: root, offset: root.childNodes.length - 1 }
  return { node: root, offset: root.childNodes.length }
}

/** Replace the field's content with `text`, each reference drawn as a box. */
export function renderEditor(root: HTMLElement, text: string): void {
  const template = document.createElement('template')
  template.innerHTML = editorHtml(text)
  root.replaceChildren(template.content)
  // A final newline needs a filler, or the empty last line has no height and no caret: the same
  // second `\n` Chromium writes when the operator types one (see `readEditor`).
  if (text.endsWith('\n')) root.appendChild(document.createTextNode('\n'))
}

export function setCaret(root: HTMLElement, offset: number): void {
  const point = pointAtOffset(root, offset)
  const selection = window.getSelection()
  if (!selection) return
  const range = document.createRange()
  range.setStart(point.node, point.offset)
  range.collapse(true)
  selection.removeAllRanges()
  selection.addRange(range)
}

export function selectOffsets(root: HTMLElement, start: number, end: number): void {
  const from = pointAtOffset(root, start)
  const to = pointAtOffset(root, end)
  const selection = window.getSelection()
  if (!selection) return
  const range = document.createRange()
  range.setStart(from.node, from.offset)
  range.setEnd(to.node, to.offset)
  selection.removeAllRanges()
  selection.addRange(range)
}

/** The selection as string offsets within the field, or null when it is not in the field. */
export function readSelection(root: HTMLElement): { start: number; end: number } | null {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return null
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null
  const { offsets } = readEditor(root, [
    { node: range.startContainer, offset: range.startOffset },
    { node: range.endContainer, offset: range.endOffset },
  ])
  if (offsets[0] === null || offsets[1] === null) return null
  return { start: offsets[0], end: offsets[1] }
}

function execCommand(command: string, value?: string): boolean {
  try {
    return typeof document.execCommand === 'function' && document.execCommand(command, false, value)
  } catch {
    return false
  }
}

/**
 * Replace the selection with `html` (or plain `text`), through the browser's editing commands
 * where it has them so the change joins the undo stack (spike: a direct DOM change breaks undo),
 * else by hand. Leaves the caret after what was inserted.
 */
export function insertAtSelection(root: HTMLElement, content: { html: string } | { text: string }): void {
  // Judged by whether the field changed, not by the command's answer, which can be false for an
  // insertion that happened.
  const before = root.innerHTML
  const ok = 'html' in content ? execCommand('insertHTML', content.html) : execCommand('insertText', content.text)
  if (ok || root.innerHTML !== before) return
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer)) return
  range.deleteContents()
  let fragment: DocumentFragment
  if ('html' in content) {
    const template = document.createElement('template')
    template.innerHTML = content.html
    fragment = template.content
  } else {
    fragment = document.createDocumentFragment()
    fragment.appendChild(document.createTextNode(content.text))
  }
  const last = fragment.lastChild
  range.insertNode(fragment)
  if (last) {
    range.setStartAfter(last)
    range.collapse(true)
    selection.removeAllRanges()
    selection.addRange(range)
  }
  root.normalize()
}

export function deleteSelection(root: HTMLElement): void {
  if (execCommand('delete')) return
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return
  const range = selection.getRangeAt(0)
  if (root.contains(range.startContainer)) range.deleteContents()
}

/** Markup for `text` with its references as boxes, for a paste that carries references. */
export function editorHtml(text: string): string {
  return parseSpecReferences(text)
    .map((segment) => (segment.kind === 'spec' ? specBoxHtml(segment) : escapeHtml(segment.text)))
    .join('')
}
