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
import agentTimelineSource from '@/components/agents/AgentTimeline.tsx?raw'
import { HUB_NEUTRALS, withHubTheme } from '@/components/spec/hubTheme'

const cssSource = readFileSync('src/index.css', 'utf8')

describe('Hub UI mock alignment contracts', () => {
  it('uses the neutral graphite palette and related shell planes in both modes', () => {
    for (const declaration of [
      '--bg:          #0a0a0b',
      '--rail:        #101012',
      '--surface:     #151518',
      '--surface-2:   #1d1d21',
      '--primary:     #fafafa',
      '--bg:          #fafafa',
      '--rail:        #f4f4f5',
      '--surface:     #ffffff',
      '--surface-2:   #f4f4f5',
      '--primary:     #18181b',
    ]) {
      expect(cssSource).toContain(declaration)
    }
    // `--top` was a plane defined for exactly one element, the tab strip. Removed rather than
    // left unreferenced, so the palette does not carry a colour nothing uses.
    expect(cssSource).not.toMatch(/--top:/)
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

  it('ships the considered elevation, field, chip, card, and skeleton foundations', () => {
    for (const primitive of [
      '.elevation-ground',
      '.elevation-resting',
      '.elevation-nested',
      '.elevation-overlay',
      '.control-field',
      '.aw-chip',
      '.interactive-card',
      '.skeleton',
    ]) {
      expect(cssSource).toContain(primitive)
    }
    expect(cssSource).toContain('animation: skeleton-shimmer 1.8s var(--ease) infinite')
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
    // SpecFrame.tsx is the second: the spec document is sandboxed onto an opaque origin, so a
    // `var(--surface)` reference cannot cross into it and the value must travel as a literal.
    // What this rule actually guards against — a hex quietly surviving a ramp swap — is covered
    // instead by 'restates --surface exactly as index.css declares it' below, which fails the
    // moment the palette moves and the copy does not.
    const HEX_EXEMPT = new Set(['components/layout/SetupModal.tsx', 'components/spec/SpecFrame.tsx'])
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

  it('the composer surface does not react to focus (2026-08-06-hub-composer-and-chrome-refinement §3)', () => {
    expect(cssSource).not.toMatch(/conversation-composer-surface:focus-within/)
    // The send button still goes through the Button primitive, whose base class carries an
    // unconditional focus-visible ring — removing the surface's own focus reaction does not
    // leave the composer's controls without one.
    expect(composerSource).toContain("from '@/components/ui/button'")
  })

  it('the tab strip carries neither a dividing line nor a plane change at its boundary (§6)', () => {
    // §6 removed the line and kept a plane change. The operator then read the remaining plane
    // as a band laid over the screen — "it pops up in a bad way… make it the same color" — so
    // the strip now paints nothing at all and sits on `--bg` with everything else.
    expect(projectTabsSource).not.toMatch(/borderBottom/)
    // Scoped to the style attribute so prose about the removal does not trip it.
    expect(projectTabsSource).not.toMatch(/style=\{\{[^}]*background/)
    expect(projectTabsSource).not.toMatch(/var\(--top\)/)
  })

  it('nothing paints a darker region around the composer (2026-08-06-hub-collaboration-and-conversation-fixes §4)', () => {
    // Operator: "There is a charcoal chat box and then a black box around it?" Two layers did
    // that — a 52px near-black drop shadow, and a `--bg` gradient across the whole strip. The
    // inset top highlight is what actually lifts the panel and is kept.
    const surfaceRule = cssSource.match(/\.conversation-composer-surface\s*\{[^}]*\}/)?.[0] ?? ''
    expect(surfaceRule).toContain('inset 0 1px')
    expect(surfaceRule).not.toMatch(/box-shadow:[^;]*\b0 20px 52px/)
    expect(surfaceRule).not.toMatch(/rgba\(2,\s*5,\s*18/)

    const fadeRule = cssSource.match(/\.conversation-composer-fade\s*\{[^}]*\}/)?.[0] ?? ''
    expect(fadeRule).not.toContain('linear-gradient')
  })

  it("the operator's own message bubble carries no accent hue (§4)", () => {
    // `--blue` is the single chromatic accent, reserved for focus/selection. A 14% wash of it
    // over --surface-2 is what read as "the old dark navy color palete".
    expect(agentTimelineSource).not.toContain('var(--blue)')
    expect(agentTimelineSource).toContain("background: 'var(--surface-2)'")
    expect(agentTimelineSource).toContain("border: '1px solid var(--border)'")
  })

  it('a turn never folds itself as a function of its position (§6)', () => {
    // `foldOverride[key] ?? !isLastTurn` collapsed whatever the operator was reading the moment
    // a new turn was appended.
    expect(agentTimelineSource).not.toMatch(/foldOverride\[key\]\s*\?\?\s*!isLastTurn/)
    expect(agentTimelineSource).toMatch(/foldOverride\[key\]\s*\?\?\s*false/)
  })
})

describe('the embedded spec document adopts the Hub it is embedded in', () => {
  it('restates the neutral ramp exactly as index.css declares it', () => {
    // The frame is sandboxed onto an opaque origin and cannot read a custom property across
    // that boundary, so the values are literals in SpecFrame.tsx. This is the assertion that
    // keeps the copy honest — change the palette and this fails rather than drifting.
    const escape = (v: string) => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    for (const [mode, block] of [
      ['dark', cssSource.slice(cssSource.indexOf('[data-mode="dark"]'), cssSource.indexOf('[data-mode="light"]'))],
      ['light', cssSource.slice(cssSource.indexOf('[data-mode="light"]'))],
    ] as const) {
      const n = HUB_NEUTRALS[mode]
      for (const [token, value] of [
        ['--bg', n.bg],
        ['--surface', n.surface],
        ['--surface-2', n.surface2],
        ['--border', n.border],
        ['--text', n.fg],
        ['--text-2', n.muted],
      ] as const) {
        expect(block, `${mode} ${token} should still be ${value}`)
          .toMatch(new RegExp(`${escape(token)}:\\s*${escape(value)}\\s*;`))
      }
    }
  })

  it('pins color-scheme to the Hub mode so the scrollbar stops following the OS', () => {
    const doc = '<html><head><style>:root{color-scheme:light dark}</style></head><body></body></html>'
    expect(withHubTheme(doc, 'light')).toContain('color-scheme:light !important')
    expect(withHubTheme(doc, 'dark')).toContain('color-scheme:dark !important')
  })

  it("grounds the document on the page, not on a lift plane, and keeps the ramp coherent", () => {
    // Every ancestor of the frame paints --bg, so the document is the region. Re-grounding
    // without also moving --surface would invert the lift: the conventions' own #f6f7f9 is
    // darker than the Hub's light --bg.
    for (const mode of ['light', 'dark'] as const) {
      const themed = withHubTheme('<html><head></head><body></body></html>', mode)
      expect(themed).toContain(`--bg:${HUB_NEUTRALS[mode].bg} !important`)
      expect(themed).toContain(`--surface:${HUB_NEUTRALS[mode].surface} !important`)
      expect(themed).toContain(`--surface-2:${HUB_NEUTRALS[mode].surface2} !important`)
    }
    // Lifted blocks must read as lifted in both modes: light lifts toward white, dark away
    // from black. Asserted as a relationship so a future palette edit cannot quietly flatten it.
    const lum = (hex: string) => parseInt(hex.slice(1, 3), 16)
    expect(lum(HUB_NEUTRALS.light.surface)).toBeGreaterThan(lum(HUB_NEUTRALS.light.bg))
    expect(lum(HUB_NEUTRALS.dark.surface)).toBeGreaterThan(lum(HUB_NEUTRALS.dark.bg))
  })

  it('recolours only the neutrals, leaving the meaning-carrying hues alone', () => {
    // accent / warn / done / danger say something inside the specification; they are not the
    // Hub's to restyle.
    const themed = withHubTheme('<html><head></head><body></body></html>', 'dark')
    const override = themed.match(/<style data-hub-theme-override>([\s\S]*?)<\/style>/)?.[1] ?? ''
    for (const token of ['--accent', '--warn', '--done', '--danger']) {
      expect(override, `${token} should not be overridden`).not.toContain(`${token}:`)
    }
  })

  it('lands the override inside <head>, never ahead of the doctype', () => {
    // A <style> prepended before <!DOCTYPE html> drops the document into quirks mode.
    const themed = withHubTheme('<!DOCTYPE html><html><head><title>S</title></head><body>x</body></html>', 'dark')
    expect(themed.indexOf('<!DOCTYPE html>')).toBe(0)
    expect(themed).toMatch(/<style data-hub-theme-override>[\s\S]*<\/style><\/head>/)

    const fragment = withHubTheme('<p>no head</p>', 'dark')
    expect(fragment.indexOf('<p>no head</p>')).toBe(0)
  })

  it('re-theming replaces the previous override instead of stacking another', () => {
    const once = withHubTheme('<html><head></head><body></body></html>', 'light')
    const twice = withHubTheme(once, 'dark')
    expect(twice.match(/data-hub-theme-override/g)).toHaveLength(1)
    expect(twice).toContain(`--bg:${HUB_NEUTRALS.dark.bg} !important`)
    expect(twice).not.toContain(HUB_NEUTRALS.light.bg)
  })
})
