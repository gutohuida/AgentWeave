import { describe, expect, it } from 'vitest'
import { listEntries } from '@/components/spec/page/adapt'
import { arrangeList, DEFAULT_LIST_PREFERENCES, SHOWN_LABEL } from '@/components/spec/page/model'
import type { SpecDocumentRecord, SpecEntry } from '@/api/spec'

// The shapes `GET /specs` and `GET /documents` return: `display_phase` rides next to `phase`.
const spec = (path: string, display_phase: string | null, phase = 'approved'): SpecEntry =>
  ({ path, phase, display_phase, document_id: `id-${path}`, kind: 'change-spec', title: path }) as SpecEntry
const record = (path: string, display_phase: SpecDocumentRecord['display_phase'], phase: SpecDocumentRecord['phase'] = 'approved') =>
  ({ id: `id-${path}`, path, title: path, kind: 'change-spec', phase, display_phase, updated_at: '2026-10-29T12:00:00Z' }) as SpecDocumentRecord

describe('a built spec reads Building or Done (F1089)', () => {
  const specs = [spec('a', 'approved'), spec('b', 'building'), spec('c', 'done'), spec('d', 'archived', 'archived'), spec('e', 'exploring', 'exploring')]
  const records = [record('a', 'approved'), record('b', 'building'), record('c', 'done'), record('d', 'archived', 'archived'), record('e', 'exploring', 'exploring')]

  it('shows the Hub display_phase in the list', () => {
    const shown = Object.fromEntries(listEntries(specs, records).map((e) => [e.path, SHOWN_LABEL[e.shown]]))
    expect(shown).toEqual({ a: 'Approved', b: 'Building', c: 'Done', d: 'Archived', e: 'Writing' })
  })

  it('does not change the state that drives the actions', () => {
    const states = Object.fromEntries(listEntries(specs, records).map((e) => [e.path, e.state]))
    expect(states.c).toBe('approved')
  })

  it('falls back to the state when the Hub predates display_phase', () => {
    const [entry] = listEntries([spec('a', null)], [])
    expect(entry.shown).toBe('approved')
  })

  it('groups Done apart from Approved when ordered by phase', () => {
    const groups = arrangeList(listEntries(specs, records), { ...DEFAULT_LIST_PREFERENCES, order: 'phase' })
    expect(groups.map((g) => [g.label, g.entries.map((e) => e.path)])).toEqual([
      ['Building', ['b']],
      ['Writing', ['e']],
      ['Approved', ['a']],
      ['Done', ['c']],
      ['Archived', ['d']],
    ])
  })
})
