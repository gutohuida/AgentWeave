import { describe, it, expect } from 'vitest'
import type { SpecListResponse } from '@/api/spec'
import {
  buildInventory,
  resolveSelection,
  searchDocuments,
  ARCHIVE_PREFIX,
} from '@/components/spec/specNavigation'

const ROADMAP = 'spec/roadmaps/agentweave-reconstruction.json'
const OTHER_ROADMAP = 'spec/roadmaps/hub-hardening.json'

function response(partial: Partial<SpecListResponse> = {}): SpecListResponse {
  return {
    specs: [],
    home: null,
    manifest: null,
    missing: [],
    diagnostics: [],
    ...partial,
  }
}

// A realistic filed document. `state` defaults to filed because the manifest
// covers it; the projection must not invent metadata for anything else.
function filed(path: string, extra: Record<string, unknown> = {}) {
  return {
    path,
    title: path,
    kind: 'change-spec' as const,
    status: 'approved',
    parent: null,
    order: 10,
    state: 'filed' as const,
    ...extra,
  }
}

describe('spec navigation — current library projection (FR-1)', () => {
  it('nests filed children under their present parent', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/changes/add-spec-navigation/spec.json', {
            title: 'Add Spec Navigation',
            parent: ROADMAP,
            order: 10,
          }),
          filed(ROADMAP, { title: 'Roadmap', kind: 'roadmap', parent: null, order: 30 }),
        ],
      })
    )

    expect(inv.library).toHaveLength(1)
    expect(inv.library[0].node.path).toBe(ROADMAP)
    expect(inv.library[0].children.map((c) => c.node.path)).toEqual([
      'spec/changes/add-spec-navigation/spec.json',
    ])
    expect(inv.needsAttention).toHaveLength(0)
  })

  it('orders siblings by manifest order, then title, then path', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/c.json', { title: 'C', order: 30 }),
          filed('spec/a.json', { title: 'A', order: 10 }),
          filed('spec/b2.json', { title: 'Same', order: 20 }),
          filed('spec/b1.json', { title: 'Same', order: 20 }),
          filed('spec/b0.json', { title: 'Earlier', order: 20 }),
        ],
      })
    )

    // order first; within equal order, title; within equal title, path
    expect(inv.library.map((n) => n.node.path)).toEqual([
      'spec/a.json',
      'spec/b0.json',
      'spec/b1.json',
      'spec/b2.json',
      'spec/c.json',
    ])
  })

  it('keeps unindexed and unfiled documents visible under Needs attention', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/agentweave-spec.json', { title: 'Baseline', kind: 'baseline' }),
          { path: 'spec/scratch.json', state: 'unindexed' as const },
          { path: 'spec/orphan.json', state: 'unfiled' as const },
        ],
      })
    )

    expect(inv.library.map((n) => n.node.path)).toEqual(['spec/agentweave-spec.json'])
    expect(inv.needsAttention.map((n) => n.path).sort()).toEqual([
      'spec/orphan.json',
      'spec/scratch.json',
    ])
    // visible, not dropped
    expect(inv.nodes).toHaveLength(3)
  })

  it('treats a filed node whose parent is absent as parent-orphaned, not a root', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/changes/x/spec.json', { title: 'X', parent: 'spec/roadmaps/gone.json' }),
        ],
      })
    )

    expect(inv.library).toHaveLength(0)
    expect(inv.needsAttention.map((n) => n.path)).toEqual(['spec/changes/x/spec.json'])
  })

  it('lists missing manifest entries under Needs attention and marks them unreadable', () => {
    const inv = buildInventory(
      response({
        specs: [filed(ROADMAP, { title: 'Roadmap', kind: 'roadmap' })],
        missing: [
          {
            path: 'spec/changes/deleted/spec.json',
            title: 'Deleted',
            kind: 'change-spec',
            status: 'approved',
            parent: ROADMAP,
            order: 10,
          },
        ],
      })
    )

    const node = inv.needsAttention.find((n) => n.path === 'spec/changes/deleted/spec.json')
    expect(node).toBeDefined()
    expect(node?.missing).toBe(true)
    // a missing entry must never be nested into the readable library
    expect(inv.library[0].children).toHaveLength(0)
  })
})

