# Exploration - Spec navigation and workspace layout

Date: 2026-07-29
Candidate change: `add-spec-navigation`
Includes: the former Change 3 layout scope

## Question

Now that `add-spec-manifest` supplies a visible, ordered document forest, what should the Hub Spec
workspace implement so users can move between documents and sections without making the existing
chat-and-document layout unusable?

## Decision

Proceed with one change named `add-spec-navigation`. Keep document navigation, iframe navigation,
TOC hoisting, and responsive workspace layout in the same change because they share one state
boundary and one acceptance surface.

The change should:

- replace the flat path selector with a persistent manifest-backed document tree;
- keep archived changes out of the default tree and provide a separate History browser;
- provide a `Ctrl+K` / `Cmd+K` document search using the existing dialog dependency;
- hoist a valid `nav.toc` from the active spec into the shell;
- route same-document and cross-document spec links through a versioned iframe bridge;
- collapse the global Hub sidebar to an icon rail while the Spec page is active;
- preserve the document as the minimum-width priority, collapsing chat and navigation before
  squeezing the document below its usable width; and
- preserve the current manifest drift banner and spec-agent chat behavior.

No Hub database or REST schema change is required for the first version. `GET /project/specs`
already returns the required `path`, `title`, `kind`, `status`, `parent`, `order`, and `state`
fields plus missing entries and diagnostics.

## Evidence checked

### Current API boundary

`hub/ui/src/api/spec.ts` already exposes:

- the complete visible spec inventory;
- manifest-owned parent and sibling order;
- intrinsic title, kind, and status;
- filing states (`filed`, `unindexed`, `unfiled`, `stale`);
- missing manifest entries; and
- the manifest home document.

`hub/hub/api/v1/spec.py` enriches the legacy list response with those fields. The backend remains
the authority for reconciliation and drift; the UI should not parse HTML metadata to rebuild a
second manifest.

### Current UI boundary

`SpecPage.tsx` currently has:

- one flat `<select>` that displays raw paths;
- one sandboxed `srcDoc` iframe with `allow-scripts` and an opaque origin;
- a fixed 380 px chat pane;
- no shell-side document tree, path search, TOC, or cross-document routing; and
- an injected same-document anchor workaround that already establishes the safe place to add the
  bridge.

`Sidebar.tsx` is fixed at 220 px. The generated HTML convention also gives `nav.toc` a fixed
220 px width. Together with the 380 px chat, those fixed panes leave the document as the only pane
that can be crushed.

### Existing document contract

`html-spec-conventions.md` requires a `nav.toc` containing same-document anchors and requires each
spec to keep working standalone. The Hub may hide that TOC only after it has extracted a valid
replacement. A malformed or missing TOC must leave the in-document TOC visible.

`spec-manifest-conventions.md` defines the manifest as a document forest. It also says an absent or
invalid manifest must degrade to drift rather than invisibility. Navigation must therefore include
unfiled documents and represent missing entries; it cannot render only valid manifest nodes.

## Navigation model

### Document forest

Build a pure UI projection from the API response:

1. Create nodes for every returned spec and every missing manifest entry.
2. Attach a filed node to `parent` only when that parent is present.
3. Sort siblings by `order`, then title, then path.
4. Exclude paths beneath `spec/changes/archive/` from the default tree.
5. Place roots in kind groups only when hierarchy alone would be ambiguous.
6. Put unindexed, unfiled, stale, and parent-orphaned documents in a visible `Needs attention`
   section.
7. Show missing entries in their declared position when possible, disabled and visibly marked
   `Missing`.

The selected document remains stable across list refreshes while its path is still available.
Otherwise selection falls back to manifest `home`, then `spec/spec.html`, then the first readable
document, preserving the current behavior.

Tree labels use title as the primary text and path as secondary text or tooltip. Kind and status
receive compact semantic badges. Drift state must not be communicated by color alone.

### Historical changes

Historical changes must be easy to consult without making the working navigation noisy.

The default document tree shows core documents, roadmaps, active changes, and `Needs attention`.
A compact `History` entry with an archive count opens a separate browser in the navigation pane.
Entering History does not insert archived documents into the active tree.

History groups archived change specs by their manifest parent roadmap. Within a roadmap, changes
are ordered newest first using the archive date encoded in their path, with title and path as
deterministic fallbacks. Changes with no roadmap parent appear under `Other changes`.

The first version does not add topic tags to the manifest. A historical change's title and change
name are its searchable topic vocabulary. This keeps topic lookup useful without introducing a
second taxonomy that authoring and archive skills would have to maintain.

Opening an archived document:

- keeps the History browser active;
- displays an explicit `Archived` context marker;
- allows its section outline and cross-document links to work normally; and
- never makes it eligible as the default or home document.

### Document search

`Ctrl+K` on Windows/Linux and `Cmd+K` on macOS opens a document picker while the Hub is configured.
Search matches normalized title and path, with title matches ranked before path-only matches.

The picker includes readable filed and unfiled documents. Current documents are ranked and grouped
before archived results; archived results remain available without appearing in the normal tree.
Missing documents may appear as disabled results so search does not hide known drift. Keyboard
navigation, escape-to-close, focus return, and an explicit visible shortcut affordance are
required.

Use the existing `@radix-ui/react-dialog`; do not add a command-palette package.

### URL scope

The current Hub has state-based page switching and no router or deep-link contract. This change
should not introduce a routing library. Document selection is workspace state, not a new browser
URL API. A future change can add durable deep links after the Hub has a page-routing decision.

## Iframe bridge

### Message contract

Use a small versioned envelope:

