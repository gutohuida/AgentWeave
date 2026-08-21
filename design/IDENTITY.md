# AgentWeave visual identity — the refinement contract

**Read this before every design iteration. It is the boundary, not a suggestion.**

Operator directive, 2026-08-21, verbatim:

> "You can create variants but do not change the overall tone of the app. I want to fines things
> not a complete jump in design. Not going from this to material design for example."

This document exists because an unattended agent researching "UI patterns" will drift toward
whatever it reads about. Material, shadcn defaults, Fluent, glassmorphism — each is internally
coherent and each would destroy this product's identity. The work is **refinement within the
existing language**, and the test below is how a mock proves it stayed inside.

## What the identity actually is

Measured from `hub/ui/src/index.css` (124 tokens, full light/dark parity), not asserted:

- **Near-black neutral charcoal.** Dark surfaces step `#0a0a0b → #101012 → #151518 → #1d1d21 →
  #26262b`. There is no navy, no warm grey, no tinted background. A code comment in
  `AgentTimeline.tsx` records a blue-tinted bubble being removed for reading "as leftover navy
  against the charcoal palette" — that is the standard.
- **Borders are white-alpha, not grey.** `rgba(255,255,255,0.07)` and `0.13`. Structure is
  suggested, not drawn.
- **Chromatic colour is reserved, never decorative.** `--blue` (`#7c8cff`) is the single interface
  accent and belongs to **focus and selection only**. `--accent` is deliberately *neutral*
  (`rgba(255,255,255,0.055)`), not a hue.
- **Semantic colour is earned.** green / amber / red carry state. purple is a category, not a mood.
- **Agent identity is an 8-colour scale** (`--agent-1..8`) with `-tint` and `-border` derivations
  in oklab. Colour reinforces identity and never carries it alone — the name is always present too.
- **Radius is one scale** from a single `--radius: 10px`: `sm 6 · md 8 · lg 10 · xl 14 ·
  content 24`.
- **Motion is already defined**: `--dur-fast 150ms · --dur-base 250ms · --dur-slow 500ms`, easing
  `cubic-bezier(0.16, 1, 0.3, 1)` — a soft expo-out.

## The actual problem, measured

The system is **under-applied**, not missing:

| | count |
|---|---|
| motion tokens used across all components | **9** |
| ad-hoc `transition` / `animate-` in components | **44** |
| hardcoded hex in components | **6** (token discipline is already good) |

So most of the "no nice feeling" is transitions that never got the scale, states that were never
designed, and empty/loading cases nobody dressed. **That is refinement work.** Almost nothing here
needs a new visual language; it needs the existing one applied consistently and with more care.

## Fixed — a mock that changes any of these is rejected

1. **The palette.** No new hues. No changing existing token values. Both themes stay in parity.
2. **`--blue` stays focus/selection.** It does not become a brand colour, a button fill, or an
   accent wash.
3. **The radius scale.** Derive from `--radius`; do not introduce a second geometry (no pill
   buttons beside 10px cards, no sharp corners as a "style").
4. **Type.** The existing family and scale. No display faces, no new weights as decoration.
5. **Icons.** lucide via the `Icon` wrapper, plus `simple-icons` brand marks through
   `brand:<key>`. **No third icon source, and never a second icon font** — a webfont that blocked
   paint on a CDN request is why the Material Symbols font was removed.
6. **Density.** This is an information-dense operator tool. Refinement must not cost rows on
   screen; a redesign that halves what fits is a regression however handsome it is.
7. **Flat-neutral character.** No glass, no heavy drop shadows, no gradients as surface treatment,
   no skeuomorphic texture. "Texture" here means *considered detail* — border weight, spacing
   rhythm, state feedback — not literal texture.

## Free — this is where the work is

- **Applying the motion scale** to the 44 places that transition ad hoc, and adding motion where
  there is none. Respect `prefers-reduced-motion`.
- **Interaction states**: hover, press, focus-visible, disabled, loading, selected. `--row-hover`,
  `--row-active`, `--row-selected`, `--lift-hi`, `--press-lo` already exist and are barely used.
- **Elevation**: a considered layering scale built from the existing surface steps and borders.
- **Empty states** — currently the plainest thing in the product.
- **Loading states**: skeletons that match the shape of what arrives, not spinners.
- **Spacing rhythm and alignment**: the difference between "boxes with text" and a designed card is
  usually optical alignment and a consistent vertical rhythm.
- **Hierarchy**: what is primary on each surface, and what recedes.
- **Micro-detail**: border-weight contrast, divider treatment, focus ring quality, truncation and
  overflow behaviour, number alignment (`tabular-nums` is already used in places).
- **Button and control vocabulary**: how many kinds exist, what each is for, and their states.
  Today this is inconsistent — that inconsistency is in scope to fix, within the palette above.
- **Colour *coding*** — using the existing semantic and agent scales more systematically. This is
  about applying colour with rules, not adding colours.

## The rejection test

A mock passes only if **all** of these are true. The validation pass applies it and rejects
otherwise, stating which clause failed.

1. Every colour resolves to an existing token in `hub/ui/src/index.css`. No literal hex except
   where a token already contains one.
2. Rendered in both themes, and legible in both. A brand or semantic colour that fails contrast on
   either background falls back to a palette token — see `brandHex`, which returns null for exactly
   this reason after Markdown/JSON/Rust rendered invisible in dark mode.
3. Every duration is `--dur-fast|base|slow` and every easing is `--ease`.
4. Every radius derives from `--radius`.
5. Placed beside a screenshot of the current screen, a reader would call it **the same application,
   improved** — not a redesign. If it reads as a different product, it failed, however good it is.
6. It shows at least as much information per screen as the original.
7. Interactive states are demonstrated, not just the resting state.

Clause 5 is the operator's directive and outranks the others. A mock that is beautiful and fails
clause 5 is a failed mock.

## Variants

Variants explore **degree of refinement**, never different design languages. A useful set:

- **restrained** — the smallest change that fixes the plainness
- **considered** — full application of states, motion and rhythm
- **expressive** — the most detail this identity can carry without becoming a different product

All three must pass the rejection test. "Expressive" is the ceiling of *this* language, not a
departure from it.

## Reference material

- **T3 Code** — the operator's endorsed reference, unminified source recoverable from sourcemaps at
  `C:\Users\huida\AppData\Local\Programs\t3code\resources\app.asar.unpacked\apps\server\dist\client\assets\*.js.map`
  (384 maps present, verified 2026-08-21). **Design reference only**: study structure and
  interaction patterns, do not copy code, do not commit it, do not quote it at length in a tracked
  document. Its stack differs, so structure transfers and implementation does not.
- **The product itself.** Read the current component before redesigning it. Several already carry
  the reasoning for why they look as they do, in comments — `AgentTimeline.tsx`'s note on the
  operator bubble being deliberately neutral is the clearest example, and a mock that re-tints it
  would be undoing a decision, not improving it.