describe('spec navigation — history separation (FR-2)', () => {
  const archivedA = `${ARCHIVE_PREFIX}2026-07-29-add-agent-stream-kinds/spec.json`
  const archivedB = `${ARCHIVE_PREFIX}2026-07-01-add-spec-manifest/spec.json`
  const archivedC = `${ARCHIVE_PREFIX}2026-06-15-hub-auth/spec.json`
  const archivedOrphan = `${ARCHIVE_PREFIX}2026-05-02-standalone/spec.json`

  const inv = buildInventory(
    response({
      specs: [
        filed(ROADMAP, { title: 'Reconstruction', kind: 'roadmap', parent: null, order: 30 }),
        filed(OTHER_ROADMAP, { title: 'Hub Hardening', kind: 'roadmap', parent: null, order: 40 }),
        filed('spec/changes/active/spec.json', { title: 'Active', parent: ROADMAP }),
        filed(archivedB, { title: 'Add Spec Manifest', parent: ROADMAP }),
        filed(archivedA, { title: 'Add Agent Stream Kinds', parent: ROADMAP }),
        filed(archivedC, { title: 'Hub Auth', parent: OTHER_ROADMAP }),
        filed(archivedOrphan, { title: 'Standalone', parent: null }),
      ],
    })
  )

  it('excludes archived paths from the default library entirely', () => {
    const paths: string[] = []
    const walk = (nodes: typeof inv.library) => {
      for (const n of nodes) {
        paths.push(n.node.path)
        walk(n.children)
      }
    }
    walk(inv.library)

    expect(paths).toContain('spec/changes/active/spec.json')
    for (const archived of [archivedA, archivedB, archivedC, archivedOrphan]) {
      expect(paths).not.toContain(archived)
    }
    // and they are not smuggled in as drift either
    expect(inv.needsAttention.map((n) => n.path)).not.toContain(archivedA)
  })

  it('groups history by parent roadmap, newest first, with unparented under Other changes', () => {
    const groups = inv.history.map((g) => ({
      label: g.label,
      paths: g.entries.map((e) => e.path),
    }))

    const reconstruction = groups.find((g) => g.label === 'Reconstruction')
    expect(reconstruction?.paths).toEqual([archivedA, archivedB]) // 07-29 before 07-01

    const hardening = groups.find((g) => g.label === 'Hub Hardening')
    expect(hardening?.paths).toEqual([archivedC])

    const other = groups.find((g) => g.label === 'Other changes')
    expect(other?.paths).toEqual([archivedOrphan])
    // Other changes sorts last
    expect(groups[groups.length - 1].label).toBe('Other changes')
  })

  it('parses the archive date and change name from the archive directory', () => {
    const node = inv.byPath.get(archivedA)
    expect(node?.archived).toBe(true)
    expect(node?.archiveDate).toBe('2026-07-29')
    expect(node?.changeName).toBe('add-agent-stream-kinds')
  })

  it('falls back to path ordering when an archive directory has no leading date', () => {
    const undated = `${ARCHIVE_PREFIX}no-date-change/spec.json`
    const dated = `${ARCHIVE_PREFIX}2026-01-01-dated/spec.json`
    const local = buildInventory(
      response({
        specs: [filed(undated, { title: 'Undated' }), filed(dated, { title: 'Dated' })],
      })
    )

    const group = local.history[0]
    // dated entries sort ahead of undated ones rather than throwing
    expect(group.entries.map((e) => e.path)).toEqual([dated, undated])
    expect(local.byPath.get(undated)?.archiveDate).toBeNull()
  })

  it('treats a phase-archived document as archived even though its file never moved', () => {
    // Archiving is a phase transition (`POST .../documents/phase?to=archived`); it does not
    // relocate the file. A document can be archived while its path still sits under
    // `spec/changes/<name>/`, nowhere near ARCHIVE_PREFIX — the Hub's own phase is the only signal
    // for that case, and the tree has to check it or the document reads as an ordinary current one.
    const path = 'spec/changes/quiet-hours-for-agent-notifications/spec.json'
    const local = buildInventory(
      response({
        specs: [filed(path, { title: 'Quiet hours', phase: 'archived' })],
      })
    )

    const node = local.byPath.get(path)
    expect(node?.archived).toBe(true)
    expect(node?.archiveDate).toBeNull()

    const paths: string[] = []
    const walk = (nodes: typeof local.library) => {
      for (const n of nodes) {
        paths.push(n.node.path)
        walk(n.children)
      }
    }
    walk(local.library)
    expect(paths).not.toContain(path)
    expect(local.history.flatMap((g) => g.entries.map((e) => e.path))).toContain(path)
  })
})