```text
{
  channel: "agentweave-spec",
  version: 1,
  type: "toc-ready" | "section-active" | "navigate",
  payload: ...
}
```

Shell-to-frame messages use the same channel and version with `type: "scroll-to"`.

Because a sandboxed `srcDoc` frame without `allow-same-origin` reports an opaque origin, origin
matching is not useful. The shell must instead require:

- `event.source === iframeRef.current.contentWindow`;
- exact channel, version, type, and bounded payload shapes;
- anchor IDs and href lengths within explicit limits; and
- a resolved target path that exactly matches a readable entry returned by the Hub.

Never add `allow-same-origin`. Never evaluate document-provided code or HTML in the shell.

### TOC handshake and fallback

The injected bridge reads `nav.toc a[href^="#"]`, retaining bounded plain-text labels and valid
element IDs in document order. It sends `toc-ready` only when at least one valid target exists.

The bridge hides `nav.toc` inside the iframe only after successful extraction. If extraction
fails, the document keeps its native TOC and the shell shows a compact `In-document navigation`
state rather than an empty sidebar. This resolves the prior open question automatically without a
user preference.

The existing document `IntersectionObserver` is not a reliable shell API. The injected bridge owns
its own bounded observer and emits `section-active`. Clicking a shell TOC item sends `scroll-to`;
the frame resolves the ID and calls `scrollIntoView`.

### Link routing

The injected click handler distinguishes:

- `#section`: scroll in the current frame and update active section;
- relative or project-root spec `.html` links: send `navigate` with the raw href;
- external protocols, downloads, and non-HTML assets: do not route through spec navigation.

The shell resolves relative links against the current spec's POSIX directory, removes any fragment,
rejects traversal or unsafe paths, and selects the target only when it exactly matches a readable
Hub entry. After the target document loads, the shell sends its fragment through `scroll-to`.

Unknown, missing, or unsafe targets remain in the current document and surface a bounded,
non-blocking navigation error. They must not blank the iframe.

## Workspace layout

Use the Spec workspace's measured container width, not only `window.innerWidth`, because the Hub
may itself be embedded or resized.

### Wide mode

When all minimums fit:

- global Hub navigation becomes an approximately 52 px icon rail;
- document tree and hoisted TOC share one 240-280 px navigation pane;
- document content has a hard minimum of 520 px;
- chat defaults near its current width and is user-collapsible; and
- a keyboard-accessible splitter may resize chat within bounded minimum and maximum widths.

The document navigation pane can switch between the document tree and active-document TOC without
creating a second fixed sidebar.

### Compact mode

When the container cannot satisfy the wide-mode minimums:

- chat becomes a right-side drawer, closed by default but retaining unread/running affordances;
- document navigation becomes a drawer or compact overlay;
- the document receives the remaining width; and
- opening either drawer traps focus, supports Escape, and does not resize the iframe to an
  unusable strip.

This transition should be driven by a `ResizeObserver` and the actual sum of pane minimums. A
single hard-coded 1024 px viewport breakpoint does not account for the global sidebar or embedded
Hub widths.

Persist only presentation preferences such as chat collapsed state and bounded chat width in
`localStorage`. Do not persist agent messages, API keys, or bridge data.

## Component boundary

`SpecPage.tsx` is already large and should become an orchestrator rather than absorb all new
behavior. The proposal should plan for focused modules:

- a pure document-tree builder and search matcher;
- a document navigation pane;
- a document picker dialog;
- a spec iframe wrapper that owns injection and bridge validation;
- a responsive workspace shell; and
- small hooks for container mode and persisted layout preferences.

`Sidebar` should accept an explicit compact mode from `App` based on the active page. It should not
read global page state itself.

## Verification boundary

The change needs automated UI coverage for:

- tree construction, sibling ordering, orphan fallback, and missing/unfiled states;
- home and selection fallback behavior;
- keyboard search, ranking, disabled missing results, and focus behavior;
- bridge source/version/payload rejection;
- valid TOC handshake, active-section updates, and no-TOC fallback;
- same-document and cross-document navigation, including unsafe and unknown targets;
- wide/compact transitions and drawer behavior;
- persisted layout bounds and corrupt preference fallback;
- unchanged manifest repair and spec-chat session behavior; and
- TypeScript build and production Vite build.

Tests should exercise bridge logic as pure functions where possible. JSDOM does not provide a
real sandboxed frame or layout engine, so one manual browser pass remains required for iframe
scrolling, focus, splitter behavior, and the measured laptop-width layouts.

## Proposal guardrails

- Do not add runtime dependencies.
- Do not weaken the iframe sandbox.
- Do not hide documents merely because manifest metadata is absent or invalid.
- Do not parse intrinsic metadata in the UI as a competing source of truth.
- Do not require existing spec documents to change for shell navigation.
- Do not remove standalone in-document navigation.
- Do not regress repair messaging, SSE refresh, theme injection, or chat continuity.
- Do not add application-wide URL routing as incidental scope.

## Explicit non-goals

- Editing specs in the Hub.
- Full-text search inside document bodies.
- Reordering or reparenting manifest entries from the tree.
- Adding topic tags or another archive taxonomy to the manifest.
- Repairing manifest drift directly in the UI.
- Browser-addressable document deep links.
- External-link browsing from the sandbox.
- Replacing the existing spec-agent chat model.

## Remaining proposal-time decisions

These are bounded implementation choices, not blockers to proposing the change:

- exact navigation-pane and chat width tokens after a browser measurement pass;
- whether splitter resizing ships in the first task slice or follows collapse/drawer behavior; and
- the precise non-blocking error treatment for an unresolved cross-document link.
