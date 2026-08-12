import { describe, it, expect } from 'vitest'
import type { SpecListResponse } from '@/api/spec'
import {
  buildInventory,
  resolveSelection,
  searchDocuments,
  ARCHIVE_PREFIX,
} from '@/components/spec/specNavigation'

const ROADMAP = 'spec/roadmaps/agentweave-reconstruction.html'
const OTHER_ROADMAP = 'spec/roadmaps/hub-hardening.html'

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
          filed('spec/changes/add-spec-navigation/spec.html', {
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
      'spec/changes/add-spec-navigation/spec.html',
    ])
    expect(inv.needsAttention).toHaveLength(0)
  })

  it('orders siblings by manifest order, then title, then path', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/c.html', { title: 'C', order: 30 }),
          filed('spec/a.html', { title: 'A', order: 10 }),
          filed('spec/b2.html', { title: 'Same', order: 20 }),
          filed('spec/b1.html', { title: 'Same', order: 20 }),
          filed('spec/b0.html', { title: 'Earlier', order: 20 }),
        ],
      })
    )

    // order first; within equal order, title; within equal title, path
    expect(inv.library.map((n) => n.node.path)).toEqual([
      'spec/a.html',
      'spec/b0.html',
      'spec/b1.html',
      'spec/b2.html',
      'spec/c.html',
    ])
  })

  it('keeps unindexed and unfiled documents visible under Needs attention', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/agentweave-spec.html', { title: 'Baseline', kind: 'baseline' }),
          { path: 'spec/scratch.html', state: 'unindexed' as const },
          { path: 'spec/orphan.html', state: 'unfiled' as const },
        ],
      })
    )

    expect(inv.library.map((n) => n.node.path)).toEqual(['spec/agentweave-spec.html'])
    expect(inv.needsAttention.map((n) => n.path).sort()).toEqual([
      'spec/orphan.html',
      'spec/scratch.html',
    ])
    // visible, not dropped
    expect(inv.nodes).toHaveLength(3)
  })

  it('treats a filed node whose parent is absent as parent-orphaned, not a root', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/changes/x/spec.html', { title: 'X', parent: 'spec/roadmaps/gone.html' }),
        ],
      })
    )

    expect(inv.library).toHaveLength(0)
    expect(inv.needsAttention.map((n) => n.path)).toEqual(['spec/changes/x/spec.html'])
  })

  it('lists missing manifest entries under Needs attention and marks them unreadable', () => {
    const inv = buildInventory(
      response({
        specs: [filed(ROADMAP, { title: 'Roadmap', kind: 'roadmap' })],
        missing: [
          {
            path: 'spec/changes/deleted/spec.html',
            title: 'Deleted',
            kind: 'change-spec',
            status: 'approved',
            parent: ROADMAP,
            order: 10,
          },
        ],
      })
    )

    const node = inv.needsAttention.find((n) => n.path === 'spec/changes/deleted/spec.html')
    expect(node).toBeDefined()
    expect(node?.missing).toBe(true)
    // a missing entry must never be nested into the readable library
    expect(inv.library[0].children).toHaveLength(0)
  })
})

