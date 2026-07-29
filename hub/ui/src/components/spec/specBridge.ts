// Bridge between the Hub shell and the sandboxed spec iframe.
//
// The frame is rendered with sandbox="allow-scripts" and NO allow-same-origin,
// so its documents have an opaque origin. `event.origin` is therefore "null"
// for every message and carries no authority: identity comes from comparing
// the event's source against the live `contentWindow` we injected into, and
// authenticity comes from a versioned, bounded runtime shape. Adding
// allow-same-origin would let the document reach into the Hub and is
// prohibited by the approved spec.

export const SPEC_BRIDGE_CHANNEL = 'agentweave-spec'
export const SPEC_BRIDGE_VERSION = 1
export const SPEC_BRIDGE_MARKER = 'data-aw-spec-bridge'

// Bounds keep shell state finite no matter what a document posts.
export const MAX_TOC_ANCHORS = 256
export const MAX_LABEL_LENGTH = 200
export const MAX_ID_LENGTH = 128
export const MAX_HREF_LENGTH = 2048

export interface TocAnchor {
  id: string
  label: string
}

export type FrameMessage =
  | { type: 'toc-ready'; anchors: TocAnchor[] }
  | { type: 'navigate'; href: string }
  | { type: 'active-section'; id: string }

const FRAME_MESSAGE_TYPES = new Set(['toc-ready', 'navigate', 'active-section'])

function isBoundedString(value: unknown, max: number): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= max
}

/**
 * The single trust gate for anything the document sends. Returns the typed
 * message only when the source window, channel, version, type, field types,
 * and bounds all hold; otherwise null, and the caller changes no state.
 */
export function validateFrameMessage(
  event: MessageEvent,
  activeFrame: Window | null
): FrameMessage | null {
  if (!activeFrame || event.source !== activeFrame) return null

  const data = event.data
  if (typeof data !== 'object' || data === null || Array.isArray(data)) return null

  const raw = data as Record<string, unknown>
  if (raw.channel !== SPEC_BRIDGE_CHANNEL) return null
  if (raw.version !== SPEC_BRIDGE_VERSION) return null
  if (typeof raw.type !== 'string' || !FRAME_MESSAGE_TYPES.has(raw.type)) return null

  if (raw.type === 'toc-ready') {
    const anchors = raw.anchors
    if (!Array.isArray(anchors) || anchors.length > MAX_TOC_ANCHORS) return null
    const clean: TocAnchor[] = []
    for (const anchor of anchors) {
      if (typeof anchor !== 'object' || anchor === null) return null
      const { id, label } = anchor as Record<string, unknown>
      if (!isBoundedString(id, MAX_ID_LENGTH)) return null
      if (!isBoundedString(label, MAX_LABEL_LENGTH)) return null
      clean.push({ id, label })
    }
    return { type: 'toc-ready', anchors: clean }
  }

  if (raw.type === 'navigate') {
    if (!isBoundedString(raw.href, MAX_HREF_LENGTH)) return null
    return { type: 'navigate', href: raw.href }
  }

  if (!isBoundedString(raw.id, MAX_ID_LENGTH)) return null
  return { type: 'active-section', id: raw.id }
}

export type LinkResolution =
  | { kind: 'fragment'; fragment: string }
  | { kind: 'document'; path: string; fragment: string | null }
  | { kind: 'rejected'; reason: 'external' | 'unsafe' | 'not-html' | 'unknown' }

// Only used to normalize relative paths; never fetched, never navigated to.
const RESOLUTION_BASE = 'https://spec.invalid/'
const SPEC_ROOT = 'spec/'

/**
 * Resolve a link a spec document asked the shell to follow. Anything that is
 * not a readable spec HTML document inside the project's spec root is
 * rejected, and the caller keeps the current document on screen.
 */
export function resolveSpecLink(
  href: string,
  currentPath: string,
  readablePaths: ReadonlySet<string>
): LinkResolution {
  if (!href) return { kind: 'rejected', reason: 'unsafe' }
  if (href.startsWith('#')) {
    const fragment = href.slice(1)
    return fragment
      ? { kind: 'fragment', fragment }
      : { kind: 'rejected', reason: 'unsafe' }
  }

  let url: URL
  try {
    url = new URL(href, RESOLUTION_BASE + currentPath)
  } catch {
    return { kind: 'rejected', reason: 'unsafe' }
  }

  // Any scheme or host change means the target left the spec tree.
  if (url.origin !== new URL(RESOLUTION_BASE).origin) {
    return { kind: 'rejected', reason: 'external' }
  }

  const path = url.pathname.replace(/^\/+/, '')
  // Percent-encoding is never used by manifest paths; refusing it keeps the
  // prefix check below from being bypassed by an encoded traversal segment.
  if (path.includes('%') || path.includes('..')) {
    return { kind: 'rejected', reason: 'unsafe' }
  }
  if (!path.startsWith(SPEC_ROOT)) return { kind: 'rejected', reason: 'unsafe' }
  if (!/\.html?$/i.test(path)) return { kind: 'rejected', reason: 'not-html' }
  if (!readablePaths.has(path)) return { kind: 'rejected', reason: 'unknown' }

  const fragment = url.hash ? url.hash.slice(1) : null
  return { kind: 'document', path, fragment: fragment || null }
}

