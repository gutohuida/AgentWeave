import { describe, it, expect } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this test.
import { readFileSync } from 'node:fs'

// A check row's four actions (move up, move down, edit, remove) sat in a 26px grid column as
// blocks, so they stacked into a column 102px tall inside a 34px row: every row's name, command
// and time limit was centred on that column and drawn below its own box, onto the rows beneath
// and the Add check button (operator's screenshot, 2026-10-24). jsdom computes no layout, so this
// reads the rules that decide it; the browser measurement is in the commit.
const settingsCss = readFileSync('src/styles/settings.css', 'utf8')

function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = settingsCss.match(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`))
  return match ? match[1] : ''
}

describe('a check row holds its own contents', () => {
  it('sizes the actions column to the actions', () => {
    const columns = rule('.aw-check-row').match(/grid-template-columns:\s*([^;]+);/)?.[1] ?? ''
    expect(columns.trim().split(/\s+(?![^(]*\))/).pop()).toBe('auto')
  })

  it('lays the actions out in a line', () => {
    expect(rule('.aw-check-row .aw-reveal')).toMatch(/display:\s*inline-flex/)
  })
})
