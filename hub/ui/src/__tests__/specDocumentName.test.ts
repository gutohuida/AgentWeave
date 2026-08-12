import { describe, it, expect } from 'vitest'
import { documentPathFor, slugify } from '@/lib/specDocumentName'

/**
 * The operator types a title; the server requires a path that is lowercase,
 * POSIX, beneath `spec/`, and ends `.html`. These assertions are that contract
 * restated on the side that has to satisfy it — the server remains the
 * authority and refuses anything that slips through.
 */
describe('slugify', () => {
  it('lowercases and hyphenates what was typed', () => {
    expect(slugify('Budget App')).toBe('budget-app')
  })

  it('collapses runs of punctuation into single hyphens', () => {
    expect(slugify('Budget   app!! (v2)')).toBe('budget-app-v2')
  })

  it('drops accents rather than transliterating them', () => {
    expect(slugify('Café Ledger')).toBe('cafe-ledger')
  })

  it('never leaves a leading or trailing hyphen', () => {
    expect(slugify('  --Budget--  ')).toBe('budget')
  })

  it('bounds the length, and does not end on a hyphen after truncation', () => {
    const slug = slugify('a'.repeat(80))
    expect(slug.length).toBeLessThanOrEqual(64)
    expect(slug.endsWith('-')).toBe(false)
  })

  it('returns nothing for a title with no usable characters', () => {
    expect(slugify('!!! ???')).toBe('')
  })
})

describe('documentPathFor', () => {
  it('builds a path the server contract accepts', () => {
    const path = documentPathFor('Budget App')
    expect(path).toBe('spec/changes/budget-app/spec.html')
    expect(path).toMatch(/^spec\/[a-z0-9/-]+\.html$/)
    expect(path).toBe(path!.toLowerCase())
  })

  it('refuses a title that carries nothing to name a document with', () => {
    // Not a destructive surprise, unlike a project name — but a document with no
    // name is one nobody can find again.
    expect(documentPathFor('???')).toBeNull()
  })

  it('produces no dot or hidden segment', () => {
    const path = documentPathFor('.hidden thing')!
    expect(path.split('/').every((segment) => !segment.startsWith('.') || segment === '')).toBe(true)
    expect(path).toBe('spec/changes/hidden-thing/spec.html')
  })
})