// Runs inside the sandboxed document. Kept dependency-free and defensive:
// a document that predates this feature, or has no usable TOC, must still
// render and scroll normally.
const BRIDGE_SCRIPT = `<script ${SPEC_BRIDGE_MARKER}>
(function () {
  var CHANNEL = ${JSON.stringify(SPEC_BRIDGE_CHANNEL)};
  var VERSION = ${SPEC_BRIDGE_VERSION};
  var MAX_ANCHORS = ${MAX_TOC_ANCHORS};
  var MAX_LABEL = ${MAX_LABEL_LENGTH};
  var MAX_ID = ${MAX_ID_LENGTH};
  var MAX_HREF = ${MAX_HREF_LENGTH};

  function post(msg) {
    msg.channel = CHANNEL;
    msg.version = VERSION;
    try { parent.postMessage(msg, '*'); } catch (e) {}
  }

  function collectToc() {
    var nav = document.querySelector('nav.toc');
    if (!nav) return null;
    var links = nav.querySelectorAll('a[href^="#"]');
    var anchors = [];
    for (var i = 0; i < links.length && anchors.length < MAX_ANCHORS; i++) {
      var href = links[i].getAttribute('href') || '';
      if (href.length > MAX_HREF) continue;
      var id = href.slice(1);
      if (!id || id.length > MAX_ID) continue;
      if (!document.getElementById(id)) continue;
      var label = (links[i].textContent || '').replace(/\\s+/g, ' ').trim();
      if (!label) continue;
      if (label.length > MAX_LABEL) label = label.slice(0, MAX_LABEL);
      anchors.push({ id: id, label: label });
    }
    return anchors.length > 0 ? anchors : null;
  }

  function trackActiveSection(anchors) {
    if (typeof IntersectionObserver === 'undefined') return;
    var visible = {};
    var observer = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        visible[entries[i].target.id] = entries[i].isIntersecting;
      }
      for (var j = 0; j < anchors.length; j++) {
        if (visible[anchors[j].id]) { post({ type: 'active-section', id: anchors[j].id }); return; }
      }
    }, { rootMargin: '0px 0px -70% 0px' });
    for (var k = 0; k < anchors.length; k++) {
      var el = document.getElementById(anchors[k].id);
      if (el) observer.observe(el);
    }
  }

  function scrollTo(id) {
    var target = id ? document.getElementById(id) : null;
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // Native navigation blanks an opaque-origin srcDoc frame, so every link is
  // handled here: same-document scrolls locally, everything else asks the shell.
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (!href || href.length > MAX_HREF) return;
    e.preventDefault();
    if (href.charAt(0) === '#') { scrollTo(href.slice(1)); return; }
    post({ type: 'navigate', href: href });
  });

  window.addEventListener('message', function (e) {
    var d = e.data;
    if (!d || typeof d !== 'object') return;
    if (d.channel !== CHANNEL || d.version !== VERSION) return;
    if (d.type === 'scroll-to' && typeof d.id === 'string' && d.id.length <= MAX_ID) scrollTo(d.id);
  });

  function init() {
    var anchors = collectToc();
    if (!anchors) return;
    // Hiding the in-document TOC is safe only now that the shell has a
    // working replacement for it.
    var nav = document.querySelector('nav.toc');
    if (nav) nav.style.display = 'none';
    post({ type: 'toc-ready', anchors: anchors });
    trackActiveSection(anchors);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>`

export function withSpecBridge(html: string): string {
  if (html.includes(SPEC_BRIDGE_MARKER)) return html
  return /<\/body>/i.test(html)
    ? html.replace(/<\/body>/i, `${BRIDGE_SCRIPT}</body>`)
    : html + BRIDGE_SCRIPT
}

/** Ask the active frame to scroll to a section. */
export function postScrollTo(frame: Window | null, id: string): void {
  if (!frame || !id || id.length > MAX_ID_LENGTH) return
  frame.postMessage(
    { channel: SPEC_BRIDGE_CHANNEL, version: SPEC_BRIDGE_VERSION, type: 'scroll-to', id },
    '*'
  )
}
