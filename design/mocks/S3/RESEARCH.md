# S3 research — the right side panel

`PanelShell` and its tabs (`FileTree`, `FilePreview`, `SpecIndexTab`, `LoopsIndexTab`,
`FilesIndexTab`). Named in `STATE.json`'s queue as "always on screen while working" — unlike S1/S2
this surface is chrome the operator lives beside constantly rather than a page they navigate to, so
plainness here is a background irritant rather than a one-off bad impression. This pass reads the
current code end to end before touching anything, per `screen_pass_protocol`, then researches the
kind of surface it is (tabbed multi-purpose side panel: index tabs + drill-down detail tabs).

## What was read

- **`PanelShell.tsx`** (full, including comments). The generic shell all three panel tenants share
  (`2026-08-18-one-shell-three-panels`). Already carries real, considered engineering: WAI-ARIA
  `tablist` with automatic activation and a roving `tabIndex` (design D11 — "the first controls of
  their kind in this codebase"), arrow-key/Home/End navigation, `scrollIntoView` on activation for
  strip overflow (design D12, task 6.1), and a genuinely good empty state — a grid of launcher cards
  replacing what used to be one line of grey text, added directly off an operator complaint
  (2026-08-19: *"when we open the right screen and there is nothing there weird"*). None of this
  interaction design needs to change. What is missing is entirely visual: the tab strip and the
  launcher cards are functionally complete and visually inert.
- **`FileTree.tsx`** (full). Its own collapsed-state persistence (`localStorage`, keyed separately
  from the specs tree so folding one never disturbs the other), a chevron that already rotates with
  `transition: transform var(--dur-fast) var(--ease)` — one of the handful of places IDENTITY.md's
  "9 correct usages" count includes, and colour-coded file glyphs from `fileIcons.ts` reused as-is.
- **`FilePreview.tsx`** (full, including its two block comments). A genuinely careful trust-boundary
  decision is recorded here: it deliberately does **not** reuse `MarkdownMessage` (which carries a
  load-bearing "no `rehypePlugins`, ever" rule because it renders content the operator did not
  author) — a workspace file is content the operator opened from their own checkout, so it gets its
  own renderer with syntax highlighting. The one `dangerouslySetInnerHTML` is highlight.js's own
  escaped output, not raw file content. This boundary is correct and must not be touched.
- **`SpecIndexTab.tsx`** and **`SpecDocumentBrowser.tsx`** (full). One browser component serves both
  the Ctrl/Cmd+K picker and this tab (design: "the content and its rules do not change with the
  chrome around it"). Search-or-browse: empty query shows `SpecTree`, typing switches to a ranked
  flat list grouped into current / archived (opacity-dimmed, `0.65`) / missing (disabled, "missing"
  label) — missing documents are deliberately shown-but-unselectable so drift is visible rather than
  hidden. An inline "Start an exploration" affordance exists only when `onCreate` is wired.
- **`LoopsIndexTab.tsx`** (full). Already the most information-dense of the five: ending-state
  badges bucketed strictly from `ending_state` (not derived from `stop_reason` text — design D17),
  a running agent's name with a `smart_toy` icon (added 2026-08-19 after the operator asked "whose
  loop is this" could not be answered), queue-length, and an open-questions warning badge. This tab
  is close to done functionally; the gap is almost entirely surface polish (row hover/press, badge
  weight) rather than missing information.
- **`FilesIndexTab.tsx`** (full). Search-or-tree, same pattern as the spec browser. Selecting a file
  closes this tab per design D8 (handled centrally in `panelTabsStore.openTab`, not here).
- **`fileIcons.ts`** (full, including its two block comments). Already a deliberate, well-reasoned
  colour-coding system — whole-filename rules checked before extension rules (so `Dockerfile`,
  `Makefile`, `.gitignore` are recognised despite having no extension), and colour is explicitly
  called out as carrying most of the recognition at 12px ("`FileCode2` and `FileType2` are
  near-identical shapes at that size... it is the green-vs-blue that actually tells `app.py` from
  `panel.ts` at a glance"). Brand marks wear their own fixed colour and skip light/dark parity on
  purpose; this is consistent with U0b's colour-coding system and should be left alone, not
  reinvented.
- **`RowMenu.tsx`** (full) — the "+" add-tab affordance in the strip is this same component used
  elsewhere for row actions (2026-08-08 operator call: three-dot/plus affordances over right-click,
  "not everyone will think about it"). Its popup already uses real tokens (`--surface`, `--border`,
  `--radius`) — reuse it as-is rather than hand-rolling a second menu style for the tab strip.
- **`hub/ui/src/index.css`** — confirmed `--row-hover`/`--row-active`/`--row-selected` exist and are
  unused anywhere in these five files; every row in `FileTree`, `FilesIndexTab`, `LoopsIndexTab`, and
  `SpecDocumentBrowser` sets `background: 'none'` at rest with no `:hover` rule at all. Confirmed via
  `grep` that none of the five component files contain the string `row-hover`.
- **`design/mocks/_system/foundations.html`** and **`controls.html`** (the U0a/U0b outputs this
  screen inherits, per `screen_pass_protocol`'s own framing of the queue). Already define the exact
  vocabulary this screen needs and should reuse rather than reinvent: `.sk-line`/`.sk-row`/`.sk-chip`
  skeleton primitives, `.empty-state`/`.empty-icon-ring` (a second, more general empty-state pattern
  than `PanelShell`'s own bespoke launcher grid — worth checking they don't disagree), `.ctl-switch`
  (a real toggle control — `LoopsIndexTab`'s "Show archived" is a bare native `<input
  type="checkbox">` today), `.menu-panel`/`.menu-item` (already what `RowMenu`'s popup approximates
  inline), and the elevation tiers built from the existing surface steps.
- **Icon.tsx's icon map** — confirmed by `grep` that `folder_open` is the *only* folder glyph
  registered; there is no closed-folder icon (`folder`) to switch to. `FileTree.tsx` renders
  `folder_open` unconditionally regardless of `collapsed[row.path]` — not a bug introduced by
  under-styling, but a real, checkable gap: a collapsed directory shows the same "open" glyph as an
  expanded one. Fixing it for real needs a new `Icon.tsx` map entry, which is a source change outside
  a mock's scope (per `limits`); noting it as a finding to flag in `RATIONALE.md`, and the mock can
  still demonstrate the corrected visual (open vs. closed folder glyph) since mocks already inline
  lucide-shaped SVGs rather than calling the real component (confirmed by reading how S2's
  `considered.html` embeds icons — inline SVGs matching `Icon.tsx`'s actual shapes, not a
  dependency on the map at runtime).

## T3 Code reference (design pattern only — nothing quoted here is copied)

Read `RightPanelTabs.tsx`, `RightPanelSheet.tsx`, and `FileBrowserPanel.tsx` from the sourcemaps at
`...\t3code\...\assets\*.js.map`. This is the closest sibling surface that exists: a tabbed side
panel with an add-tab menu and an empty-state launcher grid — structurally the same problem
`PanelShell` already solved. What is worth carrying as *pattern*, restated for this palette rather
than copied:

1. **Tabs are pill-shaped chips in a scrollable strip**, not flat squared-off blocks: `h-6`, rounded,
   with the active tab's background the only thing distinguishing it at rest, and a `hover:bg-accent/
   60` wash on inactive tabs. AgentWeave's tab strip currently has *no* hover state on an inactive
   tab at all — only the always-visible close button is a `<button>` a cursor can register against;
   the label itself gives no feedback until you're already on it.
2. **The close affordance swaps in on hover**, not always-visible: the icon and the close glyph
   occupy the same slot, cross-fading via `group-hover`, so an inactive tab shows its identity icon
   until you're about to close it, then shows only `X`. AgentWeave's tab always renders *two* icons
   side by side (the descriptor icon, then a separate close button) whether or not the tab is
   hovered — takes more horizontal room per tab (real cost under IDENTITY.md's density clause, since
   more tabs fit in the same strip if idle tabs are narrower) and gives the close button no
   discoverability signal.
3. **Every tab wraps its label in a tooltip**, so a `max-w-*` truncated title is still readable on
   hover. AgentWeave's tab label has no `title` attribute and no tooltip — only the *close* button
   has a `title`. A long conversation subject, spec path, or loop label truncated at 140px is
   currently unreadable except by opening the tab.
4. **A tab context menu** (right-click: close / close others / close to the right / close all) is
   cheap, standard, and entirely absent from `PanelShell`. Given the pre-authorisation to flag
   missing features rather than implement them, this is worth mocking as a demonstrated affordance
   and noting in `RATIONALE.md` — not silently added to the real component.
5. **Middle-click (auxclick) closes a tab** without moving to the X — a small thing, absent here too.
6. **The empty-state launcher cards get real interaction states**: `hover:border-border
   hover:bg-accent/60`, a subtle inset ring in dark mode, and a disabled variant that keeps the same
   shape but dims and explains why via tooltip (T3's browser/diff cards, unavailable outside their
   desktop app, still render — greyed, with a reason on hover — rather than disappearing).
   `PanelShell`'s own launcher cards are static: no hover, no press, no focus-visible ring defined at
   all beyond the browser's UA default. This is the single clearest instance of IDENTITY.md's
   diagnosis — "states that were never designed" — on this screen.
7. **A card can badge a live count** (T3 badges its Agents launcher card with the running-subagent
   count). `PanelShell`'s `loops` launcher has no equivalent, even though `LoopsIndexTab` already
   computes exactly this number (`counts.running`) once the tab is open — the empty state discards
   information the app already has. Worth mocking as the kind of "missing information" the operator
   asked P1 explicitly to surface.
8. **File tree rows get a genuinely considered hover/selected treatment** built from
   `color-mix(in srgb, currentColor N%, transparent)` at low percentages (7–14%) rather than a flat
   token swap — soft, tonal, and automatically correct in both themes because it derives from
   `currentColor`. AgentWeave's own `--row-hover`/`--row-active`/`--row-selected` tokens already do
   the equivalent (`color-mix` against `--text`), so this is a case of "the right tool already
   exists, apply it" rather than importing a new technique.
9. **A file preview gets a persistent header**: refresh control, search field with an icon baked into
   the input rather than floating beside it, and (for the preview pane specifically, per the general
   web research below) a breadcrumb/path strip above the content. `FilePreview.tsx` renders straight
   into content with no header at all — the only place the current path is visible is the tab label
   itself, truncated, with no tooltip (see finding 3 above compounding this one).

## General web research (code/file preview UI conventions)

Searched for side-panel/file-tree/tabbed-panel patterns and code-preview-pane conventions
specifically (not just T3). Findings that generalise beyond one reference app:

- **Breadcrumb path headers are conventional** for a code/file viewer pane — a persistent strip
  above the content showing the full path (and, in richer viewers, a symbol path), often with a
  "copy path" affordance. `FilePreview.tsx` has none; the file's full path is knowable only from the
  tree it came from or the truncated tab label.
- **A copy-to-clipboard button on code content** is a now-standard, low-cost affordance (seen across
  documentation and preview tooling broadly, not just IDEs). Absent here.
- **Tree views commonly use indentation plus a light connecting guide** rather than indentation
  alone, to keep deep hierarchies scannable — worth exploring as a restrained option in P2, checked
  against IDENTITY.md clause 7 ("no texture" reads as no *literal* texture, not no connecting line;
  a 1px `--border` guide is structure, which the identity explicitly says is fine to suggest).
- **Search fields conventionally support Escape-to-clear/close** and show a leading search icon
  rather than relying on the placeholder text alone to signal purpose. Both `FilesIndexTab`'s and
  `SpecDocumentBrowser`'s search inputs are bare `<input>` elements with a placeholder and nothing
  else — no icon, no Escape handling, no clear button once text is typed.
- **Tabs pattern (general UX reference, uxpatterns.dev):** horizontal scrolling tab strips are the
  right choice specifically when the tab count is dynamic and may exceed the available width — which
  is exactly `PanelShell`'s situation (`overflow-x-auto` is already the right structural choice; the
  visual layer around it is what is under-designed).

## What is already good and should be left alone

- `PanelShell`'s interaction design (ARIA tablist, keyboard nav, scroll-into-view, close-vs-activate
  event handling, the empty-state-as-launcher-not-error framing).
- `FilePreview`'s trust-boundary separation from `MarkdownMessage` — do not merge them or add
  `rehype-raw` to either.
- `fileIcons.ts`'s colour-coding system and its whole-filename-before-extension precedence.
- `LoopsIndexTab`'s information architecture (ending-state bucketing from `ending_state`, not
  `stop_reason` text; the agent attribution row).
- `SpecDocumentBrowser`'s current/archived/missing grouping, including missing-but-visible documents.
- The chevron rotation in `FileTree` — already correctly on the motion scale.

## What's missing, concretely (for P2)

1. No hover/press/focus-visible state on any row across `FileTree`, `FilesIndexTab`,
   `LoopsIndexTab`, or `SpecDocumentBrowser`'s search results, despite the exact tokens for it
   already existing and being unused in all five files (`grep`-confirmed).
2. Tab strip: no hover feedback on inactive tabs, no tooltip on truncated labels, no context menu,
   redundant always-visible close icon costing horizontal density.
3. Launcher empty-state cards: no hover/press/focus states, no badge for live counts the app already
   computes (loops running count).
4. `FilePreview`: no path/breadcrumb header, no copy button, no visible language indicator beyond
   file extension inference.
5. Search inputs (files, specs): no icon, no Escape-to-clear, no visible affordance that they're
   search fields beyond placeholder text.
6. `LoopsIndexTab`'s "Show archived" is a bare checkbox; U0b already defined a `.ctl-switch` toggle
   vocabulary this should adopt instead.
7. Loading states are a plain `Loading…` paragraph in three of the five tabs; foundations.html
   already defines skeleton primitives (`.sk-line`, `.sk-row`, `.sk-chip`) sized for exactly this use.
8. Directory rows always show `folder_open`'s glyph regardless of collapsed state — no closed-folder
   icon exists in `Icon.tsx`'s map today; mockable visually, but real implementation needs a new map
   entry (source change, out of scope here — flag only).
9. No connecting structure in the file tree beyond indentation — an optional, restrained addition to
   explore (a 1px `--border` guide), not a requirement.

**Not building a mock this iteration** — P1 is explore-only per `screen_pass_protocol`. P2 validates
these findings against `IDENTITY.md`'s rejection test and builds `design/mocks/S3/<variant>.html`.
