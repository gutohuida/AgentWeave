# S8-jobs rationale — scheduled jobs (`JobsPage`, `JobCard`, `JobForm`)

First sub-screen of overflow item S8 (`jobs`, then `agents`, then `logs/activity`, then the command
palette — each its own four-pass unit, per the queue item's own text and `pre_authorised`'s "do not
start a later S8 sub-screen while an earlier one has unfinished passes"). Four passes: P1 explore,
P2 validate + mock, P3 iterate, P4 finish (this document).

## Research → six findings, three of them missing features

Full sourcing lives in `RESEARCH.md`: `JobsPage.tsx`, `JobCard.tsx` and `JobForm.tsx` read in full
including comments (two encode deliberate decisions preserved rather than "fixed" — `RunHistory`
must not say "no runs yet" while still loading, and the run-history row's error-summary-before-
timestamp ordering avoids a `"scheduled1 minute ago"` collision); `hub/ui/src/index.css` for the
available tokens; and `_system/foundations.html`/`controls.html` (U0a/U0b), since Jobs is the first
numbered screen built after the system pass and so the first real test of whether that vocabulary
composes onto a scheduling list rather than only the surfaces it was designed against. External
research covered cron-builder UIs (live plain-English translation + next-fire preview before
commit), modern self-hosted cron dashboards (next-run time and run-history trend treated as
first-class list information, not hidden behind an expand), and GitHub Actions' own workflow-run
list (status-coloured, terse at the collapsed level, detail one click away) — confirming
AgentWeave's existing two-level card shape is right, just under-styled at the collapsed level.

1. **The cron string is never translated to English anywhere the operator sees it**, before or
   after creating a job — a missing-feature gap, not a colour problem. Mocked as a small,
   dependency-free formatter covering the finite preset-like shapes this product's jobs actually
   use; not implemented, per scope.
2. **No next-run preview before submit** — same category as (1), mocked not implemented.
3. **The collapsed card carries no run-health signal at all** — "is this job okay" requires an
   expand plus, for an uncached job, a network fetch. A genuine information gap, not decoration.
4. **Texture/motion gaps, same character as every screen so far**: no hover lift on cards, minimal
   active-state contrast on filter pills/cron chips, no weight distinction between primary
   (`Run`)/routine (`Pause`/`Resume`)/destructive (`Archive`) actions, no chevron rotation, flat
   `variant="secondary"` loop-queue badges regardless of status word, a generic spinner instead of
   a job-shaped skeleton.
5. **`JobForm`'s native radio/checkbox controls are unstyled**, inconsistent with `controls.html`'s
   segmented/toggle patterns; the loop disclosure has no container or motion once open.
6. **The `Local` source badge is easy to miss** despite a locally-defined job behaving differently
   enough (see `hub/hub/jobs`) that at-a-glance distinction is worth more visual weight.

## What was rejected, and under which clause

Nothing from `RESEARCH.md` was discarded — P2 validated all six against `IDENTITY.md`'s rejection
test and all six passed, checked clause by clause in `RESEARCH.md` itself: run-trend dots and
loop-queue badge tones reuse `RunHistory`'s and `Badge.tsx`'s own status→colour maps verbatim
(clause 1, no new hue), `--blue` keeps its existing single job as `Next:` text and gains no new
role (clause 2), cards/chips/buttons/form panel all derive from the existing radius family and the
pill-shaped filter tabs/cron chips are the real component's own existing shape, not a mock
invention (clause 3), `'JetBrains Mono'` for the cron chip exactly as today (clause 4), lucide-style
stroke icons only (clause 5), the trend dots and translation line are additive single lines rather
than a layout that costs rows (clause 6), and the skeleton sheen is a motion effect over a flat
fill — the same pattern `foundations.html` already established — not a gradient surface (clause 7).
A pie/donut/gauge for run health was considered from the research and rejected under clause 6/7: a
row of small status dots is the density-preserving, identity-consistent equivalent to a chart.

**Two variants** — `restrained.html` (token-only fixes: hover lift, focus-visible, motion,
weight-differentiated actions, chevron rotation, coloured loop badges) and `considered.html` (all
of the above plus the three missing-feature mocks: cron-to-English translation line, next-run
preview in the form, and the run-trend dot strip on the collapsed card). Both explore degree of the
same language, not a different one.

## P3 — screenshot iteration, no defect found

All four renders (restrained × light/dark, considered × light/dark) were captured at 1040×1400 and
read: legible in both themes, no layout breaks, no clipped or overlapping text, only the same 3
pre-existing font `ERR_FILE_NOT_FOUND` console errors every mock this run carries. The loop-queue
badge colours were cross-verified against `Badge.tsx`'s actual `STATUS_STYLES` map rather than by
eye — confirmed the mock's `blocked` badge deliberately falls back to `b-neutral`/`STATUS_STYLES
.pending`, replicating the real component's own fallback for an unmapped status key rather than
accidentally matching it, and confirmed a second loop-block with a different status mix (green/
amber/red/grey) proves the mapping composes rather than being tuned to one example. All seven
rejection-test clauses were re-run against the renders; all passed. No defect surfaced — P2 was
unusually careful (`LoopBlock` and `Badge.tsx` source read directly before mocking, not
approximated), and this pass confirmed that care held rather than finding something new, which the
protocol treats as a legitimate P3 outcome, not a skipped one.

## P4 — real interaction, not another look at a screenshot

P2/P3 both worked from static renders. Following S7's P4 precedent (where a real narrow-viewport
and keyboard pass caught a genuine overflow bug static screenshots missed at desktop width), P4
here used the same two real-interaction checks rather than re-reading the same PNGs:

**A 420px narrow-viewport reflow check** on both files, measuring
`document.documentElement.scrollWidth` against the viewport width directly (not by eye) — both
files measured `scrollWidth == 420` at both 1040px and 420px, i.e. no overflow at either width. No
overflow bug to fix, unlike S7 at this exact width.

**A real keyboard `Tab` walk** (`document.activeElement` read after each of 15 `Tab` presses, not a
CSS rule read off a screenshot) across both files. A first pass produced a false alarm: two button
variants (`.btn.ghost`, `.btn.destructive` — the Pause/Resume and Archive actions) appeared to have
a fully transparent focus box-shadow, which would have been a real accessibility defect (keyboard
users reaching the row actions with no visible indicator at all). Re-ran with a 250ms settle delay
after each `Tab` press before reading computed style, since the first pass read mid-transition
(the resting 1px drop-shadow and the incoming ring blended in the computed value at the moment of
sampling) — the corrected reading shows the identical ring
(`0 0 0 2px var(--bg), 0 0 0 4px var(--ring)`) on every tabbable element in both files, ghost and
destructive included. Traced why: `restrained.html`/`considered.html` define `:focus-visible` rules
for only `.theme-toggle`, `.btn.primary`, `.btn.outline` and `.filter-pill` directly, but both files
`<link>` the real `hub/ui/src/index.css`, which carries its own global
`button:not([data-slot="button"]):focus-visible` rule (`index.css:287-288`) — every real `<button>`
element gets the ring for free from the imported stylesheet regardless of the mock's own per-variant
rules. Confirmed this is the actual mechanism, not assumed. **No real defect** — the false alarm was
a timing artifact in the first check script, caught and corrected before being recorded as a
finding, exactly the discipline the protocol asks for (verify before reporting, not the other way
round).

**No fix was needed this pass.** Recorded as a legitimate P4 outcome per the protocol: the pass
still did real work (two genuine interaction checks a screenshot cannot perform), it simply
confirmed P2/P3's care held rather than turning up something new — the second screen this run to
finish all four passes clean (S7 caught a real bug in the same slot; S8-jobs did not, and that
difference is itself worth recording rather than presenting both as identical).
