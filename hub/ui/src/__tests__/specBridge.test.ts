import { describe, it, expect, vi } from 'vitest'
import {
  SPEC_BRIDGE_CHANNEL,
  SPEC_BRIDGE_VERSION,
  MAX_TOC_ANCHORS,
  MAX_LABEL_LENGTH,
  MAX_HREF_LENGTH,
  validateFrameMessage,
  resolveSpecLink,
  withSpecBridge,
  SPEC_BRIDGE_MARKER,
  requestToc,
} from '@/components/spec/specBridge'

const activeWindow = { name: 'active-frame' } as unknown as Window
const otherWindow = { name: 'other-frame' } as unknown as Window

function frameEvent(data: unknown, source: Window = activeWindow) {
  return { source, data } as unknown as MessageEvent
}

function tocMessage(anchors: { id: string; label: string }[]) {
  return {
    channel: SPEC_BRIDGE_CHANNEL,
    version: SPEC_BRIDGE_VERSION,
    type: 'toc-ready',
    anchors,
  }
}

describe('spec bridge — message validation (FR-7)', () => {
  it('accepts a well-formed message from the active frame', () => {
    const msg = validateFrameMessage(frameEvent(tocMessage([{ id: 'intro', label: 'Intro' }])), activeWindow)
    expect(msg).not.toBeNull()
    expect(msg?.type).toBe('toc-ready')
    expect(msg?.type === 'toc-ready' && msg.anchors).toEqual([{ id: 'intro', label: 'Intro' }])
  })

  it('rejects a message from any window that is not the active frame', () => {
    // srcDoc frames have an opaque origin, so identity is the only real check.
    expect(validateFrameMessage(frameEvent(tocMessage([]), otherWindow), activeWindow)).toBeNull()
  })

  it('rejects a message when there is no active frame', () => {
    expect(validateFrameMessage(frameEvent(tocMessage([])), null)).toBeNull()
  })

  it('rejects a foreign channel', () => {
    const data = { ...tocMessage([]), channel: 'some-other-app' }
    expect(validateFrameMessage(frameEvent(data), activeWindow)).toBeNull()
  })

  it('rejects an unsupported version', () => {
    const data = { ...tocMessage([]), version: SPEC_BRIDGE_VERSION + 1 }
    expect(validateFrameMessage(frameEvent(data), activeWindow)).toBeNull()
  })

  it('rejects an unknown message type', () => {
    const data = { ...tocMessage([]), type: 'exfiltrate' }
    expect(validateFrameMessage(frameEvent(data), activeWindow)).toBeNull()
  })

  it('rejects non-object payloads', () => {
    for (const payload of [null, undefined, 'toc-ready', 42, []]) {
      expect(validateFrameMessage(frameEvent(payload), activeWindow)).toBeNull()
    }
  })

  it('rejects a TOC payload above the anchor bound', () => {
    const anchors = Array.from({ length: MAX_TOC_ANCHORS + 1 }, (_, i) => ({
      id: `s${i}`,
      label: `Section ${i}`,
    }))
    expect(validateFrameMessage(frameEvent(tocMessage(anchors)), activeWindow)).toBeNull()
  })

  it('accepts a TOC payload exactly at the anchor bound', () => {
    const anchors = Array.from({ length: MAX_TOC_ANCHORS }, (_, i) => ({
      id: `s${i}`,
      label: `Section ${i}`,
    }))
    expect(validateFrameMessage(frameEvent(tocMessage(anchors)), activeWindow)).not.toBeNull()
  })

  it('rejects an over-long anchor label', () => {
    const anchors = [{ id: 'x', label: 'a'.repeat(MAX_LABEL_LENGTH + 1) }]
    expect(validateFrameMessage(frameEvent(tocMessage(anchors)), activeWindow)).toBeNull()
  })

  it('rejects anchors with non-string fields', () => {
    const anchors = [{ id: 'x', label: 12 }] as unknown as { id: string; label: string }[]
    expect(validateFrameMessage(frameEvent(tocMessage(anchors)), activeWindow)).toBeNull()
  })

  it('validates navigate messages and bounds the href', () => {
    const ok = validateFrameMessage(
      frameEvent({
        channel: SPEC_BRIDGE_CHANNEL,
        version: SPEC_BRIDGE_VERSION,
        type: 'navigate',
        href: '../system-map.html#SM-K-002',
      }),
      activeWindow
    )
    expect(ok?.type).toBe('navigate')

    const tooLong = validateFrameMessage(
      frameEvent({
        channel: SPEC_BRIDGE_CHANNEL,
        version: SPEC_BRIDGE_VERSION,
        type: 'navigate',
        href: 'a'.repeat(MAX_HREF_LENGTH + 1),
      }),
      activeWindow
    )
    expect(tooLong).toBeNull()
  })

  it('validates active-section messages', () => {
    const msg = validateFrameMessage(
      frameEvent({
        channel: SPEC_BRIDGE_CHANNEL,
        version: SPEC_BRIDGE_VERSION,
        type: 'active-section',
        id: 'requirements',
      }),
      activeWindow
    )
    expect(msg?.type === 'active-section' && msg.id).toBe('requirements')
  })
})

