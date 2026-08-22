# U0a research — motion, elevation, interaction states

Read first, per protocol: `design/IDENTITY.md` in full (the rejection test governs every choice
below), then the current product — `hub/ui/src/index.css` (860 lines, all 124 tokens),
`buttonVariants.ts`, `TaskCard.tsx`, `EmptyState.tsx`, and the `AgentTimeline.tsx` comment on the
removed blue-tinted operator bubble.

## What the current product already has, precisely

Not a guess — read from the files above:

- Five surface steps (`--bg → --rail → --surface → --surface-2 → --surface-3`), white-alpha
  borders (`--border` 0.07, `--border-hi` 0.13, `--border-region` 0.05), and two lighting tokens
  already defined for raised controls: `--lift-hi` (inset top highlight, "lit from above at rest")
  and `--press-lo` (inset shadow, "inverts while pressed") — `buttonVariants.ts`'s `primary` variant
  is the one place that already does this correctly: `shadow-[inset_0_1px_0_var(--lift-hi),0_1px_3px_rgb(0_0_0/0.24)]`
  at rest, `active:shadow-[inset_0_1px_0_var(--press-lo)]` pressed, elevation shadow removed.
- Three row-state tokens (`--row-hover` 8/11/7%, `--row-active`, `--row-selected`) already
  color-mixed against `--text` per theme, cited in `index.css` as derived from T3's own
  sidebar-row hover/active/selected ratios re-expressed against AgentWeave's palette — so the T3
  reference for row interaction density is already incorporated at the token level, not something
  this pass needs to re-derive.
- Three durations (`--dur-fast` 150ms, `--dur-base` 250ms, `--dur-slow` 500ms) and one easing
  (`cubic-bezier(0.16, 1, 0.3, 1)`, a soft expo-out) — but IDENTITY.md's own count says only 9
  component sites reference them against 44 ad-hoc `transition`/`animate-` declarations.
- `EmptyState.tsx`: icon in a 64px `--surface-3` circle, title, optional description. No motion,
  no variation by context — the same treatment whether the empty board is "no tasks yet" or "no
  results for this filter", which are different situations for the operator.
- `TaskCard.tsx` demonstrates two things worth generalising: (1) a card border that changes colour
  on hover via manual `onMouseEnter`/`onMouseLeave` rather than CSS `:hover` (because the resting
  colour is conditional on `isBlocked`) — the mock should show the CSS-only version as the default
  case and note the manual-JS version only applies when the resting state itself is conditional;
  (2) `task-live-pulse`, the one already-shipped considered animation in the product: a box-shadow
  pulse gated behind a JS `prefers-reduced-motion` check *and* the CSS media query, "so reduced
  motion loses only the pulsing, never the cue" (the static ring persists). That's the correct
  reduced-motion pattern and the mock reuses it rather than inventing a new one.
- No skeleton loading anywhere in the codebase (`grep -r skeleton hub/ui/src` — zero matches).
  Every loading state today is either a spinner or nothing.

## External research

