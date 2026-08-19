import { describe, expect, it } from 'vitest'
import { buildFilePathTree } from '@/components/spec/specNavigation'

// Task 5.1, 2026-08-18-one-shell-three-panels: the files tab's tree, adapted from
// buildPathTree for GET /workspace/paths's raw listing.

const PATHS = [
  'README.md',
  'src/components/agents/Composer.tsx',
  'src/components/agents/ConversationView.tsx',
  'src/lib/composerTrigger.ts',
]

describe('buildFilePathTree — the workspace as its folder hierarchy', () => {
  it('names a shared directory once, above its children', () => {
    const rows = buildFilePathTree(PATHS)
    const agentsDirs = rows.filter((r) => r.kind === 'directory' && r.path === 'src/components/agents')
    expect(agentsDirs).toHaveLength(1)
  })

  it('keeps every segment, unlike buildPathTree there is no shared prefix to drop', () => {
    const rows = buildFilePathTree(PATHS)
    expect(rows.some((r) => r.kind === 'directory' && r.label === 'src')).toBe(true)
    expect(rows.find((r) => r.path === 'src')?.depth).toBe(0)
    expect(rows.find((r) => r.path === 'src/components')?.depth).toBe(1)
    expect(rows.find((r) => r.path === 'src/components/agents')?.depth).toBe(2)
  })

  it('nests a file under every segment of its own path', () => {
    const rows = buildFilePathTree(PATHS)
    const composer = rows.find((r) => r.kind === 'file' && r.path === 'src/components/agents/Composer.tsx')
    expect(composer?.depth).toBe(3)
    expect(composer?.label).toBe('Composer.tsx')
  })

  it('a root-level file has depth 0 and no directory rows', () => {
    const rows = buildFilePathTree(['README.md'])
    expect(rows).toEqual([{ kind: 'file', path: 'README.md', label: 'README.md', depth: 0 }])
  })

  it('sorts by path so directory grouping is stable regardless of input order', () => {
    const shuffled = [...PATHS].reverse()
    expect(buildFilePathTree(shuffled)).toEqual(buildFilePathTree(PATHS))
  })

  it('an empty listing produces no rows', () => {
    expect(buildFilePathTree([])).toEqual([])
  })
})
