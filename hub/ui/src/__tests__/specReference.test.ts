import { describe, expect, it } from 'vitest'
import { findSpecReferences, formatSpecReference, parseSpecReferences } from '@/lib/specReference'

// The reference's text form (`reference-a-spec-in-a-sentence-from-the-composer`, design D1, FR-6).
describe('the text form of a spec reference', () => {
  it('names the kind, the title and the document id, as the design gives it', () => {
    expect(formatSpecReference({ id: 'spdoc-407caf5abcdb', title: 'The spec header, redesigned' })).toBe(
      '[spec: The spec header, redesigned](spdoc-407caf5abcdb)',
    )
  })

  it('never begins with @, which the Claude CLI would expand into a file (F409)', () => {
    const text = formatSpecReference({ id: 'spdoc-1', title: '@README.md' })
    expect(text.startsWith('@')).toBe(false)
    expect(parseSpecReferences(text)).toEqual([{ kind: 'spec', id: 'spdoc-1', title: '@README.md' }])
  })

  it('reads back the same references, in order, between plain text', () => {
    const a = { id: 'spdoc-aa', title: 'Ref A' }
    const b = { id: 'spdoc-bb', title: 'Ref B' }
    const text = `Compare ${formatSpecReference(a)} with ${formatSpecReference(b)} today`
    expect(parseSpecReferences(text)).toEqual([
      { kind: 'text', text: 'Compare ' },
      { kind: 'spec', ...a },
      { kind: 'text', text: ' with ' },
      { kind: 'spec', ...b },
      { kind: 'text', text: ' today' },
    ])
  })

  it('keeps a title holding brackets and backslashes intact', () => {
    const reference = { id: 'spdoc-cc', title: 'Odd [title] \\ with ](x) inside' }
    const text = `x ${formatSpecReference(reference)} y`
    expect(findSpecReferences(text)).toEqual([{ ...reference, start: 2, end: text.length - 2 }])
  })

  it('folds a title onto one line, and falls back to the id for an empty one', () => {
    expect(formatSpecReference({ id: 'spdoc-dd', title: 'two\nlines ' })).toBe('[spec: two lines](spdoc-dd)')
    expect(formatSpecReference({ id: 'spdoc-ee', title: '  ' })).toBe('[spec: spdoc-ee](spdoc-ee)')
  })

  it('reads plain text and other links as text', () => {
    const text = 'see [docs](https://example.com) and [spec: x](not-an-id)'
    expect(parseSpecReferences(text)).toEqual([{ kind: 'text', text }])
    expect(parseSpecReferences('')).toEqual([])
  })
})