**Elevation in dark UIs is communicated by lighter surfaces, not shadows** — shadows barely read
against a near-black ground plane, which is exactly what `TaskCard.tsx`'s own `box-shadow` note
about "no outer drop shadow... could not read as a shadow, only as a dark halo" already discovered
by hand for the composer. The general guidance (dark-mode design-system surveys, 2026) confirms
this as the standard approach, not a local workaround: raise surfaces by shade for depth, reserve
shadow for the inset lighting cues (`--lift-hi`/`--press-lo`) that read as physical press, not for
drop shadows that don't read on a dark ground.
[Dark Mode Design Systems](https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/) ·
[Post #4 (Design System Chronicles)](https://www.fourzerothree.in/p/scalable-accessible-dark-mode)

**Motion durations**: 100–200ms for direct-feedback interactions (button press, hover, small state
flips), 200–400ms for a state or view transition (toggle, modal, disclosure), longer only for
multi-step sequences. AgentWeave's three-step scale (150/250/500ms) already brackets this correctly
— `--dur-fast` for the direct-feedback tier, `--dur-base` for transitions, `--dur-slow` reserved for
things that should read as deliberately unhurried (the live-pulse keyframe already uses 2.4s, well
outside the token scale, correctly — a slow ambient loop isn't a state transition).
[Micro-Interactions in Motion Design](https://blog.pixelfreestudio.com/best-practices-for-implementing-micro-interactions-in-motion-design/) ·
[Atlassian Motion Foundations](https://atlassian.design/foundations/motion)

**Easing**: ease-out for entrances, ease-in for exits, ease-in-out for symmetric state changes.
`--ease` (`cubic-bezier(0.16, 1, 0.3, 1)`) is already an expo-out — correct for the entrances and
hovers that dominate this UI's motion surface (things appearing, rows lighting up), and the mock
uses the same single easing throughout rather than introducing a second curve, since IDENTITY.md's
clause 3 fixes "every easing is `--ease`."

**Skeleton over spinner for content loading**: a skeleton that mirrors the shape of what's arriving
reduces the perceived wait and avoids the blank-then-pop flash a spinner produces; a spinner remains
correct for a short, shapeless action (submitting, saving) rather than content population.
IDENTITY.md already directs this ("Loading states: skeletons that match the shape of what arrives,
not spinners"), and this is the mainstream recommendation, not a stretch.
[Skeleton Screens vs Loading Spinners](https://www.onething.design/post/skeleton-screens-vs-loading-spinners) ·
[Loading – Carbon Design System](https://carbondesignsystem.com/patterns/loading-pattern/)

**Empty states**: dashboard/analytics guidance for 2026 favours a plain, textual empty state with a
single icon over an illustration — illustrations cost vertical space and this is an
information-dense operator tool (IDENTITY.md clause 6). `EmptyState.tsx`'s existing shape (icon
circle, title, description) is therefore the right shape already; what's missing is that it never
distinguishes "genuinely nothing exists yet" from "your filter matched nothing" or "still loading",
three situations the operator currently sees identically or not at all.
[Loading, empty and error states](https://design-system.agriculture.gov.au/patterns/loading-error-empty-states)

## T3 Code — design reference only

`--row-hover`/`--row-active`/`--row-selected`'s ratios are already sourced from T3's sidebar-row
treatment per the comment in `index.css` — that transfer already happened in an earlier pass, so
this system pass does not re-derive it. `384` sourcemaps are present at the path recorded in
STATE.json; spot-checked for skeleton-loading patterns (three files reference a "skeleton" symbol
in their original source), but T3's stack differs enough that its skeleton implementation is not a
structure worth reading closely for a static-CSS mock — the actionable takeaway is the same one the
general research already gave (shape-matched placeholders, not a spinner), so nothing further is
quoted or copied from T3 for this pass, matching IDENTITY.md's "structure transfers and
implementation does not."

## What's missing from the current product, concretely

1. **Elevation isn't a named scale.** Surfaces exist (`--bg` through `--surface-3`) but nothing
   documents *when* to reach for which step, or how the two lighting tokens (`--lift-hi`,
   `--press-lo`) compose with them. `foundations.html` names four elevation tiers built from what
   already exists.
2. **Focus-visible is inconsistent in weight.** Some controls (`buttonVariants`, `.row-item`) carry
   a two-layer ring (`--bg` gap + `--ring`); most ad-hoc buttons don't get any explicit
   focus-visible treatment beyond the generic `button:not(...)` base rule. The mock shows the ring
   as one demonstrated pattern, not a new one.
3. **Disabled has one visual idiom** (`opacity: 0.64`, `pointer-events: none`) applied in exactly
   two places (`buttonVariants`, the generic button base rule) and nowhere else — rows, chips and
   cards have no disabled treatment at all today.
4. **Loading has no shape-matched pattern anywhere.** This is the single largest gap the mock needs
   to fill: skeleton rows for a list, a skeleton card for `TaskCard`'s shape, and a skeleton line
   for inline text — all built from `--surface-3`/`--border` with a slow shimmer sweep gated behind
   `prefers-reduced-motion`, following `task-live-pulse`'s existing reduced-motion pattern.
5. **Selected vs active vs hover read almost identically** in places that aren't `.row-item` (which
   already does this correctly) — the mock generalises the three-state row treatment to a card
   context (`TaskCard`) and a list-item context, since those are the two places IDENTITY.md's
   "Interaction states" section names as under-designed.
6. **Empty states don't vary by cause.** The mock adds two more empty-state variants next to the
   existing shape: "still loading" (a skeleton, not this component at all — see above) and
   "no match for this filter" (same icon-circle shape, a lighter tone and a clear-filter action,
   distinguishing it from "nothing exists yet" without changing the shape IDENTITY.md protects).

## Validated against the rejection test

Everything above stays inside the eight fixed constraints: no new hue, `--blue` untouched (used
only for focus rings and the existing `--agent-1`/`--ring` roles, never as a fill), the radius scale
untouched, no new type, `Icon`/lucide only, no illustration in the empty-state variants (density),
and no glass/gradient/skeuomorphism — the skeleton shimmer is a `color-mix` sweep against the
existing `--surface-3`/`--border-hi`, not a gradient surface treatment. Nothing here reads as a
different product; it is the existing five-surface, three-duration, one-easing system, named and
applied to the states IDENTITY.md lists as free.

## U0b research — button taxonomy, form controls, colour coding

Read first: `buttonVariants.ts` in full (its own comments on the three control rules — permanent
transparent border, padding subtracting border thickness, raised-lit-from-above/inverts-under-press
— already state the taxonomy's mechanics precisely), `RowMenu.tsx` (the existing menu pattern —
Radix `DropdownMenu`, opened by a persistent-on-hover three-dot trigger, never right-click, per an
explicit 2026-08-08 operator quote preserved in its comment), `Badge.tsx`/`StatusBadge` (status and
variant colour tables, `tone()` deriving `bg`/`border` from one token via `tint()` so text and
container can never drift apart), and every `<select>`/`<input type=checkbox>` call site
(`AgentSettingsControls.tsx`, `JobForm.tsx`, `ProjectSettingsPanel.tsx`) — all native, unstyled
beyond a background/border/radius on the `<select>` box itself; the checkbox is the bare UA
control with no themed replacement anywhere, and no toggle/switch component exists in the codebase
at all (`grep -rn "role=\"switch\"" hub/ui/src` — zero matches).

**What the current product's button taxonomy already is, precisely.** Four variants —
`primary` (filled, lit-from-above, one per view), `outline` (bounded, unfilled, the "secondary"
role under a different name), `ghost` (blends in until touched, the "tertiary" role), `destructive`
(danger-coloured, same shape rules as the other three) — cross eight sizes: `xs/sm/md/lg` (text
buttons, 28–40px tall) and `icon/icon-sm/icon-xs` (square, 28–36px) plus `pill` (content-sized, no
built-in radius so a rounded-full caller does not have to fight specificity). `controls.html`
demonstrates the full 4×8 matrix once, then each variant's five states (rest/hover/press/
focus-visible/disabled) once at a representative size — repeating five states across all eight
sizes would be redundant since the state *treatment* does not vary by size, only the size does.

**External research confirms the existing four-variant taxonomy already matches convention.**
Design-system guidance converges on primary (single, filled, the one action a screen wants taken) /
secondary (outlined, common but not primary) / tertiary (least emphasis, blends into the layout) /
destructive (danger-coloured, kept away from constructive actions, spaced or dividing rather than
adjacent) — exactly `primary`/`outline`/`ghost`/`destructive` under AgentWeave's own naming. Nothing
here calls for a fifth variant; the gap is that only 9 sites reference the motion tokens the
variants already define, matching U0a's finding, not a missing variant.
[Button hierarchy (primary/secondary/tertiary)](https://subux.pro/guides/article/button-hierarchy-primary-secondary-tertiary) ·
[Design System Breakdown: Button](https://clipcontent.substack.com/p/design-system-breakdown-button-22-11-08)

**Colour coding: semantic tokens are functional labels, not decoration**, and the mainstream
guidance is to keep the set small (success/warning/danger/info) and apply it by *meaning*, never by
preference — exactly what `StatusBadge`'s `STATUS_STYLES` table already does for task status. The
one place today's code departs from IDENTITY.md's own rule: `Badge.tsx`'s `INFO = tone('var(--blue)')`
colours `in_progress` with `--blue`, and IDENTITY.md clause 2 reserves `--blue` for focus and
selection only. This mock does not carry that choice forward — `controls.html`'s colour-coding
system uses only `--green`/`--amber`/`--red`/`--purple` for status/category and keeps `--blue` out
of the status vocabulary entirely, matching the identity rather than the one existing outlier.
Flagging it here rather than fixing `Badge.tsx` itself, which is source, not a mock, and outside
this iteration's scope.
[Semantic Colors in UI/UX Design](https://medium.com/@zaimasri92/semantic-colors-in-ui-ux-design-a-beginners-guide-to-functional-color-systems-cc51cf79ac5a) ·
[Designing Semantic Color Systems for UI Clarity](https://uxdictionary.io/article/designing-semantic-color-systems-for-ui-clarity)

**`--purple` is already a category colour, not a status one**, confirmed across every existing call
site: task-kind events (`EventRow.tsx`, `LogLine.tsx`), the message-card category chip
(`MessageCard.tsx`), and every file-type icon in `fileIcons.ts` (markdown/xml/html/css/images all
render `--purple` regardless of whether anything succeeded or failed). `controls.html`'s
colour-coding rules keep this distinction explicit: green/amber/red answer "how did this go",
purple answers "what kind of thing is this" — the two questions never share a colour, and the
8-colour `--agent-1..8` scale answers a third question ("whose is this") that also never borrows
from the other two.

**Form controls.** No custom checkbox, radio, toggle/switch, or styled `<select>` exists anywhere in
the codebase today — every instance is the bare UA control, which is why they were not already
covered by U0a (that pass generalised existing patterns; these have no existing pattern to
generalise). `controls.html` builds all four from the same primitives U0a already established: the
`.demo-input`-style border/background/focus-ring recipe for text/select boxes, `--row-hover`-style
neutral fills for hover, and (new, argued below) `--blue` for a checkbox/toggle's *checked* fill —
defensible under clause 2 as literally "selection," the same justification `--ring`/`--blue` already
carries for a selected row or focused control, and nowhere used as a status or brand colour.
[Semantic Colors in UI/UX Design](https://medium.com/@zaimasri92/semantic-colors-in-ui-ux-design-a-beginners-guide-to-functional-color-systems-cc51cf79ac5a)

## Validated against the rejection test (U0b)

Same eight constraints as U0a, rechecked for this pass's specific additions: the checkbox/toggle
checked-fill use of `--blue` is selection, not a new brand or status role, so clause 2 holds: colour
coding uses only `--green`/`--amber`/`--red`/`--purple` plus the existing `--agent-1..8` scale, no
ninth colour introduced; every control's radius derives from `--radius-sm/md/lg`; every duration is
`--dur-fast` (all control state changes are direct feedback, never `--base`/`--slow`); the styled
`<select>`'s chevron is an inline `Icon`-style SVG, not a new icon source; density is preserved —
control heights match the existing `buttonVariants` size scale (28/32/36/40px) rather than growing
to accommodate the new visual treatment.
