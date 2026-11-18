import { beforeEach, describe, expect, it } from 'vitest'
import {
  insertAtSelection,
  pointAtOffset,
  readEditor,
  readSelection,
  renderEditor,
  selectOffsets,
  setCaret,
  specBoxHtml,
} from '@/lib/composerEditor'
import { formatSpecReference } from '@/lib/specReference'

const REF = { id: 'spdoc-aa', title: 'Ref <A> & "B"' }
const TOKEN = formatSpecReference(REF)

let field: HTMLDivElement
beforeEach(() => {
  document.body.innerHTML = ''
  field = document.createElement('div')
  field.contentEditable = 'true'
  document.body.appendChild(field)
})

describe('the composer field as text (FR-7: a draft keeps its boxes)', () => {
  it('draws each reference as one box and reads the same text back', () => {
    const text = `see ${TOKEN} now\nnext line`
    renderEditor(field, text)
    const boxes = field.querySelectorAll('[data-spec-box]')
    expect(boxes).toHaveLength(1)
    expect(boxes[0].getAttribute('contenteditable')).toBe('false')
    expect(boxes[0].textContent).toBe(REF.title)
    expect(boxes[0].querySelector('.composer-spec-box-icon')).not.toBeNull()
    expect(readEditor(field).text).toBe(text)
  })

  it('keeps a final newline, and ignores the browser’s filler at the end', () => {
    renderEditor(field, 'line\n')
    expect(field.textContent).toBe('line\n\n')
    expect(readEditor(field).text).toBe('line\n')
    // What Chromium writes for 'one', Shift+Enter: the second newline only gives the caret a line.
    field.replaceChildren('one', '\n', '\n')
    expect(readEditor(field).text).toBe('one\n')
    field.replaceChildren('one\n')
    expect(readEditor(field).text).toBe('one')
    field.innerHTML = 'one<br>two<br>'
    expect(readEditor(field).text).toBe('one\ntwo')
  })

  it('reads a line the browser wrapped in a block', () => {
    field.innerHTML = 'one<div>two</div>'
    expect(readEditor(field).text).toBe('one\ntwo')
  })

  it('counts a box as its whole token for offsets, and never puts the caret inside it', () => {
    renderEditor(field, `see ${TOKEN} now`)
    const afterBox = 4 + TOKEN.length
    expect(pointAtOffset(field, 4)).toEqual({ node: field.firstChild, offset: 4 })
    expect(pointAtOffset(field, afterBox)).toEqual({ node: field, offset: 2 })
    setCaret(field, afterBox + 1)
    expect(readSelection(field)).toEqual({ start: afterBox + 1, end: afterBox + 1 })

    // A caret the browser left inside the box reads as just after it.
    const box = field.querySelector('[data-spec-box]')!
    const range = document.createRange()
    range.setStart(box.lastChild!, 2)
    getSelection()!.removeAllRanges()
    getSelection()!.addRange(range)
    expect(readSelection(field)).toEqual({ start: afterBox, end: afterBox })
  })

  it('replaces a selected range with a box by hand where the browser has no editing command', () => {
    renderEditor(field, 'The spec @ref')
    selectOffsets(field, 9, 13)
    insertAtSelection(field, { html: specBoxHtml(REF) + ' ' })
    expect(readEditor(field).text).toBe(`The spec ${TOKEN} `)
    expect(readSelection(field)).toEqual({ start: 9 + TOKEN.length + 1, end: 9 + TOKEN.length + 1 })
  })

  it('escapes a title as text, so it cannot inject markup', () => {
    renderEditor(field, formatSpecReference({ id: 'spdoc-bb', title: '<img src=x onerror=alert(1)>' }))
    expect(field.querySelector('img')).toBeNull()
    expect(field.querySelector('[data-spec-box]')?.getAttribute('data-title')).toBe('<img src=x onerror=alert(1)>')
  })
})
