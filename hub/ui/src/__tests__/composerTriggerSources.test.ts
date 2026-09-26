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

// F409 D10: a value with an at-sign that is not at the start or after a `/` would type a live mention.
describe('resolveTriggerResults — unsafe mention values (F409 D10)', () => {
  const ALL = [
    'src/app.py',
    'packages/@scope/x.ts',
    'node_modules/@types/y.d.ts',
    '@root/z.md',
    'x @/home/u/.ssh/id_rsa',
    'notes@home.md',
    'x﻿@y',
  ]

  it('drops unsafe paths from a path trigger', () => {
    const trigger = detectComposerTrigger('@', 1)!
    expect(resolveTriggerResults(trigger, ALL).map((item) => item.value)).toEqual(ALL.slice(0, 4))
  })

  it('drops unsafe skill names from a skill trigger', () => {
    const trigger = detectComposerTrigger('$', 1)!
    const results = resolveTriggerResults(trigger, [
      '.claude/skills/ok/SKILL.md',
      '.claude/skills/x @/y/SKILL.md',
    ])
    expect(results.map((item) => item.value)).toEqual(['ok'])
  })

  it('filters before the 50-result cap, so refused values take no slots', () => {
    const many = [
      ...Array.from({ length: 60 }, (_, i) => `a@b${i}.md`),
      ...Array.from({ length: 3 }, (_, i) => `ok${i}.md`),
    ]
    const trigger = detectComposerTrigger('@', 1)!
    expect(resolveTriggerResults(trigger, many).map((item) => item.value)).toEqual([
      'ok0.md',
      'ok1.md',
      'ok2.md',
    ])
  })
})