describe('spec navigation — selection fallback (FR-4)', () => {
  const base = response({
    specs: [
      filed('spec/spec.json', { title: 'Spec', kind: 'baseline' }),
      filed(ROADMAP, { title: 'Roadmap', kind: 'roadmap' }),
      filed(`${ARCHIVE_PREFIX}2026-07-29-old/spec.json`, { title: 'Old' }),
    ],
    home: ROADMAP,
  })

  it('keeps the current selection while its path stays readable', () => {
    const inv = buildInventory(base)
    expect(resolveSelection(inv, 'spec/spec.json', ROADMAP)).toBe('spec/spec.json')
  })

  it('keeps an archived selection the user chose explicitly', () => {
    const inv = buildInventory(base)
    const archived = `${ARCHIVE_PREFIX}2026-07-29-old/spec.json`
    expect(resolveSelection(inv, archived, ROADMAP)).toBe(archived)
  })

  it('falls back to manifest home when the selection disappears', () => {
    const inv = buildInventory(base)
    expect(resolveSelection(inv, 'spec/gone.json', ROADMAP)).toBe(ROADMAP)
  })

  it('falls back to spec/spec.json when home is unreadable', () => {
    const inv = buildInventory(base)
    expect(resolveSelection(inv, null, 'spec/missing-home.json')).toBe('spec/spec.json')
  })

  it('falls back to the first readable current document when home and spec.json are gone', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/b.json', { title: 'B', order: 20 }),
          filed('spec/a.json', { title: 'A', order: 10 }),
        ],
      })
    )
    expect(resolveSelection(inv, null, null)).toBe('spec/a.json')
  })

  it('never falls back to an archived document or a missing entry', () => {
    const inv = buildInventory(
      response({
        specs: [filed(`${ARCHIVE_PREFIX}2026-07-29-old/spec.json`, { title: 'Old' })],
        missing: [
          {
            path: 'spec/spec.json',
            title: 'Spec',
            kind: 'baseline',
            status: 'living',
            parent: null,
            order: 10,
          },
        ],
        home: 'spec/spec.json',
      })
    )
    expect(resolveSelection(inv, null, 'spec/spec.json')).toBeNull()
  })
})

describe('spec navigation — search ranking (FR-3)', () => {
  const archived = `${ARCHIVE_PREFIX}2026-07-29-add-agent-stream-kinds/spec.json`
  const inv = buildInventory(
    response({
      specs: [
        filed('spec/changes/add-spec-navigation/spec.json', { title: 'Add Spec Navigation' }),
        filed('spec/system-map.json', { title: 'System Map', kind: 'system-map' }),
        filed(archived, { title: 'Add Agent Stream Kinds' }),
      ],
      missing: [
        {
          path: 'spec/changes/gone/spec.json',
          title: 'Add Gone Change',
          kind: 'change-spec',
          status: 'approved',
          parent: null,
          order: 10,
        },
      ],
    })
  )

  it('ranks current readable results before archived results', () => {
    const results = searchDocuments(inv, 'add')
    expect(results.current.map((n) => n.path)).toEqual([
      'spec/changes/add-spec-navigation/spec.json',
    ])
    expect(results.archived.map((n) => n.path)).toEqual([archived])
  })

  it('scores a title match above a path-only match', () => {
    const results = searchDocuments(inv, 'system')
    expect(results.current[0].path).toBe('spec/system-map.json')
  })

  it('matches an archived change by its change name as topic vocabulary', () => {
    const results = searchDocuments(inv, 'stream-kinds')
    expect(results.archived.map((n) => n.path)).toEqual([archived])
  })

  it('normalizes case and surrounding whitespace', () => {
    expect(searchDocuments(inv, '  SYSTEM  ').current[0].path).toBe('spec/system-map.json')
  })

  it('returns missing matches separately so they can be rendered disabled', () => {
    const results = searchDocuments(inv, 'gone')
    expect(results.current).toHaveLength(0)
    expect(results.archived).toHaveLength(0)
    expect(results.missing.map((n) => n.path)).toEqual(['spec/changes/gone/spec.json'])
  })

  it('returns every readable document for an empty query', () => {
    const results = searchDocuments(inv, '   ')
    expect(results.current).toHaveLength(2)
    expect(results.archived).toHaveLength(1)
  })
})
