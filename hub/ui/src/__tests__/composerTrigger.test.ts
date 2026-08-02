import { describe, expect, it } from 'vitest'
import {
  acceptTriggerResult,
  detectComposerTrigger,
  quoteMentionValue,
  replaceTextRange,
} from '@/lib/composerTrigger'

describe('detectComposerTrigger', () => {
  it('does not treat a slash mid-sentence as a trigger', () => {
    const text = 'see https://example.com/foo'
    expect(detectComposerTrigger(text, text.length)).toBeNull()
  })

  it('detects a slash command at line start', () => {
    const text = '/mod'
    expect(detectComposerTrigger(text, text.length)).toEqual({
      kind: 'slash-command',
      query: 'mod',
      rangeStart: 0,
      rangeEnd: 4,
    })
  })

  it('detects a path mention mid-line', () => {
    const text = 'see @src/comp'
    expect(detectComposerTrigger(text, text.length)).toEqual({
      kind: 'path',
      query: 'src/comp',
      rangeStart: 4,
      rangeEnd: 13,
    })
  })

  it('detects a skill mention mid-line', () => {
    const text = 'run $aw-stat'
    expect(detectComposerTrigger(text, text.length)).toEqual({
      kind: 'skill',
      query: 'aw-stat',
      rangeStart: 4,
      rangeEnd: 12,
    })
  })

  it('returns null once the cursor has moved past a completed mention', () => {
    const text = '@src/composer.tsx looks good'
    expect(detectComposerTrigger(text, text.length)).toBeNull()
  })

  it('a slash command only matches at the very start of its line, not after other lines', () => {
    const text = 'first line\n/mod'
    expect(detectComposerTrigger(text, text.length)).toEqual({
      kind: 'slash-command',
      query: 'mod',
      rangeStart: 11,
      rangeEnd: 15,
    })
  })

  it('returns null for an empty line prefix', () => {
    expect(detectComposerTrigger('', 0)).toBeNull()
  })
})

describe('replaceTextRange', () => {
  it('repositions the cursor immediately after the inserted value, not at text end', () => {
    const text = '@src/comp then check the tests'
    const result = replaceTextRange(text, 0, 9, '@src/components/agents/Composer.tsx')
    expect(result.text).toBe('@src/components/agents/Composer.tsx then check the tests')
    expect(result.cursor).toBe('@src/components/agents/Composer.tsx'.length)
  })
})

describe('quoteMentionValue', () => {
  it('quote-escapes a value containing whitespace', () => {
    expect(quoteMentionValue('docs/release notes.md')).toBe('"docs/release notes.md"')
  })

  it('leaves a value with no whitespace unchanged', () => {
    expect(quoteMentionValue('src/index.ts')).toBe('src/index.ts')
  })

  it('escapes embedded double quotes', () => {
    expect(quoteMentionValue('a "weird" name.md')).toBe('"a \\"weird\\" name.md"')
  })
})

describe('acceptTriggerResult', () => {
  it('inserts a quote-escaped path mention at the trigger range', () => {
    const text = 'see @doc then continue'
    const trigger = detectComposerTrigger(text, 8)! // cursor right after "@doc"
    const result = acceptTriggerResult(text, trigger, 'docs/release notes.md')
    expect(result.text).toBe('see @"docs/release notes.md" then continue')
    expect(result.cursor).toBe('see @"docs/release notes.md"'.length)
  })

  it('inserts an unquoted skill mention', () => {
    const text = '$stat'
    const trigger = detectComposerTrigger(text, text.length)!
    const result = acceptTriggerResult(text, trigger, 'aw-status')
    expect(result.text).toBe('$aw-status')
    expect(result.cursor).toBe('$aw-status'.length)
  })

  it('inserts a slash command', () => {
    const text = '/mod'
    const trigger = detectComposerTrigger(text, text.length)!
    const result = acceptTriggerResult(text, trigger, 'model')
    expect(result.text).toBe('/model')
    expect(result.cursor).toBe('/model'.length)
  })
})
