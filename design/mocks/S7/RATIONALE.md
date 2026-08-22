# S7 rationale — the overview screen

Four passes (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this document).
`OverviewPage.tsx`, one file with six differently-weighted inline sections (header, budgets, agent
health grid, workspace shortcuts, task summary chips, activity ticker) rather than several separate
components — this is the landing surface, the operator's first look at the product every session.

## Research → seven findings, three of them missing features

Full sourcing lives in `RESEARCH.md`: the component read in full including its comments (three of
them, `AgentHealthCard`'s deliberate static-glow-not-`animate-ping` choice for `stalled` agents chief
among them, were left alone as decisions already made correctly, not gaps); two `WebSearch` passes
(dashboard/overview information-hierarchy patterns; empty-state/first-run patterns); and four T3 Code
sourcemap analogues pulled directly (`ContextWindowMeter.tsx`, `ThreadStatusIndicators.tsx`,
`NoActiveThreadState.tsx`, and `ProviderStatusBanner.tsx` — the last explicitly **not** adopted, its
container literally named `alert-glass`, which IDENTITY.md clause 7 forbids outright).

1. **The page title carried the least visual weight of anything on it.** A plain 14px/600 `<h1>`,
   smaller than `AccountingPanel`'s own embedded heading. Both mocks give the header a clearer
   weight step, no new type scale.
2. **`AccountingPanel`/`SettingsSection` reuse is a fit problem.** That CSS was built for a
   dedicated settings page (`min-height: 76px` rows, no border/background of its own) and, pasted
   into `OverviewPage`'s stack, reads as a page fragment rather than a native widget. Addressed by
   the grouping fix (finding 7) rather than touching `SettingsSection` itself — out of scope, and a
   mock can't safely change a component other screens depend on.
3. **`AgentHealthCard`'s hover transition was a literal `'border-color 0.15s'` string**, not
   `var(--dur-fast)` — IDENTITY.md's own measured problem (9 token uses vs. 44 ad-hoc) caught
   in the wild. Both mocks replace it with the token; `considered.html` also adds an elevation lift
   and background shift on hover, not just the one border-color change.
4. **No `:focus-visible` treatment at all on a keyboard-reachable navigation card.** Both mocks add
   a visible ring using `--ring`, the same token every other screen's selection state already uses.
   **Verified working via a real keyboard `Tab` walk in P4**, not just declared in CSS and assumed —
   see the P4 section below.
5. **`.lifted-surface` had a resting-state shadow and nothing else** — no hover rule, no active
   rule, no transition property, shared by three primary-navigation buttons (Tasks/Spec/Jobs). Both
   mocks give it its first hover/active/focus-visible states; `considered.html` also adds the two
   already-mapped icons (`task_alt`, `schedule`) plus a plausible third for Spec, addressed as a
   missing-feature note below since it changes information content, not just styling.
6. **The task-status colour mapping is a hand-rolled ternary local to this one file** — grepped
   `hub/ui/src` and found `TaskCard.tsx`/`TasksBoard.tsx` (S2) independently re-derive the same
   five-way mapping. Not fixed here (mocks-only scope, and a shared config is a source change), but
   flagged so a mock that quietly "fixed" the overview's chip colours wouldn't read as a second,
   still-independent copy.
7. **No grouping between six blocks of different visual weight**, all `space-y-6`. `considered.html`
   adds three named groups (state / attention / navigate) using the existing `--border-region`
   hairline the page's own header already draws — no new divider style — an ordering informed by
   the F-pattern research (decision-critical agent-health signal moved above the budget panel).

Three ideas were mocked as **missing features and flagged, not implemented**, per the
pre-authorization: icons on the workspace buttons (finding 5, above — genuinely new information, not
just decoration), a shared task-status colour config (finding 6), and a **populated-preview empty
state** for the agent grid — a ghosted, non-interactive sketch of what a populated grid looks like,
gradient-masked into the existing "No agents connected" message, rather than plain prose alone.
`considered.html` builds this as a labelled candidate alongside the plain empty state, explicitly not
a replacement — `RATIONALE.md` (this document) is where the choice between them is recorded for the
operator, not decided unilaterally.

## What was rejected, and under which clause

Nothing from `RESEARCH.md`'s findings was discarded — P2 validated all seven against `IDENTITY.md`'s
rejection test and all seven passed: token-driven transitions and a hover rule for `.lifted-surface`
(clauses 1/3, tokens only), focus-visible using `--ring` (clause 2 — stays focus/selection, doesn't
become a brand colour), grouping dividers reusing `--border-region` (clauses 3/4, no new geometry),
workspace icons sourced from `Icon.tsx`'s existing map (clause 5, no new icon source), and the
status-change ring kept explicitly distinct from the always-on `pulse` glow the component's own
comment marks as deliberate (does not touch the do-not-undo finding). `ProviderStatusBanner.tsx`'s
glass container was read for layout shape only and its `alert-glass` treatment was not carried over,
rejected under clause 7 (no glass, no gradient-as-surface).

