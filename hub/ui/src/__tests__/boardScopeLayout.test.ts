import { describe, expect, it } from 'vitest'

// jsdom has no layout, so a long spec title squeezing the agent filter off the toolbar cannot be seen
// by a render test: the button's width cap and truncation are asserted in the stylesheet instead.

// vitest stubs css imports to '', and the UI has no node typings: read the file the way node does.
// @ts-expect-error no node typings in the UI project
const { readFileSync } = (await import('node:fs')) as { readFileSync: (p: string, enc: string) => string }
const css = readFileSync('src/styles/board.css', 'utf8')

describe('board scope button with a long spec title', () => {
  it('caps the button width and truncates the label', () => {
    expect(css).toMatch(/\.aw-board-scope-button\s*\{[^}]*max-width:\s*\d+px/)
    const label = css.match(/\.aw-board-scope-label\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(label).toContain('text-overflow: ellipsis')
    expect(label).toContain('overflow: hidden')
    expect(label).toContain('white-space: nowrap')
  })

  it('lets the scope control give way before the chips and search', () => {
    expect(css).toMatch(/\.aw-board-scope\s*\{[^}]*flex:\s*0\s+[1-9]\d*\s+240px/)
  })

  it('caps the picker list width', () => {
    expect(css).toMatch(/\.aw-board-scope-list\s*\{[^}]*max-width:/)
  })
})
