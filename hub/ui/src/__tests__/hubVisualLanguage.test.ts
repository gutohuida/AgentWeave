/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { readFileSync, readdirSync, statSync } from 'node:fs'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { join } from 'node:path'

import appSource from '@/App.tsx?raw'
import projectManagerSource from '@/components/projects/ProjectManagerModal.tsx?raw'
import sidebarSource from '@/components/layout/Sidebar.tsx?raw'
import projectHeaderSource from '@/components/layout/ProjectHeader.tsx?raw'
import projectTabsSource from '@/components/layout/ProjectTabs.tsx?raw'
import conversationControlsSource from '@/components/agents/ConversationControls.tsx?raw'
import composerSource from '@/components/agents/Composer.tsx?raw'

const cssSource = readFileSync('src/index.css', 'utf8')

describe('Hub UI mock alignment contracts', () => {
  it('uses the neutral graphite palette and related shell planes in both modes', () => {
    for (const declaration of [
      '--bg:          #0a0a0b',
      '--rail:        #101012',
      '--top:         #0d0d0f',
      '--surface:     #151518',
      '--surface-2:   #1d1d21',
      '--primary:     #fafafa',
      '--bg:          #fafafa',
      '--rail:        #f4f4f5',
      '--top:         #ffffff',
      '--surface:     #ffffff',
      '--surface-2:   #f4f4f5',
      '--primary:     #18181b',
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

  it('adopts the Button primitive in the shell and conversation controls rather than hand-rolled buttons', () => {
    // A `<button` opening tag carrying its own `style={…}` attribute is exactly the pattern the
    // Button primitive replaces — every control in these files should either render <Button> or,
    // where a shared row treatment applies, a plain <button className="row-item" ...> with no
    // inline style.
    const handRolledButtonWithStyle = /<button(?:(?!>)[\s\S])*?style=\{/
    for (const [name, source] of [
      ['App.tsx', appSource],
      ['Sidebar.tsx', sidebarSource],
      ['ProjectHeader.tsx', projectHeaderSource],
      ['ProjectTabs.tsx', projectTabsSource],
      ['ConversationControls.tsx', conversationControlsSource],
      ['Composer.tsx', composerSource],
    ] as const) {
      expect(source, `${name} should not render a <button style={…}>`).not.toMatch(handRolledButtonWithStyle)
    }
    expect(sidebarSource).toContain("from '@/components/ui/button'")
    expect(projectHeaderSource).toContain("from '@/components/ui/button'")
    expect(projectTabsSource).toContain("from '@/components/ui/button'")
    expect(conversationControlsSource).toContain("from '@/components/ui/button'")
    expect(composerSource).toContain("from '@/components/ui/button'")
  })

  it('declares no raw hex colour outside the mode-preview swatch exemption (2026-08-04-hub-charcoal-visual-refresh)', () => {
    // A raw hex or rgba() literal survives a ramp swap unchanged, silently keeping the old
    // palette embedded in whatever it colours (this is how Badge.tsx's status palette was
    // found). SetupModal's light/dark mode-preview swatches are the one legitimate exception:
    // they show what each mode looks like regardless of which mode is currently active, so
    // they cannot be expressed as a token that itself changes per mode.
    const HEX_EXEMPT = new Set(['components/layout/SetupModal.tsx'])
    const HEX_COLOR_RE = /#[0-9a-fA-F]{3,8}\b/

    function listTsxFiles(dir: string): string[] {
      const out: string[] = []
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry)
        if (statSync(full).isDirectory()) out.push(...listTsxFiles(full))
        else if (entry.endsWith('.tsx')) out.push(full)
      }
      return out
    }

    for (const file of listTsxFiles('src/components')) {
      const relative = file.replace(/\\/g, '/').replace(/^src\//, '')
      if (HEX_EXEMPT.has(relative)) continue
      const source = readFileSync(file, 'utf8')
      const match = source.match(HEX_COLOR_RE)
      expect(match, `${relative} should not declare a raw hex colour (found ${match?.[0]})`).toBeNull()
    }
  })

  it('the project header sheds its box and presents a segmented, middle-elided path (2026-08-04-hub-charcoal-visual-refresh)', () => {
    expect(projectHeaderSource).not.toContain('borderBottom')
    expect(projectHeaderSource).not.toContain('border-region')
    expect(projectHeaderSource).toContain('elidePathSegments')
    expect(projectHeaderSource).toMatch(/title=\{pathDisplay/)
  })

  it('writes no data-theme attribute to the application document (2026-08-04-hub-charcoal-visual-refresh)', () => {
    // SpecFrame.tsx writes data-theme into an *embedded spec document*, which has its own
    // :root[data-theme] CSS layer — that write is untouched and correctly out of scope here.
    expect(appSource).not.toMatch(/dataset\.theme/)
    expect(appSource).not.toMatch(/data-theme=/)
  })
})