**Two variants, not three** — a P2 decision recorded here per the protocol. S7 is six loosely-coupled
inline sections rather than one focal interaction; a third "expressive" degree was judged to repeat
`considered.html`'s ideas with more adjectives rather than show a reader anything new at this
surface's scale. `restrained.html`/`considered.html` still explore genuine degrees of the same
language — token-only fixes vs. full grouping + motion + icons + populated-preview candidate.

## P3 — a colder second look at the rendered screenshots, no defect found

P2's own build pass already screenshotted all four combinations (variant × theme) and read every
image. P3 went further: cropped and 1.5–2× upscaled the two regions most likely to hide a defect a
builder reviewing their own work would miss — `considered.html`'s populated-preview empty state (a
faded ghost card sitting under the centered "No agents connected" message, gradient-masked) and the
interaction-states strip (resting/hover/focus-visible/status-changed/pressed cells). Neither showed
clipping, overlap, or illegible text in either theme. Console errors (3 pre-existing font
`net::ERR_FILE_NOT_FOUND`s, same as every other mock this run) were re-confirmed per-file rather than
assumed carried over from P2. Verdict: no fix needed at that pass.

## P4 — a real-interaction and narrow-viewport pass, one genuine defect found and fixed

P2 and P3 both worked from **static screenshots** — real but resting-state (or single-hover) renders,
read by eye. P4 deliberately used a different method: real browser interaction and a real narrow
viewport, not another look at another screenshot, specifically to check what only executing the page
can reveal.

**Real keyboard `Tab` walk** (not a `:focus-visible` CSS rule read off a screenshot, an actual
`document.activeElement` check after repeated `Tab` presses) confirmed the finding-4 focus ring
described above genuinely activates and renders correctly in both files — a keyboard user reaching an
`AgentHealthCard` analogue by `Tab` sees the ring, not just a declared-but-untriggered CSS rule.

**A 420px narrow-viewport reflow check** (the same width S6's P3 used) found a **real, confirmed
overflow bug in `considered.html`**: `document.documentElement.scrollWidth` (558px) exceeded the
420px viewport. Bisecting element-by-element (`.doc` → `.overview-frame` → `.ov-group` → `.ov-grid`
→ `.ov-workspace`) isolated it to exactly one place — `.ov-workspace`'s three-column
`grid-template-columns: repeat(3, 1fr)` row (the Tasks/Spec/Jobs shortcuts), whose track correctly
sized each column to ~107px, but whose grid *items* (`.ov-work-btn`) did not shrink to fit: each
button's icon + gap + padding + un-wrapped detail text (e.g. "Requirements and evidence") computed a
content-based minimum wider than its track, and because `.ov-work-btn` itself (the grid item, as
opposed to its child `.ov-work-body`, which already had `min-width: 0`) had no `min-width` override,
its default `min-width: auto` used that full content-based minimum instead of shrinking — the classic
CSS Grid/Flexbox "child pushes a fixed-track container wider than its parent" failure mode. Fixed by
adding `min-width: 0` to `.ov-work-btn` itself (`considered.html`, one property, one rule) — re-ran
the same check afterward and `scrollWidth` dropped to exactly `420`, matching the viewport, with the
button's existing `overflow: hidden; text-overflow: ellipsis` on `.ov-work-detail` now actually able
to take effect instead of being overridden by the parent's un-shrunk minimum. `restrained.html` has
no icon and shorter, non-nowrap detail text in that button and measured `False` (no overflow) both
before and after — left untouched, since it had no defect to fix and adding the same property
defensively without a proven failure would be scope creep this queue item doesn't call for.

This is exactly the class of bug static-screenshot review structurally cannot catch: every P2/P3
screenshot was taken at a wide desktop viewport, where the same CSS defect never manifests because
there was always enough space for the grid tracks to reach their content-based minimum without
being visibly constrained. It took an actually-executed narrow layout to surface it.

## Verification summary across all four passes

- P2: `py -3.11` + Playwright loading each file via `file://` (no server — static documents), both
  variants × both themes, full-page screenshots read and checked against the rejection test.
- P3: cropped/upscaled colder re-read of the two highest-risk regions, per-file console check
  repeated rather than assumed. No mock defect found.
- P4 (this pass): real keyboard-driven focus-visible walk (confirms finding 4 actually works, not
  merely declared) and a real 420px-viewport reflow check (S6's precedent) — found and fixed one
  genuine `considered.html`-only overflow bug (`.ov-work-btn` missing `min-width: 0`), re-verified
  clean (`scrollWidth === 420`) after the fix, and re-ran the full hover/focus/420px battery on both
  files afterward with no regressions.
- All verification screenshots and throwaway scripts (`_p4_check.py`, `_p4_debug.py`, `_p4_shots/`)
  were deleted after use, per this queue's established no-committed-screenshots precedent
  (`.gitignore`'s blanket `*.png` rule) — `git status --short` confirmed only the intended `.html`
  diff and this document remained before committing.

**S7 is now fully done — all four passes (P1–P4) complete and verified, including one real defect
found and fixed at the pass built specifically to find what static screenshots can't.**
