import { describe, expect, it } from 'vitest'
import { listEntries } from '@/components/spec/page/adapt'
import { arrangeList, DEFAULT_LIST_PREFERENCES } from '@/components/spec/page/model'
import type { SpecDocumentRecord, SpecEntry } from '@/api/spec'

// `GET /documents` as the Hub returns it: each change names its roadmap in its own file, with the
// slice's place in the roadmap's build order; the spec index records no parent for either.
const ROADMAP = 'spec/changes/the-roadmap/spec.json'
const entry = (path: string, kind: string): SpecEntry =>
  ({ path, phase: 'approved', document_id: `id-${path}`, kind, title: path }) as SpecEntry
const record = (path: string, kind: string, extra: Partial<SpecDocumentRecord> = {}) =>
  ({ id: `id-${path}`, path, title: path, kind, phase: 'approved', display_phase: 'approved', updated_at: '2026-11-02T12:00:00Z', ...extra }) as SpecDocumentRecord

describe('a slice is listed under the roadmap it names (FR-9)', () => {
  const specs = [entry(ROADMAP, 'roadmap'), entry('spec/changes/b/spec.json', 'change-spec'), entry('spec/changes/a/spec.json', 'change-spec')]
  const records = [
    record(ROADMAP, 'roadmap'),
    record('spec/changes/b/spec.json', 'change-spec', { roadmap: { document: ROADMAP, slice: 'b', order: 1 } }),
    record('spec/changes/a/spec.json', 'change-spec', { roadmap: { document: ROADMAP, slice: 'a', order: 0 } }),
  ]

  it('groups both under the roadmap, slice a first, and none under Not in a roadmap', () => {
    const groups = arrangeList(listEntries(specs, records), { ...DEFAULT_LIST_PREFERENCES, order: 'roadmap' })
    expect(groups.map((g) => [g.roadmap?.path ?? g.label, g.entries.map((e) => e.path)])).toEqual([
      [ROADMAP, ['spec/changes/a/spec.json', 'spec/changes/b/spec.json']],
    ])
  })

  it('carries a waiting reason from the route', () => {
    const [, , a] = listEntries(
      specs,
      [records[0], records[1], { ...records[2], waiting: ['amendments_to_review'], amendments: { total: 2, unreviewed: 2 } }],
    )
    expect(a.waiting).toBe('2 amendments to review')
  })

  it('says "1 amendment to review" for exactly one', () => {
    const [, , a] = listEntries(
      specs,
      [records[0], records[1], { ...records[2], waiting: ['amendments_to_review'], amendments: { total: 1, unreviewed: 1 } }],
    )
    expect(a.waiting).toBe('1 amendment to review')
  })
})

describe('Not archived hides an archived slice under a live roadmap', () => {
  const live = 'spec/changes/live/spec.json'
  const gone = 'spec/changes/gone/spec.json'
  const specs = [entry(ROADMAP, 'roadmap'), entry(live, 'change-spec'), { ...entry(gone, 'change-spec'), phase: 'archived' } as SpecEntry]
  const records = [
    record(ROADMAP, 'roadmap'),
    record(live, 'change-spec', { roadmap: { document: ROADMAP, slice: 'live', order: 0 } }),
    record(gone, 'change-spec', { phase: 'archived', display_phase: 'archived', roadmap: { document: ROADMAP, slice: 'gone', order: 1 } }),
  ]

  it('lists the roadmap with its live slice only', () => {
    const groups = arrangeList(listEntries(specs, records), { ...DEFAULT_LIST_PREFERENCES, order: 'roadmap', phase: 'unarchived' })
    expect(groups.map((g) => [g.roadmap?.path ?? g.label, g.entries.map((e) => e.path)])).toEqual([[ROADMAP, [live]]])
  })

  it('Any phase still shows both', () => {
    const groups = arrangeList(listEntries(specs, records), { ...DEFAULT_LIST_PREFERENCES, order: 'roadmap' })
    expect(groups.map((g) => [g.roadmap?.path ?? g.label, g.entries.map((e) => e.path)])).toEqual([[ROADMAP, [live, gone]]])
  })
})