describe('spec navigation — history separation (FR-2)', () => {
  const archivedA = `${ARCHIVE_PREFIX}2026-07-29-add-agent-stream-kinds/spec.html`
  const archivedB = `${ARCHIVE_PREFIX}2026-07-01-add-spec-manifest/spec.html`
  const archivedC = `${ARCHIVE_PREFIX}2026-06-15-hub-auth/spec.html`
  const archivedOrphan = `${ARCHIVE_PREFIX}2026-05-02-standalone/spec.html`

  const inv = buildInventory(
    response({
      specs: [
        filed(ROADMAP, { title: 'Reconstruction', kind: 'roadmap', parent: null, order: 30 }),
        filed(OTHER_ROADMAP, { title: 'Hub Hardening', kind: 'roadmap', parent: null, order: 40 }),
        filed('spec/changes/active/spec.html', { title: 'Active', parent: ROADMAP }),
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

    expect(paths).toContain('spec/changes/active/spec.html')
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
    const undated = `${ARCHIVE_PREFIX}no-date-change/spec.html`
    const dated = `${ARCHIVE_PREFIX}2026-01-01-dated/spec.html`
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
})

describe('spec navigation — selection fallback (FR-4)', () => {
  const base = response({
    specs: [
      filed('spec/spec.html', { title: 'Spec', kind: 'baseline' }),
      filed(ROADMAP, { title: 'Roadmap', kind: 'roadmap' }),
      filed(`${ARCHIVE_PREFIX}2026-07-29-old/spec.html`, { title: 'Old' }),
    ],
    home: ROADMAP,
  })

  it('keeps the current selection while its path stays readable', () => {
    const inv = buildInventory(base)
    expect(resolveSelection(inv, 'spec/spec.html', ROADMAP)).toBe('spec/spec.html')
  })

  it('keeps an archived selection the user chose explicitly', () => {
    const inv = buildInventory(base)
    const archived = `${ARCHIVE_PREFIX}2026-07-29-old/spec.html`
    expect(resolveSelection(inv, archived, ROADMAP)).toBe(archived)
  })

  it('falls back to manifest home when the selection disappears', () => {
    const inv = buildInventory(base)
    expect(resolveSelection(inv, 'spec/gone.html', ROADMAP)).toBe(ROADMAP)
  })

  it('falls back to spec/spec.html when home is unreadable', () => {
    const inv = buildInventory(base)
    expect(resolveSelection(inv, null, 'spec/missing-home.html')).toBe('spec/spec.html')
  })

  it('falls back to the first readable current document when home and spec.html are gone', () => {
    const inv = buildInventory(
      response({
        specs: [
          filed('spec/b.html', { title: 'B', order: 20 }),
          filed('spec/a.html', { title: 'A', order: 10 }),
        ],
      })
    )
    expect(resolveSelection(inv, null, null)).toBe('spec/a.html')
  })

  it('never falls back to an archived document or a missing entry', () => {
    const inv = buildInventory(
      response({
        specs: [filed(`${ARCHIVE_PREFIX}2026-07-29-old/spec.html`, { title: 'Old' })],
        missing: [
          {
            path: 'spec/spec.html',
            title: 'Spec',
            kind: 'baseline',
            status: 'living',
            parent: null,
            order: 10,
          },
        ],
        home: 'spec/spec.html',
      })
    )
    expect(resolveSelection(inv, null, 'spec/spec.html')).toBeNull()
  })
})

describe('spec navigation — search ranking (FR-3)', () => {
  const archived = `${ARCHIVE_PREFIX}2026-07-29-add-agent-stream-kinds/spec.html`
  const inv = buildInventory(
    response({
      specs: [
        filed('spec/changes/add-spec-navigation/spec.html', { title: 'Add Spec Navigation' }),
        filed('spec/system-map.html', { title: 'System Map', kind: 'system-map' }),
        filed(archived, { title: 'Add Agent Stream Kinds' }),
      ],
      missing: [
        {
          path: 'spec/changes/gone/spec.html',
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
      'spec/changes/add-spec-navigation/spec.html',
    ])
    expect(results.archived.map((n) => n.path)).toEqual([archived])
  })

  it('scores a title match above a path-only match', () => {
    const results = searchDocuments(inv, 'system')
    expect(results.current[0].path).toBe('spec/system-map.html')
  })

  it('matches an archived change by its change name as topic vocabulary', () => {
    const results = searchDocuments(inv, 'stream-kinds')
    expect(results.archived.map((n) => n.path)).toEqual([archived])
  })

  it('normalizes case and surrounding whitespace', () => {
    expect(searchDocuments(inv, '  SYSTEM  ').current[0].path).toBe('spec/system-map.html')
  })

  it('returns missing matches separately so they can be rendered disabled', () => {
    const results = searchDocuments(inv, 'gone')
    expect(results.current).toHaveLength(0)
    expect(results.archived).toHaveLength(0)
    expect(results.missing.map((n) => n.path)).toEqual(['spec/changes/gone/spec.html'])
  })

  it('returns every readable document for an empty query', () => {
    const results = searchDocuments(inv, '   ')
    expect(results.current).toHaveLength(2)
    expect(results.archived).toHaveLength(1)
  })
})
