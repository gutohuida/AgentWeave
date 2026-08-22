# S8-logs research — the activity feed and log console (`ActivityLog`, `EventRow`, `LogsView`, `LogLine`)

Third sub-screen of queue item `S8` (`jobs` and `agents` both closed 4/4 — `pre_authorised`: "do not
start a later S8 sub-screen while an earlier one has unfinished passes"). This pass reads the
current code end to end before touching anything, per `screen_pass_protocol`.

## What these actually are, and how they're joined

The queue item names four components as one screen (`LogsView`, `LogLine`, `ActivityLog`,
`EventRow`). They are, but not as siblings — `App.tsx:441-461` renders them as **two subviews of one
tab**, switched by a bare `activity`/`logs` button pair with no visual state beyond `aria-pressed`
(no background, no border, no active fill — literally unstyled text buttons, the plainest control in
the product so far this run). Reading both components confirms they are genuinely different
personas over overlapping data, not a duplicate:

- **`ActivityLog`** (human-facing feed) — actor-centred cards: coloured icon bubble by event kind
  (`chat`/`task_alt`/`help`/`bolt`), agent name with its identity-colour dot, a relative timestamp
  (`formatDistanceToNow`), Pause/Resume, and a severity filter row. Backed by the shared instance-
  wide SSE stream (`useSSE`) plus a `/events/history` fetch on mount, capped at `MAX_EVENTS = 200`
  client-side.
- **`LogsView`** (developer/debug console) — a dense monospace table: sticky column header
  (TIMESTAMP / SEV / EVENT TYPE / AGENT / MESSAGE), search box, agent `<select>`, severity chips,
  category chips (`transport`/`watchdog`/`runner`/`proxy`/`setup`/`jobs`/`stderr`, derived client-
  side by `eventCategory()` string-matching on `event_type`), a Live/Paused toggle with a pulsing
  dot, and a "jump to latest" nudge when the operator has scrolled up. Backed by `useLogs` (REST +
  SSE-triggered invalidation), not the same client hook as `ActivityLog`.

Both are legitimate, matching a well-established external pattern (below) — this is not a
duplication to fix, and `RATIONALE.md` should say so explicitly to preempt future flagging of it as
one.

## What was read

- **`LogsView.tsx`** (full). Column-header table, `SEVERITY_ACTIVE_STYLE`/chip logic duplicated as
  inline `color-mix()` JS objects rather than the shared `tint()` helper `LogLine`/`EventRow` both
  already import from `lib/colorTint.ts` — same computed colour, two implementations. The toolbar
  `chipBase` object (severity + category chips) carries **no `transition` at all** — state changes on
  these chips are an instant snap, the only interactive control read this run with literally zero
  motion, not even an unscaled one.
- **`LogLine.tsx`** (full, including comments). Hover is applied via inline `onMouseEnter`/
  `onMouseLeave` JS setting `style.background` directly, bypassing the `--row-hover` token other
  screens use through CSS. The row is a `<div onClick={...}>` with no `role`, no `tabIndex`, no
  keyboard handler — a log entry with expandable JSON is **not reachable or expandable by keyboard at
  all**, the only true accessibility gap (not just styling) found this run. The expand chevron swaps
  icon name (`expand_more` ⇄ `chevron_right`) with no rotation transition. The copy button reveal
  (`opacity-0 group-hover:opacity-100 transition-opacity`) uses Tailwind's default duration, one more
  instance of the ad-hoc-vs-`--dur-*` split `IDENTITY.md` already measured (9 tokenised vs. 44 ad
  hoc). `SEVERITY_CHIP` covers `error`/`warn`/`info`/`debug` — every severity gets a chip here.
- **`ActivityLog.tsx`** (full, including comments). A defensive-programming comment on `pausedRef`
  explains it mirrors a stale-closure pattern even though `useSSE` doesn't need it today — read, not
  touched. `chipBase` here *does* set a transition, but hardcodes `'background-color 0.15s,
  border-color 0.15s, color 0.15s'` — the literal value equals `--dur-fast` (150ms) but is not the
  token, so a future change to the scale silently misses this file. No explicit loading state: the
  empty state (`EmptyState`) is shown whenever `visibleEvents.length === 0`, which reads identically
  whether the initial history fetch hasn't resolved yet or the feed is genuinely empty — a real,
  if minor, correctness-adjacent gap (same shape as the `RunHistory` "no runs yet" bug `S8-jobs`'s
  research flagged, though lower stakes here since it's just a fetch-timing window on tab open).
- **`EventRow.tsx`** (full). `SEVERITY_CHIP` here covers only `error`/`warn`/`debug` — **`info` gets
  no chip**, unlike `LogLine`'s equivalent map. Both are reading the same `severity` field from the
  same backend; the asymmetry is arbitrary, not a deliberate persona difference (a human-facing feed
  omitting the "nothing's wrong" badge is defensible, but nothing in the code says this was a choice
  rather than an oversight). No copy-entry affordance at all, unlike `LogLine`.
- **`hub/ui/src/index.css`** — confirmed available tokens for this pass: `--row-hover`, `--dur-fast/
  base/slow`, `--ease`, `tint()` (`lib/colorTint.ts`), the semantic colours, `--surface/-2/-3`,
  `--border`, the `content-24` radius step (used by the JSON-expand panel's `rounded-lg`, actually
  `--radius-lg` not content — checked, no mismatch).
- **`design/mocks/_system/foundations.html` and `controls.html`** (U0a/U0b) — the segmented-control
  pattern built there is the direct fix for the bare `activity`/`logs` subview switch; the elevation
  and interaction-state vocabulary this mock draws from rather than inventing again.

## External research

- **SigNoz logs UI** (fetched): recommends log volume/graph "at a glance" alongside the raw list, an
  advanced field-mix query builder, and live tail as first-class, not a checkbox afterthought.
  AgentWeave's `LogsView` has the live toggle but **zero visual overview** — no volume-over-time
  signal anywhere, pure list. A thin severity-coloured sparkline/histogram strip above the list is a
  genuine missing-information gap by this source's own standard, not decoration.
  ([SigNoz: Logs UI](https://signoz.io/blog/logs-ui/))
- **Console/devtools filtering conventions** (Chrome DevTools Console reference, general search):
  severity-level checkboxes/toggles, free-text filter, and **regex filtering** are the near-universal
  trio; AgentWeave's search is substring-only (`toLowerCase().includes`), no regex mode. A missing
  feature, not a styling gap — worth noting, out of scope to implement in a mock.
  ([Chrome DevTools: Console features reference](https://developer.chrome.com/docs/devtools/console/reference))
- **Log colorization conventions** (Papertrail, general search): colorizing *by source/program* in
  addition to severity is common in mature log viewers. AgentWeave's category chips (`transport`/
  `watchdog`/...) are filter-only today, uncoloured. **Rejected as a direction before it reaches
  P2**: giving each of 7 categories its own hue would need 7 new colours, which fails `IDENTITY.md`
  clause 1 (no new hues) and its "semantic colour is earned" principle (these are not states). If
  category needs a visual anchor, it must reuse the existing 8-colour *agent* scale's neutral
  siblings or stay monochrome with icon-only differentiation — a call for P2, not this pass.
  ([Papertrail: Log colorization](https://www.papertrail.com/help/log-colorization/))
- **T3 Code sourcemaps**: no standalone log-list/activity-feed surface exists in T3 Code — its
  closest analogue is `ThreadTerminalDrawer.tsx`, an in-thread embedded terminal, not a separate
  console screen. Read anyway for transferable patterns: it derives its terminal theme colours by
  reading real computed CSS custom properties at runtime (`readThemeColor`) rather than hardcoding,
  and uses the same `opacity-0` + `transition-colors` hover-reveal idiom `LogLine`'s copy button
  already uses independently. Confirms the token-driven approach is the right direction; nothing here
  was a new pattern to import. Not quoted at length or committed, per `IDENTITY.md`'s reference-only
  rule.

## Findings — what's missing, not just unstyled

1. **The subview switch itself is the plainest control found this run.** Two `<button>`s with only
   `aria-pressed`, no background, no border, no active fill, no motion. This is the literal entry
   point to both surfaces and currently looks like unstyled markup. Fix with the segmented-control
   pattern `_system/controls.html` already established — direct reuse, not a new pattern.
2. **No log-volume overview.** SigNoz names this explicitly as a UX baseline; AgentWeave's `LogsView`
   has none. A thin sparkline/histogram strip (severity-coloured, using existing semantic tokens)
   above the toolbar or column header is in scope to mock.
3. **`LogLine`'s expandable rows are keyboard-unreachable.** A `<div onClick>` with no `role`,
   `tabIndex`, or key handler is a real accessibility gap, not a styling one. The mock should give
   expandable rows a proper interactive role and a visible focus ring (`--row-selected`/focus-visible
   pattern from `_system/foundations.html`), matching the keyboard-nav expectation console-style UIs
   set (Chrome DevTools console rows are keyboard-navigable).
4. **`EventRow` has no `info` severity chip and no copy-entry affordance**, while `LogLine` has both.
   Both read the same backend `severity` field for the same kind of event — this reads as drift, not
   a deliberate difference between the two personas. Worth aligning in the mock (adding `info` case,
   note copy affordance as a feature gap) while keeping the two surfaces' distinct *shapes* (feed
   cards vs. table rows) intact.
5. **Zero motion on the two most state-heavy controls.** `LogsView`'s severity/category chips have no
   `transition` property at all (instant snap); the expand chevron swaps icon rather than rotating.
   Both are direct, low-risk applications of `--dur-fast`/`--ease` — exactly the under-applied-not-
   missing gap `IDENTITY.md` measures project-wide.
6. **No skeleton loading anywhere in either surface.** `LogsView` shows plain `"Loading…"` text;
   `ActivityLog` shows no distinct loading state at all (empty-state and "still fetching" look
   identical). Same generic gap `IDENTITY.md` and `S8-jobs`'s research already named for this
   product; a shape-matched skeleton (a few dimmed row placeholders) is in scope here too.
7. **No regex search mode and no volume/source colorization**, per the external research above.
   Real feature gaps by the standards those sources describe; note in `RATIONALE.md` as observed-but-
   not-implemented, per `pre_authorised`'s "mock every missing feature you find, don't build it."
8. **Duplicated colour computation.** `LogsView`'s `SEVERITY_ACTIVE_STYLE` reimplements `color-mix()`
   inline instead of calling the shared `tint()` helper its own sibling `LogLine` already imports.
   Not a visual defect today (the computed colour is identical) but worth modelling the mock on
   `tint()` consistently, since that is what closes the gap if this ever gets implemented for real.

## What must not change (`IDENTITY.md` clauses 1, 2, 6)

- No per-category hue scale (finding rejected above under "External research" — 7 new colours fails
  clause 1). Category differentiation, if mocked at all, stays icon/weight-based, not colour-based.
- `--blue` stays reserved for focus/selection; the Live-mode pulsing dot and any volume-strip
  "current" marker must not adopt blue as a status fill — reuse the existing green/amber/red mapping
  already in `SEVERITY_CHIP`/`EVENT_TYPE_COLOR`.
- Density must not drop: the sparkline/volume strip (finding 2) is a single additional thin row, not
  a panel that pushes the log list below the fold on a normal viewport.
- The two surfaces' distinct shapes (narrative feed vs. dense table) stay distinct — aligning finding
  4's inconsistencies is not licence to merge `ActivityLog` and `LogsView` into one layout.

## Validation against `IDENTITY.md`'s rejection test (preliminary, before building any mock)

1. **Palette** — every colour the mock will need (segmented-control fill, sparkline bars, focus
   ring, skeleton sheen) is an existing token or an existing `tint()`/`color-mix()` of one; no new
   hex. Checked against the category-colour temptation specifically and rejected it above.
2. **`--blue` stays focus/selection** — unchanged; no new fill role proposed.
3. **Radius scale** — segmented control, chips, table rows and the JSON-expand panel all already use
   `--radius`/`--radius-sm`/`--radius-lg`; no new geometry needed.
4. **Type** — existing family/scale; `'JetBrains Mono'` stays exactly where it already is (timestamps,
   event type, JSON payload) and does not spread to prose text.
5. **Icons** — lucide via `Icon` only; volume-strip needs no new icon, expand chevron reuses the
   existing `expand_more`/`chevron_right` pair with rotation added as motion, not a new glyph.
6. **Density** — findings 1, 3, 5, 6 add no rows; finding 2's volume strip is the only net-new
   vertical space and is a single thin row, an accepted density cost for a named information gap
   (same reasoning `S8-jobs` used for its run-trend dots).
7. **Flat-neutral character** — no gradients as a surface, no glass; the volume strip is flat coloured
   bars from semantic tokens (same idiom as `--row-hover` fills), not a chart library import.

No finding failed the test outright this pass; the one direction that would have (per-category hue
scale) was rejected before reaching a mock, per finding-rejection practice `S8-jobs` established.
Full clause-by-clause re-check happens again in P2 against the actual built HTML, per protocol.

## P3 — iterate

Both mocks booted `data-mode="dark"` with a bare toggle (flip `dataset.mode`, no `aria-label`) —
the same defect S8-agents' P3 found and fixed. `scripts/uishot.py`'s dark-capture path looks for a
button named exactly `"Switch to dark mode"` (the real app's own pattern, `ProjectHeader.tsx`/
`StatusBar.tsx`) and clicks it once, with no light-mode-toggle route at all; against a mock booted
dark with no matching label, `--theme dark` would silently capture the wrong default state and
`--theme light` had nothing to click. Fixed identically to the S8-agents precedent: both mocks now
default `data-mode="light"`, and a `toggleMockTheme()` function flips `aria-label`/`title` between
`"Switch to dark mode"`/`"Switch to light mode"` matching `ProjectHeader.tsx` exactly. Verified
`py -3.11 scripts/uishot.py --url file:///.../restrained.html --theme light|dark` (and
`considered.html`) captured all four correctly *unmodified* — no per-mock Playwright workaround
needed, same fix, same verification method, third screen running in a row where this exact toggle
recipe is now the default rather than something to rediscover.

Read all four captures fresh. Clause-by-clause against `IDENTITY.md`'s rejection test:

- **Clause 1 (tokens only)** — grepped both files for hex/`rgb()`/`rgba()` literals. Two hits in
  `restrained.html` (`rgb(0 0 0 / 0.16)`, `rgb(0 0 0 / 0.2)`, both shadow alpha), one in
  `considered.html` (`rgb(0 0 0 / 0.2)`); matches existing non-chromatic shadow-alpha practice
  already validated for this same reason in S8-agents' P3. A third apparent hit (`#4c1a`) in both
  files is a conversation-ID string in mock content ("replied in #conversations-continue" /
  "reply queued in conversation #4c1a"), not a CSS colour — false positive from the regex, not a
  violation.
- **Clause 3 (durations/easing)** — every discrete-interaction `transition` is `--dur-fast`/
  `--dur-base`/`--dur-slow` with `--ease`, no ad hoc literal. Two ambient/infinite `animation`s
  (`pulse-dot 1.6s`, `skel-sheen 1.4s`) are hardcoded rather than token-driven — checked against
  the same precedent S8-agents' P3 established (`task-live-pulse 2.4s ease-in-out infinite` in
  `index.css` is itself hardcoded): the `--dur-*` scale is scoped to discrete transitions, not
  ambient/looping ones, so this is consistent with the codebase's own practice, not a gap.
- **Clause 4 (radius)** — segmented control, chips, table rows, volume strip and the JSON-expand
  panel all reuse `--radius`/`--radius-sm`/`--radius-lg`; nothing new.
- **Clauses 2, 5, 6, 7** held on inspection: `--blue` appears only on focus rings and the arrival
  flash (never a status fill — Live/severity still read green/amber/red from the existing map);
  icons are lucide-style inline SVG only; density is unchanged from P2 (the volume strip is still
  the only net-new row); both variants read as the same app refined, legible in both themes; the
  interaction-states strip in both variants demonstrates resting/hover/active/focus-visible/live
  explicitly, and `considered.html` additionally demonstrates the arrival-flash mid-fade state.

No clause failures survived the critique — the only real defect found was the theme-toggle bug,
now fixed and verified. `git status --short` shows only the two mock HTML files and this section
modified; no other tree changes this pass. Verification screenshots (4 PNGs, written under `/tmp`
via `uishot.py --out`) were deleted after reading, per the blanket `*.png` `.gitignore`.
