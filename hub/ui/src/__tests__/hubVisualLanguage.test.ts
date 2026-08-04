/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { readFileSync } from 'node:fs'

import appSource from '@/App.tsx?raw'
import projectManagerSource from '@/components/projects/ProjectManagerModal.tsx?raw'
import sidebarSource from '@/components/layout/Sidebar.tsx?raw'

const cssSource = readFileSync('src/index.css', 'utf8')

describe('Hub UI mock alignment contracts', () => {
  it('uses the approved mock palette and related shell planes in both modes', () => {
    for (const declaration of [
      '--bg:          #10131b',
      '--rail:        #171b2a',
      '--top:         #141827',
      '--surface:     #1b2030',
      '--surface-2:   #242a3c',
      '--primary:     #7c8cff',
      '--bg:          #f5f6fa',
      '--rail:        #e9ecf5',
      '--top:         #ffffff',
      '--surface:     #ffffff',
      '--surface-2:   #eef1f7',
      '--primary:     #5063d8',
    ]) {
      expect(cssSource).toContain(declaration)
    }
  })

  it('defines every shared surface used by project dialogs', () => {
    expect(projectManagerSource).not.toContain('var(--surface-1)')
    expect(projectManagerSource).toContain("background: 'var(--surface)'")
    expect(projectManagerSource).toContain("background: 'var(--scrim)'")
  })

  it('retains local fonts, compact radii, motion, and reduced-motion support', () => {
    expect(cssSource).toContain("@import '@fontsource-variable/dm-sans'")
    expect(cssSource).toContain('--radius:      10px')
    expect(cssSource).toContain('--dur-fast:    150ms')
    expect(cssSource).toContain('@media (prefers-reduced-motion: reduce)')
  })

  it('uses named SVG icons instead of literal or corrupted project glyphs', () => {
    expect(sidebarSource).toContain("import { Icon }")
    expect(sidebarSource).not.toMatch(/[ÃÂâ]/)
    expect(sidebarSource).toContain('Add project')
    expect(sidebarSource).toContain('name="chevron_right"')
  })

  it('replaces the permanent status strip with a project header and bounded content', () => {
    expect(appSource).not.toContain('<StatusBar')
    expect(appSource).toContain('<ProjectHeader')
    expect(appSource).toContain('workspace-content')
    expect(cssSource).toContain('@media (max-width: 760px)')
  })
})
