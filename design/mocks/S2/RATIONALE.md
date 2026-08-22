# S2 rationale — task board + task cards

Four passes across three iterations (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this
document). The operator named this screen the worst offender, verbatim: *"The cards look very
plain, with no texture, no animation or fine details just a box with things written on it and the
task board the same."* `TasksBoard.tsx` / `TaskCard.tsx` / `TaskDetailDrawer.tsx` /
`TaskIntegrationNote.tsx`.

## Research → changes

Full findings and sourcing live in `RESEARCH.md`. Summary of what each of the ten verified gaps
became in the mocks, plus two further bugs found while building and iterating rather than by P1's
research pass.

1. **The priority badge is a real product bug, not a style gap.** `TaskCard.tsx:309` passes
   `task.priority` into `StatusBadge`, but `Badge.tsx`'s `STATUS_STYLES` map has no
   `low`/`medium`/`high`/`critical` entries — every priority falls through to the neutral default,
   so a `critical` task and a `low` one render an identical grey pill today. Fixed in both variants
   with a real `PRIORITY_STYLES` map, graduated across tokens already on the card (neutral → neutral
   → amber → red — the same amber/red already used for "Stalled" and "Prerequisite regressed" on
   this exact card, not a new hue). `considered` additionally disambiguates `high`/`critical` by
   *shape*, not just colour, with a flag glyph — because amber/red already carry a different meaning
   elsewhere on the same card (finding below). `restrained` disambiguates with a plain colour dot
   only — deliberately the smaller fix; see the P3 finding below on why that turned out to be the
   safer choice at this density, not merely a lesser one.
2. **No hover elevation** — today's only feedback is an inline `onMouseEnter`/`onMouseLeave`
   border-colour swap, no CSS `:hover` rule at all, on the one surface in the product where "the
   whole card is the button" (F5) is the entire interaction model. `considered`: lift + `--surface-3`
   + shadow on `--dur-base`. `restrained`: a real CSS `:hover` rule, border + fill only, no lift —
   the smallest change that still demonstrates a genuine state change (rejection-test clause 7)
   without adding elevation as a second, heavier commitment.
3. **No press/active state at all.** `considered`: settle + `--press-lo` inset. `restrained`: a
   one-step darken on `--press-lo`, no lift to release. Both forced via `data-force` in a
   rest/hover/press(/selected in `considered`) strip so every state renders without a live pointer.
4. **Column empty states are bare** — `EmptyState` exists and is used for the whole-board case but
   never per-column, and a 7-column board routinely shows several empty columns at once.
   `considered`: a small icon tile, sized down from `EmptyState`'s own icon-circle so it reads as a
   smaller member of the same family, not a competing pattern (confirmed against
   `EmptyState.tsx` before building). `restrained`: centred text in a dashed box, no icon.
5. **No drag-and-drop — a missing feature, not a style gap**, confirmed absent by reading both files
   for `draggable`/dnd imports. Mocked as an *illustration* only in `considered` (a mid-drag card,
   rotated/reduced-opacity/elevated-shadow, plus a highlighted drop-zone with the standard
   idle→hover→grab→move→drop microstates named in `RESEARCH.md`'s sourcing) — not built, per
   `pre_authorised`. `restrained` omits this section entirely: illustrating a feature that doesn't
   exist is itself an "expressive" move relative to `restrained`'s own degree, not a restrained one.
6. **The badge row was all same-shaped pills, nothing scannable by shape.** Addressed as part of
   finding 1's flag glyph (priority) and reuses the existing icon vocabulary elsewhere in the card
   (status pill, assignee-status dot) rather than adding new icon treatments beyond what finding 1
   already required — deliberately not over-iconified everything on the card, which would have
   pushed density (clause 6).
7. **Requirement chips and informational badges shared identical visual weight.** `considered`:
   requirement chips get a visible border and a hover state (clickable-looking); the informational
   "from: reviewer" badge stays flat text, no border — now two visibly different *kinds* of thing at
   rest, not just on hover. `restrained`: chips differentiated by a border alone, informational text
   unchanged.
8. **`TaskIntegrationNote` broke the card's own pattern** — every other fact on the card is a pill or
   a bordered block; the merge outcome was a bare `<p>` with only a text colour. `considered`: a
   bordered, icon-led block (`.integration-note`, confirmed present at `considered.html:176` and all
   three outcome call sites — merged/failed/skipped — lines 427/437/448) matching the card's existing
   pill/block idiom. `restrained`: a coloured left-rule instead of a full block — text-only micro-fix,
   no new container shape.
9. **No `tabular-nums` on the relative timestamp.** One-line fix, both variants:
   `font-variant-numeric: tabular-nums` on `.card-time` (`considered.html:174`) — the exact
   already-used-elsewhere-but-missing-here micro-detail `IDENTITY.md` names.
10. **The description clamp had no fade-into-more affordance.** `considered`: a bottom fade gradient
    over the `line-clamp-2`'d description (`.card-desc-fade`, `considered.html:128-135`), the same
    idiom `RESEARCH.md` names from T3's `ProposedPlanCard`, applied only on hover so it doesn't cost
    anything at rest. `restrained`: unchanged — the plain clamp, no fade — since a gradient overlay
    is itself a small piece of "expressive" texture relative to this variant's own degree.

**Two further bugs, found beyond `RESEARCH.md` itself, by building and by looking rather than by
research:**

- **Finding 11 — a real, present-tense icon-mapping bug in the shipped product**, found while
  building the mock in iteration 14 (P2), not flagged by P1's research pass. `help_circle`,
  `alert_triangle`, `filter_alt`, and `expand_less` are the names `TaskCard.tsx`'s blocked box and
  Stalled badge, and `TasksBoard.tsx`'s requirement-filter banner and rejected-section chevron,
  actually pass to `Icon` — but none of the four exists in `Icon.tsx`'s `ICONS` map (only `help`,
  `warning`, `filter_list`, and `expand_more` do). `Icon()`'s unmapped-name fallback renders `null`,
  so today, in the real product, all four render nothing: the blocked box has no icon, the Stalled
  badge has no icon (the neighbouring Prerequisite-regressed badge does — it correctly uses
  `warning`), the requirement-filter banner has no icon, and the rejected-section toggle has no
  chevron in either state. Both mocks use the correct, already-mapped icon names at every one of
  these four call sites — not a new icon, a corrected one.
