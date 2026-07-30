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

// Stamps the Hub's active light/dark mode onto the spec document's <html> tag so
// spec.html's `:root[data-theme="..."]` CSS layer (see html-spec-conventions.md)
// matches the dashboard instead of only following the OS preference.
export function withHubTheme(html: string, mode: 'light' | 'dark'): string {
  return /<html[^>]*\sdata-theme=/i.test(html)
    ? html.replace(/data-theme="[^"]*"/i, `data-theme="${mode}"`)
    : html.replace(/<html([^>]*)>/i, `<html$1 data-theme="${mode}">`)
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
      style={{ background: 'var(--bg)' }}
    />
  )
})
