# S8-logs rationale — the activity feed and log console

Third `S8` sub-screen (jobs and agents both closed 4/4 first, per `pre_authorised`'s "do not start a
later S8 sub-screen while an earlier one has unfinished passes"). Four passes (P1 explore, P2
validate + mock, P3 iterate, P4 finish — this document).

## The queue item names four components as one screen; they are two subviews of one tab

`ActivityLog`/`EventRow` (human-facing feed) and `LogsView`/`LogLine` (developer console) are
rendered by `App.tsx:441-461` as two subviews behind a bare `activity`/`logs` button pair — the
plainest control read this run: no background, no border, no active fill, only `aria-pressed`.
They are genuinely different personas over overlapping event data (actor-centred cards with
relative timestamps vs. a dense monospace table with column headers), not a duplication to merge —
`RESEARCH.md` says this explicitly so it isn't re-flagged as redundant later. Both mocks fix the
subview switch itself using the segmented-control pattern `_system/controls.html` (U0b) already
established, direct reuse rather than a new pattern.

## Research → eight findings, three of them missing information rather than styling

Full sourcing lives in `RESEARCH.md`: both components read in full including comments (one
deliberate non-bug left alone — `ActivityLog`'s `pausedRef` stale-closure guard, unneeded today but
harmless); SigNoz and Chrome DevTools console conventions (external); T3 Code's
`ThreadTerminalDrawer.tsx` (closest analogue, not a matching screen — no standalone log surface
exists there).

1. **No log-volume overview.** SigNoz names this as a UX baseline; `LogsView` is pure list, zero
   at-a-glance signal. Mocked as a thin severity-coloured sparkline/histogram strip above the
   toolbar — the only net-new vertical space either mock adds, an accepted density cost for a named
   information gap (same reasoning `S8-jobs` used for its run-trend dots).
2. **`LogLine`'s expandable rows are keyboard-unreachable** — a real `<div onClick>` with no
   `role`, `tabIndex`, or key handler is an accessibility gap, not a styling one. Both mocks give
   every expandable row `role="button" tabindex="0" aria-expanded`, and P4's real keyboard-tab walk
   (below) confirmed every one of them actually receives a visible focus ring, not just the markup.
3. **`EventRow` has no `info` severity chip and no copy-entry affordance**, while `LogLine` has
   both, reading the same backend `severity` field — drift, not a deliberate persona difference.
   Both mocks align the feed to carry the same chip and affordance the console already has.
4. Zero motion on `LogsView`'s severity/category chips (no `transition` at all) and the expand
   chevron swapping icon instead of rotating — both fixed with `--dur-fast`/`--ease`, the same
   under-applied-not-missing gap `IDENTITY.md` measures project-wide.
5. No skeleton loading state in either surface (`LogsView` shows plain "Loading…" text;
   `ActivityLog`'s empty-state and still-fetching states are visually identical) — same generic gap
   `IDENTITY.md` and `S8-jobs` already named for this product.
6. No regex search mode, no source/category colorization — real feature gaps by the external
   sources' own standards, noted in `RESEARCH.md` as observed-but-not-implemented per
   `pre_authorised`'s "mock every missing feature you find, don't build it."
7. Duplicated colour computation (`LogsView`'s `SEVERITY_ACTIVE_STYLE` reimplements `color-mix()`
   inline instead of calling the shared `tint()` helper its own sibling already imports) — modelled
   consistently on `tint()` in the mock so a real implementation has one thing to copy, not two.

## What was rejected, and under which clause

**Per-category colour scale** (transport/watchdog/runner/proxy/setup/jobs/stderr, one hue each) was
considered from the Papertrail source and rejected *before* reaching a mock: seven new hues fails
`IDENTITY.md` clause 1 (no new colours) and its "semantic colour is earned" principle — these are
sources, not states. If category needs a visual anchor at all, it stays icon-only or reuses the
existing agent-identity dots' neutral siblings; neither mock invents a colour for it.

Nothing else from `RESEARCH.md`'s findings failed the P2 validation pass (full clause-by-clause
check recorded there): the volume strip, focus rings, chip motion, skeleton states and alignment
fixes all trace to existing tokens, the existing `tint()` helper, or precedent already validated on
an earlier screen. Two variants only (`restrained.html`, `considered.html`), the same
degree-of-refinement axis every other S8 sub-screen used, not a third redundant "expressive" pass.

## P3 — a recurring toggle bug, fixed by the now-standard recipe

Both mocks initially booted `data-mode="dark"` with an unlabelled toggle — the identical defect
found in S8-agents' and (per that entry) generalized as the default recipe: `scripts/uishot.py`'s
dark-capture path clicks a button named exactly `"Switch to dark mode"` (`ProjectHeader.tsx`'s own
convention) with no light-mode route, so an unlabelled dark-booted mock silently defeats the tool
rather than erroring. Fixed identically: both now default `data-mode="light"`, with
`toggleMockTheme()` flipping `aria-label`/`title` to match `ProjectHeader.tsx` exactly. Verified
`uishot.py --theme light|dark` against both files unmodified — this is now the third screen running
where the fix is applied from precedent rather than rediscovered.

Full clause-by-clause critique against `IDENTITY.md` after the fix (detail in `RESEARCH.md`'s
"P3 — iterate" section): no failures. Tokens-only held (two non-chromatic shadow-alpha `rgb()`
literals per file, matching existing practice; a `#4c1a` conversation-ID string in mock content was
a regex false positive, not a colour). Durations held on the same "scale covers discrete
transitions, not ambient/infinite ones" reasoning already established for `task-live-pulse`.

## P4 — real interaction and narrow-viewport verification

P2 and P3 both worked from screenshots read by eye. P4 used the S8-agents precedent instead —
actually driving the page, the class of bug static review can't catch:

- **Real keyboard `Tab` walk**, both files, reading `document.activeElement` after each press: 44
  stops in `restrained.html`, 41 in `considered.html`, every one showing a visible focus ring
  (`box-shadow`/`outline` present, none `none`) — including finding 2's previously-unreachable
  expandable rows, confirming the accessibility fix actually works under real keyboard navigation
  and not just in markup.
- **420px narrow-viewport reflow check** (same width used as precedent by S6/S7/S8-agents): both
  files measured `document.documentElement.scrollWidth === 420` exactly — no overflow.
- **Real mouse-hover check** on the copy-button reveal (`opacity: 0` → `1` on `.log-row-main:hover`):
  confirmed genuine — the first read showed `0` both before and immediately after `hover()`, which
  first looked like a bug, but was a sampling artefact: `getComputedStyle` was polled before the
  `--dur-fast` opacity transition had advanced a frame. Re-checked after a short settle and the
  reveal is correct in both files. Recorded here so a future pass doesn't waste time rediscovering
  that a same-tick read of a transitioning property understates it — poll after the transition
  duration, not synchronously after the trigger.

No defect survived P4 — a legitimate "clean" outcome, same as S8-agents' P4 in the same slot, not a
skipped check.

## Result

`design/mocks/S8-logs/{restrained,considered}.html`, both passes complete, added to
`design/mocks/index.html` below. This closes S8-logs at 4/4 and leaves only the command palette as
S8's remaining sub-screen per `S8`'s stated sub-order.