- **The flag-glyph legibility bug, found in P3 by screenshotting and reading, not from the source.**
  `FLAG`/`FLAG_SM` — the shape built for finding 1's `high`/`critical` disambiguation — was
  originally a thin `stroke-width: 2.4` outline at 9×9px. Rendered, it read as the letter "P," not a
  flag, in both themes, at every call site (the finding-1 before/after table, every `high`/`critical`
  card badge, the states-strip). Comparing against the card's other small glyphs at similar sizes
  (`WARN_SM` at 11px, `HELP` at 15px, both thin-stroke, both legible) isolated the cause as the
  flag's specific geometry — a thin pole plus a thin hooked pennant collapses into noise at a size a
  closed triangle or circle survives — not size alone. Fixed by rebuilding `FLAG` as a filled shape
  (`fill="currentColor"`, a solid pole rect + solid pennant path) and bumping both call sites from
  9px to 11px to match `WARN_SM`'s already-confirmed-legible size. Re-screenshotted, cropped, and
  zoomed 4–5× on the actual on-card size in both themes after the fix (P3, then reconfirmed fresh in
  P4 with new captures) — reads clearly as a flag everywhere it appears, no regression.

## What was rejected, and under which clause

- **A third "expressive" variant.** Rejected before being built, same reasoning as S1: two variants
  ("restrained"/"considered") already carry a clear degree difference on this screen, and a third
  reading would mean inventing decoration with no further finding to justify it — **clause 7**'s
  "texture means considered detail, not literal texture" and **clause 5** ("the same application,
  improved").
- **Building drag-and-drop for real.** Finding 5 is a missing feature; `pre_authorised` says mock it,
  not implement it. Illustrated in `considered` only, not built as working interaction in either
  variant.
- **Any new hue for the priority scale.** `PRIORITY_STYLES` in both variants reuses tokens already on
  the same card for other signals (neutral, amber, red) rather than a fifth colour — validated
  directly against `Badge.tsx`'s existing `tone()` recipe before building, not approximated.
  **Clause 1/2.**
- **Icon-heavy badge rows on every field.** Finding 6 was addressed narrowly (the priority flag,
  reusing existing icon slots) rather than adding an icon to every pill on the card — a fuller
  icon-everywhere treatment would have cost density on a seven-column board with four-plus badges
  per card already. **Clause 6.**

## The judgement call from P3/P4

**`restrained`'s glyph-free priority dot turned out to be the safer choice at this information
density, not just a smaller version of `considered`'s flag.** This wasn't the plan going in — the
flag was built as the fuller, more differentiated treatment and only failed legibility under actual
render-and-read scrutiny in P3. `restrained` never carried this risk in the first place, because a
plain colour dot has no stroke geometry to collapse at small sizes. Worth stating plainly here rather
than only in the log: on a board this dense, where every card already carries four-plus badges at
9–11px, a solid-colour signal is more robust by construction than a glyph-based one, independent of
whether the specific glyph chosen happens to render legibly. If a real implementation picks between
these two degrees, that robustness — not just restraint as a stylistic preference — is a reason to
lean toward the dot.

## What's already good and was left alone

Carried forward verbatim from `RESEARCH.md`'s P1 findings, confirmed still true after building and
after two full render-and-read passes: the purple-for-blocked / amber-for-stalled distinction
(deliberately opposite signals, never recoloured or merged); the "Stalled" wording and its amber tone
(already renamed once after a direct operator complaint, not touched again); the live-pulse ring
(`task-live-pulse`, design D12 — already respects `prefers-reduced-motion`, already never the sole
carrier of the "running" fact; both mocks extend the same idiom rather than inventing a second motion
language); the sticky column headers and their `-12px` offset hack (fixed in direct response to an
operator complaint about losing column context while scrolling — kept working in both mocks); the
centred-modal drawer geometry (reversed from an earlier side-panel design on the operator's own
explicit 2026-08-17 direction — not reintroduced); `blocked` folded into "In Progress" rather than
given its own column (R3); and F4/F5's requirement-chip and card-is-a-summary/drawer-is-the-work-
surface split. None of these were touched — both mocks change appearance and feedback only, never the
information architecture those decisions protect.
