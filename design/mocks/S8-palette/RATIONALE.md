# S8-palette rationale — the command palette

Fourth and last `S8` overflow sub-screen (jobs, agents, logs all closed 4/4 first, per
`pre_authorised`'s "do not start a later S8 sub-screen while an earlier one has unfinished
passes"). Four passes (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this document).

## The component is thin styling over a capable library, not a custom build

`hub/ui/src/components/palette/CommandPalette.tsx` wraps [`cmdk`](https://cmdk.paco.me/)
(`Command.Dialog`), styled in `index.css:324-372` under a comment stating the intent — *"composes
with the app's own tokens rather than a competing look"* — that intent is sound; what exists under
it is minimal, not wrong. Four flat groups (Agents, Tasks, Spec documents, Conversations), each row
one icon plus one line of text, nothing else. `RESEARCH.md` reads the component in full including
its comments (the truncated `searchText` on conversation rows is a documented fix for a real
ranking bug, left alone) before naming eight concrete gaps.

## Eight findings, five in scope for styling, one flagged as a genuine missing feature

Full detail and sourcing in `RESEARCH.md`. In scope, refined using only existing tokens:

1. **No keyboard-hint footer** — the one moment a keyboard-first surface has a user's full
   attention and says nothing about arrow keys / Enter / Esc.
2. **No open/close transition** — every other overlay in the app uses `--dur-fast`/`--dur-base`
   with the shared easing; this dialog snapped in instantly.
3. **No match highlighting** — cmdk filters and ranks internally but nothing marked *why* a row
   matched.
4. **Selection had no motion and no secondary cue** — an instant `--surface-2` swap with nothing
   to distinguish keyboard-selection from mouse-hover, which the T3 Code reference explicitly
   avoids by design (single `isActive` treatment, not two competing highlight sources).
5. **Rows carried no secondary information** — a task row showed only its title (no status), a
   conversation row showed no speaker attribution, every other list surface in the app
   (`TaskCard`, `ConversationView`) surfaces at least one secondary attribute.
6. **No colour coding at all** — notably no use of the app's own 8-colour `--agent-*` scale for
   the Agents group, where it is free identity information already computed elsewhere, not
   decoration.
8. **Empty state was a dead end** — "No matches." with no suggestion of what's searchable.

Finding 7 (no shown shortcut for the palette's own opening key) was named lower priority in
`RESEARCH.md` and left out of both mocks — the palette has no assignable per-item actions today, so
there is nothing for a resolved-shortcut badge to show; inventing one would be decoration, not
information.

**Finding 6's colour scale is reuse, not invention** — each Agent row wears *that agent's own*
already-assigned `--agent-N` colour (computed elsewhere in the app for the same identity), never a
new single hue for the whole group. A single-hue-per-group scheme was considered and rejected before
building anything: it would map a colour to a group boundary that carries no such meaning today,
failing clause 1 (colour must already carry the meaning it's given).

## Two variants, both closing the same seven findings via degree

`restrained.html` closes findings 1, 3, 4, 8 — footer hint chips, `<mark>`-based highlighting
(weight/foreground strength only, no highlighter colour, per the T3 Code source), hover now
visually distinct from keyboard-selection, a real scale+fade open/close transition respecting
`prefers-reduced-motion`, and a named empty state. `considered.html` adds findings 5 and 6 on top —
per-row agent identity colour, a secondary information line on every row (status chip / speaker +
highlighted snippet / doc phase), and trailing content (timestamp / status chip) replacing empty
space. Both reuse the existing `[cmdk-*]` attribute-selector hooks straight from `index.css` rather
than re-styling from scratch, so token fidelity is exact by construction — the same reuse pattern
`S8-logs` used for `.btn`/`.lchip`.

**Recent items on the empty query** — `considered.html` also mocks a "recent items" section shown
before any typing, sourced from Mobbin and Destiner's notes on command-palette design. This is a
genuine missing **feature** (the app tracks no "recently opened" list today), not a styling gap —
flagged here per the loop's pre-authorised allowance, mocked so the shape is visible, explicitly
*not* implemented.

## What was rejected, and under which clause

Checked against `IDENTITY.md`'s rejection test in `RESEARCH.md` before building anything:

- A new colour hue, a border/ring/glow beyond the existing `--ring` selection accent, or restyling
  cmdk's structure into a different visual language (full-screen takeover, sidebar-style palette) —
  **rejected under clause 5**, no jump in design, refinement only.
- A per-item resolved-keyboard-shortcut badge (finding 7) — not rejected on identity grounds, just
  out of scope: there is nothing true to show it for yet, so it would be invented content rather
  than surfaced information.

Nothing else from `RESEARCH.md`'s findings failed validation — the footer, highlighting, hover
state, transition, secondary lines, trailing content and agent colour all trace to existing tokens,
existing computed identity, or direct precedent from an earlier screen (`_system/controls.html`'s
state vocabulary, `S8-logs`'s reuse-not-restyle approach).

## P3 — one real bug found and fixed, plus a density trade-off stated rather than buried

The adversarial pass (both variants, both themes, plus a 480px viewport check) found and fixed one
real defect: at 480px, `considered.html`'s palette overflowed its own demo `.stage` container
(measured `paletteWidth` 543px inside a 424px `.stage`) because `.stage-narrow` — a flex item with
no `width`/`min-width: 0` of its own — let long unwrapped row-title/row-sub text force a wide
min-content box instead of shrinking into the existing ellipsis rules. Fixed with one line,
`.stage-narrow { min-width: 0; width: 100% }`, confirmed by DOM re-measurement
(`paletteWidth` 543px → 365px) and re-screenshots at 480px (both themes, clean) and 1440px
(pixel-identical to before the fix). `restrained.html` never hit this — it has no long unwrapped
secondary-line text to trigger it.

**Density (clause 6) was measured, not assumed.** At the production
`.command-palette [cmdk-list] { max-height: min(60vh, 420px) }` cap, `restrained.html`'s
single-line rows (~34px) fit ~12 rows; `considered.html`'s two-line rows (~49px where a row carries
a secondary line, ~35px where it doesn't) fit ~9. Row *count* per screenful genuinely drops for
`considered.html`'s richer rows, even though information *per row* rises. Stated here plainly
rather than asserted away: whether nine richer rows read as "at least as much information per
screen" as twelve plainer ones is a judgement call for whoever picks a variant, not a settled fact —
`restrained.html` is the variant to prefer if row count at a glance matters more than per-row
context, `considered.html` if the reverse.

## P4 — second look

A fresh read of all four captures (both variants, both themes) after the P3 fix found nothing new:
every row type (resting, hovered, keyboard-selected, focus-visible, and — `considered.html` only —
disabled) renders legibly in both themes, the recent-items feature note reads clearly as a note and
not shipped behaviour, and the same four groups and same underlying information as today's palette
are still present in both variants — no row lost, per clause 5's "refinement, not a jump."
