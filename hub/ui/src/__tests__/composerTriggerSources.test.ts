import { describe, expect, it } from 'vitest'
import { resolveTriggerResults } from '@/lib/composerTriggerSources'
import { detectComposerTrigger } from '@/lib/composerTrigger'

const WORKSPACE_PATHS = [
  '.claude/skills/aw-status/SKILL.md',
  '.claude/skills/aw-delegate.md',
  'src/index.ts',
  'src/components/agents/Composer.tsx',
]

describe('resolveTriggerResults', () => {
  it('sources @path results from the workspace path listing, unscoped', () => {
    const trigger = detectComposerTrigger('@src', 4)!
    const results = resolveTriggerResults(trigger, WORKSPACE_PATHS)
    expect(results.map((item) => item.value)).toEqual([
      'src/index.ts',
      'src/components/agents/Composer.tsx',
    ])
  })

  it('sources $skill results scoped to .claude/skills/, prefix and .md suffix stripped', () => {
    const trigger = detectComposerTrigger('$aw', 3)!
    const results = resolveTriggerResults(trigger, WORKSPACE_PATHS)
    expect(results.map((item) => item.value)).toEqual(['aw-status', 'aw-delegate'])
    expect(results.some((item) => item.value.includes('src/'))).toBe(false)
  })

  it('returns no skill results, not an error, when nothing lives under .claude/skills/', () => {
    const trigger = detectComposerTrigger('$any', 4)!
    const results = resolveTriggerResults(trigger, ['src/index.ts'])
    expect(results).toEqual([])
  })

  it('sources /command results from a static list, ignoring workspacePaths entirely', () => {
    const trigger = detectComposerTrigger('/mod', 4)!
    const results = resolveTriggerResults(trigger, [])
    expect(results.map((item) => item.value)).toEqual(['model'])
  })
})
