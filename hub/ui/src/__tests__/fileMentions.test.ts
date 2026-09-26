import { describe, expect, it } from 'vitest'
import { isSafeMentionValue, neutraliseFileMentions } from '@/lib/fileMentions'
import { startWorkMessage } from '@/api/tasks'

// F409 D8/D10: the Claude CLI expands an unescaped `@path` in a prompt into a file attachment.
describe('neutraliseFileMentions', () => {
  it('puts a backslash before every at-sign and leaves other text alone', () => {
    expect(neutraliseFileMentions('Fix @/etc/passwd for ops@x.io')).toBe(
      'Fix \\@/etc/passwd for ops\\@x.io',
    )
    expect(neutraliseFileMentions('no at sign')).toBe('no at sign')
  })
})

describe('isSafeMentionValue', () => {
  it.each(['src/app.py', 'packages/@scope/x.ts', 'node_modules/@types/y.d.ts', '@root/z.md'])(
    'is true for %s',
    (value) => expect(isSafeMentionValue(value)).toBe(true),
  )
  it.each(['x @/home/u/.ssh/id_rsa', 'notes@home.md', 'x\uFEFF@y'])('is false for %j', (value) =>
    expect(isSafeMentionValue(value)).toBe(false),
  )
})

describe('startWorkMessage (useStartWorkOnTask)', () => {
  it('neutralises the task title', () => {
    expect(startWorkMessage('t1', 'Fix @/etc/passwd for ops@x.io')).toBe(
      'Work on task t1: Fix \\@/etc/passwd for ops\\@x.io',
    )
  })
  it('is byte-identical to today for a title with no at-sign', () => {
    expect(startWorkMessage('t1', 'Fix the build')).toBe('Work on task t1: Fix the build')
  })
})
