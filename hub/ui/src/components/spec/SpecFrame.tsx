import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from 'react'
import {
  postScrollTo,
  requestToc,
  resolveSpecLink,
  validateFrameMessage,
  withSpecBridge,
  type LinkResolution,
  type TocAnchor,
} from './specBridge'

// The composer's surface, restated. The spec document is sandboxed onto an opaque origin, so
// it cannot read the Hub's custom properties — the value has to travel as a literal.
// `hubVisualLanguage.test.ts` asserts these agree with `--surface` in index.css, the same way
// mcp_server.py's restated constants are pinned to their source.
export const HUB_SURFACE = { light: '#ffffff', dark: '#151518' } as const

// Two things the embedding fixes, both of which a standalone document gets right on its own
// and only gets wrong *inside the Hub*:
//
//  1. `color-scheme`. The conventions declare `light dark`, which tells the browser the
//     document handles both — so the UA paints scrollbars, and any form control, from the
//     **OS** preference. Reading a light Hub on a dark OS therefore produced a dark scrollbar
//     down the side of a white page (operator: "the scroll wheel on the spec in light mode is
//     dark"). Inside the frame the mode is not a preference to be honoured, it is already
//     decided, so it is pinned to the one the Hub is in.
//
//  2. `--bg`. The document's own ground is #ffffff / #15171c; the composer it sits beside is
//     #ffffff / #151518. Identical in light and a few points off in dark, which is exactly the
//     kind of near-match that reads as a mistake. The document is a panel in the Hub, so it
//     takes the Hub's panel colour (operator: "make the background of the spec the same color
//     as the composer background").
//
// `!important` rather than source order: the conventions' own `:root[data-theme="light"]` rule
// outranks a bare `:root`, and where this <style> lands relative to it depends on the document.
function themeOverride(mode: 'light' | 'dark'): string {
  return (
    `<style data-hub-theme-override>:root{` +
    `color-scheme:${mode} !important;` +
    `--bg:${HUB_SURFACE[mode]} !important;` +
    `}</style>`
  )
}

// Stamps the Hub's active light/dark mode onto the spec document's <html> tag so
// spec.html's `:root[data-theme="..."]` CSS layer (see html-spec-conventions.md)
// matches the dashboard instead of only following the OS preference.
export function withHubTheme(html: string, mode: 'light' | 'dark'): string {
  const themed = /<html[^>]*\sdata-theme=/i.test(html)
    ? html.replace(/data-theme="[^"]*"/i, `data-theme="${mode}"`)
    : html.replace(/<html([^>]*)>/i, `<html$1 data-theme="${mode}">`)

  // Drop any override from a previous pass before adding this one, so re-theming the same
  // string does not accumulate stylesheets.
  const stripped = themed.replace(/<style data-hub-theme-override>[\s\S]*?<\/style>/gi, '')
  const override = themeOverride(mode)
  // Appended, never prepended: a <style> placed ahead of the doctype would put the whole
  // document into quirks mode. A trailing one still applies.
  return /<\/head>/i.test(stripped)
    ? stripped.replace(/<\/head>/i, `${override}</head>`)
    : `${stripped}${override}`
}

export interface SpecFrameHandle {
  scrollToSection: (id: string) => void
}

interface SpecFrameProps {
  path: string
  content: string
  mode: 'light' | 'dark'
  readablePaths: ReadonlySet<string>
  /** Scrolled to once the next document reports a usable outline. */
  pendingFragment: string | null
  onOutline: (anchors: TocAnchor[]) => void
  onActiveSection: (id: string) => void
  onNavigate: (path: string, fragment: string | null) => void
  onRejected: (reason: Extract<LinkResolution, { kind: 'rejected' }>['reason'], href: string) => void
}

export const SpecFrame = forwardRef<SpecFrameHandle, SpecFrameProps>(function SpecFrame(
  { path, content, mode, readablePaths, pendingFragment, onOutline, onActiveSection, onNavigate, onRejected },
  ref
) {
  const frameRef = useRef<HTMLIFrameElement>(null)
  // Read inside the message handler so a re-render never detaches the listener.
  const pendingRef = useRef(pendingFragment)
  pendingRef.current = pendingFragment

  useImperativeHandle(
    ref,
    () => ({
      scrollToSection: (id: string) => postScrollTo(frameRef.current?.contentWindow ?? null, id),
    }),
    []
  )

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      const frame = frameRef.current?.contentWindow ?? null
      const message = validateFrameMessage(event, frame)
      if (!message) return

      if (message.type === 'toc-ready') {
        onOutline(message.anchors)
        // A fragment carried across a document switch can only be honoured
        // once the new document is parsed and reports its outline.
        const fragment = pendingRef.current
        if (fragment) postScrollTo(frame, fragment)
        return
      }

      if (message.type === 'active-section') {
        onActiveSection(message.id)
        return
      }

      const resolved = resolveSpecLink(message.href, path, readablePaths)
      if (resolved.kind === 'document') onNavigate(resolved.path, resolved.fragment)
      else if (resolved.kind === 'rejected') onRejected(resolved.reason, message.href)
      // 'fragment' is handled inside the document; nothing to do here.
    },
    [path, readablePaths, onOutline, onActiveSection, onNavigate, onRejected]
  )

  useEffect(() => {
    window.addEventListener('message', handleMessage)
    // Defer until parent effects have cleared the previous document's outline.
    const handshake = window.setTimeout(
      () => requestToc(frameRef.current?.contentWindow ?? null),
      0
    )
    return () => {
      window.clearTimeout(handshake)
      window.removeEventListener('message', handleMessage)
    }
  }, [handleMessage])

  return (
    <iframe
      ref={frameRef}
      title={path}
      data-testid="spec-frame"
      // No allow-same-origin: the document stays on an opaque origin and
      // cannot reach the Hub. Message identity replaces origin checking.
      sandbox="allow-scripts"
      srcDoc={withSpecBridge(withHubTheme(content, mode))}
      onLoad={() =>
        window.setTimeout(() => requestToc(frameRef.current?.contentWindow ?? null), 0)
      }
      className="w-full h-full border-0"
      // Matches the ground the document paints inside itself, so nothing flashes a different
      // colour before srcdoc parses and overscroll has nothing else to reveal.
      style={{ background: 'var(--surface)' }}
    />
  )
})
