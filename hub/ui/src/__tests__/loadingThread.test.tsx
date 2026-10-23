// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { readdirSync, readFileSync, statSync } from 'node:fs'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LoadingThread } from '../components/common/LoadingThread'

// the-thread-is-how-agentweave-shows-it-is-loading: every loading placeholder is the brand's
// thread, so no component may still render the grey shimmer or a spinning icon.
const COMPONENTS = join('src', 'components')
const APP = join('src', 'App.tsx')

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name: string) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.tsx?$/.test(name) ? [path] : []
  })
}

describe('LoadingThread replaces every loading placeholder', () => {
  it('leaves no shimmer skeleton and no spinning icon in any component', () => {
    const offenders = [...sources(COMPONENTS), APP].flatMap((file) => {
      const text = readFileSync(file, 'utf8')
      const hits: string[] = []
      if (/className=\{?["'`][^"'`]*\bskeleton\b/.test(text)) hits.push('skeleton')
      if (/\banimate-spin\b/.test(text)) hits.push('animate-spin')
      return hits.length ? [`${relative(COMPONENTS, file)}: ${hits.join(', ')}`] : []
    })
    expect(offenders).toEqual([])
  })

  it('is a named status holding the thread, held back for fast loads', () => {
    render(<LoadingThread label="Loading the vault" />)
    const status = screen.getByRole('status', { name: 'Loading the vault' })
    expect(status.className).toContain('aw-delayed')
    expect(status.querySelector('svg[data-loading-thread]')).not.toBeNull()
  })

  it('draws the master thread at panel size and the small one inline and in controls', () => {
    const { container, rerender } = render(<LoadingThread label="Loading tasks" />)
    const panel = container.querySelector('svg[data-loading-thread]')!
    expect(panel.getAttribute('width')).toBe('64')
    expect(panel.getAttribute('data-drawing')).toBe('master')

    rerender(<LoadingThread label="Loading runs" size="inline" />)
    const inline = container.querySelector('svg[data-loading-thread]')!
    expect(inline.getAttribute('width')).toBe('24')
    expect(inline.getAttribute('data-drawing')).toBe('small')
    // inline shows its label as text beside the thread
    expect(screen.getByText('Loading runs')).toBeTruthy()

    rerender(<LoadingThread label="Saving" size="control" />)
    const control = container.querySelector('svg[data-loading-thread]')!
    expect(control.getAttribute('width')).toBe('16')
    expect(control.getAttribute('data-drawing')).toBe('small')
  })

  it('weaves: both strokes and the crossing cut run the weave keyframes', () => {
    const css = readFileSync(join('src', 'index.css'), 'utf8')
    expect(css).toMatch(/@keyframes aw-weave-a\b/)
    expect(css).toMatch(/@keyframes aw-weave-b\b/)
    // still and fully drawn under reduced motion
    expect(css).toMatch(/prefers-reduced-motion: reduce\)[^}]*\{[^}]*\.aw-loading-thread/)
  })
})