describe('spec bridge — link resolution (FR-6)', () => {
  const current = 'spec/changes/add-spec-navigation/spec.html'
  const readable = new Set([
    'spec/spec.html',
    'spec/system-map.html',
    'spec/changes/add-spec-navigation/spec.html',
    'spec/roadmaps/agentweave-reconstruction.html',
  ])

  it('treats a bare fragment as same-document navigation', () => {
    expect(resolveSpecLink('#requirements', current, readable)).toEqual({
      kind: 'fragment',
      fragment: 'requirements',
    })
  })

  it('resolves a relative sibling link', () => {
    expect(resolveSpecLink('../../system-map.html#SM-K-002', current, readable)).toEqual({
      kind: 'document',
      path: 'spec/system-map.html',
      fragment: 'SM-K-002',
    })
  })

  it('resolves a relative link with no fragment', () => {
    expect(resolveSpecLink('../../spec.html', current, readable)).toEqual({
      kind: 'document',
      path: 'spec/spec.html',
      fragment: null,
    })
  })

  it('resolves a project-root-absolute link', () => {
    expect(resolveSpecLink('/spec/system-map.html', current, readable)).toEqual({
      kind: 'document',
      path: 'spec/system-map.html',
      fragment: null,
    })
  })

  it('rejects an external target', () => {
    for (const href of ['https://example.com/x.html', '//example.com/x.html', 'mailto:a@b.c']) {
      expect(resolveSpecLink(href, current, readable)).toEqual({
        kind: 'rejected',
        reason: 'external',
      })
    }
  })

  it('rejects traversal outside the spec root', () => {
    expect(resolveSpecLink('../../../etc/passwd', current, readable)).toEqual({
      kind: 'rejected',
      reason: 'unsafe',
    })
  })

  it('rejects a non-HTML target', () => {
    expect(resolveSpecLink('../../notes.md', current, readable)).toEqual({
      kind: 'rejected',
      reason: 'not-html',
    })
  })

  it('rejects a target that is not in the readable inventory', () => {
    expect(resolveSpecLink('../../changes/ghost/spec.html', current, readable)).toEqual({
      kind: 'rejected',
      reason: 'unknown',
    })
  })

  it('rejects javascript: and data: schemes', () => {
    for (const href of ['javascript:alert(1)', 'data:text/html,<b>x</b>']) {
      const result = resolveSpecLink(href, current, readable)
      expect(result.kind).toBe('rejected')
    }
  })

  it('rejects an empty href instead of selecting the current document', () => {
    expect(resolveSpecLink('', current, readable).kind).toBe('rejected')
  })
})

describe('spec bridge — injection (FR-5, FR-7)', () => {
  const html = '<html><head></head><body><nav class="toc"></nav></body></html>'

  it('injects the bridge before </body> exactly once', () => {
    const once = withSpecBridge(html)
    expect(once).toContain(SPEC_BRIDGE_MARKER)
    expect(once.indexOf('</body>')).toBeGreaterThan(once.indexOf(SPEC_BRIDGE_MARKER))
    const twice = withSpecBridge(once)
    expect(twice.split(SPEC_BRIDGE_MARKER).length - 1).toBe(1)
  })

  it('appends the bridge when the document has no body tag', () => {
    expect(withSpecBridge('<p>fragment</p>')).toContain(SPEC_BRIDGE_MARKER)
  })

  it('carries the channel, version, and bounds into the injected script', () => {
    const injected = withSpecBridge(html)
    expect(injected).toContain(SPEC_BRIDGE_CHANNEL)
    expect(injected).toContain(String(MAX_TOC_ANCHORS))
    expect(injected).toContain("d.type === 'request-toc'")
  })

  it('can repeat the TOC handshake after the frame load event', () => {
    const postMessage = vi.fn()
    requestToc({ postMessage } as unknown as Window)
    expect(postMessage).toHaveBeenCalledWith(
      {
        channel: SPEC_BRIDGE_CHANNEL,
        version: SPEC_BRIDGE_VERSION,
        type: 'request-toc',
      },
      '*'
    )
  })

  it('executes the injected bridge and publishes a real document outline', () => {
    document.body.innerHTML =
      '<nav class="toc"><a href="#intro">Introduction</a></nav><section id="intro"></section>'
    const postMessage = vi.spyOn(window, 'postMessage')
    const injected = withSpecBridge('<html><body></body></html>')
    const script = injected.match(/<script data-aw-spec-bridge>([\s\S]*?)<\/script>/)?.[1]
    expect(script).toBeTruthy()
    Function(script as string)()
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        channel: SPEC_BRIDGE_CHANNEL,
        version: SPEC_BRIDGE_VERSION,
        type: 'toc-ready',
        anchors: [{ id: 'intro', label: 'Introduction' }],
      }),
      '*'
    )
    postMessage.mockRestore()
  })
})
