import { describe, expect, it } from 'vitest'
import { detectComposerTrigger } from '@/lib/composerTrigger'
import {
  MAX_SPEC_RESULTS,
  resolveSpecResults,
  resolveTriggerResults,
  type SpecReferenceTarget,
} from '@/lib/composerTriggerSources'
import { formatSpecReference } from '@/lib/specReference'

const doc = (n: number, title: string, updated_at: string): SpecReferenceTarget => ({
  id: `spdoc-${String(n).padStart(12, '0')}`,
  title,
  path: `spec/changes/doc-${n}/spec.json`,
  updated_at,
})

// In the order `GET /project/documents` returns them: insertion order, oldest row first. The route
// does not sort (hub/hub/spec_lifecycle.py list_documents has no ORDER BY), so the menu must.
// A, B and C all contain 'ref'; by update time C is newest, then A, then B.
const A = doc(2, 'Ref A: reference boxes', '2026-11-17T10:00:00+00:00')
const B = doc(3, 'Ref B: older reference', '2026-11-10T10:00:00+00:00')
const C = doc(5, 'Ref C: newest reference', '2026-11-18T11:00:00+00:00')
const ROUTE_ORDER: SpecReferenceTarget[] = [
  doc(1, 'SPEC-1', '2026-11-18T12:00:00+00:00'),
  A,
  B,
  doc(4, 'The spec header, redesigned', '2026-11-12T09:00:00+00:00'),
  C,
  ...[6, 7, 8, 9, 10, 11, 12].map((n) => doc(n, `Other ${n}`, `2026-11-0${n - 5}T09:00:00+00:00`)),
]

const atQuery = (query: string) => detectComposerTrigger('@' + query, query.length + 1)!

describe('the @ menu lists specs (FR-1, specs-by-recency)', () => {
  it('shows exactly 10 specs for @ alone, most recently updated first', () => {
    const titles = resolveSpecResults('', ROUTE_ORDER).map((spec) => spec.title)
    expect(ROUTE_ORDER.length).toBeGreaterThan(MAX_SPEC_RESULTS)
    expect(titles).toHaveLength(10)
    expect(titles.slice(0, 5)).toEqual(['SPEC-1', C.title, A.title, 'The spec header, redesigned', B.title])
    expect(titles).not.toContain('Other 6') // the two oldest fall off
    expect(titles).not.toContain('Other 7')
  })

  it('filters by the query and keeps the recency order rather than re-ranking: C, A, B', () => {
    expect(resolveSpecResults('ref', ROUTE_ORDER).map((spec) => spec.title)).toEqual([C.title, A.title, B.title])
  })

  it('does not take the route order for recency: reversed, the result is the same', () => {
    expect(resolveSpecResults('ref', [...ROUTE_ORDER].reverse())).toEqual(resolveSpecResults('ref', ROUTE_ORDER))
  })

  it('matches on the path as well as the title, case-insensitively', () => {
    expect(resolveSpecResults('DOC-4/', ROUTE_ORDER).map((spec) => spec.title)).toEqual(['The spec header, redesigned'])
    expect(resolveSpecResults('HEAD', ROUTE_ORDER).map((spec) => spec.title)).toEqual(['The spec header, redesigned'])
  })

  it('puts a document with no update time last', () => {
    const undated = { ...doc(13, 'Ref D: undated', ''), updated_at: null }
    expect(resolveSpecResults('ref', [undated, ...ROUTE_ORDER]).map((spec) => spec.title)).toEqual([
      C.title,
      A.title,
      B.title,
      'Ref D: undated',
    ])
  })
})

describe('the @ menu groups specs above files (FR-1, menu-has-both-groups)', () => {
  const paths = ['README.md', 'hub/ui/src/components/spec/SpecDocumentHeader.tsx', 'docs/headless.md']

  it('lists the Specs group first, then the Files group, as one flat list', () => {
    const items = resolveTriggerResults(atQuery('head'), paths, ROUTE_ORDER)
    expect(items.map((item) => [item.group, item.label])).toEqual([
      ['Specs', 'The spec header, redesigned'],
      ['Files', 'hub/ui/src/components/spec/SpecDocumentHeader.tsx'],
      ['Files', 'docs/headless.md'],
    ])
    expect(items[0].spec).toEqual({ id: 'spdoc-000000000004', title: 'The spec header, redesigned' })
    expect(items[1].spec).toBeUndefined()
  })

  it('keeps today’s file results, without headings, when no spec matches', () => {
    expect(resolveTriggerResults(atQuery('README'), paths, ROUTE_ORDER)).toEqual([
      { value: 'README.md', label: 'README.md' },
    ])
  })

  it('offers no specs for $ or /', () => {
    expect(resolveTriggerResults(detectComposerTrigger('$ref', 4)!, paths, ROUTE_ORDER)).toEqual([])
    expect(resolveTriggerResults(detectComposerTrigger('/mod', 4)!, paths, ROUTE_ORDER).map((i) => i.value)).toEqual([
      'model',
    ])
  })
})

describe('a trigger next to a box (the box is one unit)', () => {
  const box = formatSpecReference({ id: 'spdoc-aa', title: 'An @odd title' })

  it('opens for @ typed straight after a box, with its range starting after the box', () => {
    const text = `see ${box}@hea`
    expect(detectComposerTrigger(text, text.length)).toEqual({
      kind: 'path',
      query: 'hea',
      rangeStart: text.length - 4,
      rangeEnd: text.length,
    })
  })

  it('never opens inside a box’s own text, even where its title holds an @', () => {
    const text = `see ${box}`
    for (let cursor = 5; cursor <= text.length; cursor++) {
      expect(detectComposerTrigger(text, cursor)).toBeNull()
    }
    expect(detectComposerTrigger(`${text}x`, text.length + 1)).toBeNull()
  })

  it('still opens a slash command at a line start below a box', () => {
    const text = `${box}\n/mod`
    expect(detectComposerTrigger(text, text.length)?.kind).toBe('slash-command')
  })
})
