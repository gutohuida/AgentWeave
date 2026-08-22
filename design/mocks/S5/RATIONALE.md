# S5 rationale — the rendered spec documents

Four passes (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this document). Per
`decisions_for_user` D-spec-render: this screen is `hub/hub/spec_render.py`'s own generated
`<body>` — server-side Python, not a React component. A mock is HTML either way, so the *process*
was unchanged, but **implementing anything found here later touches Python string-building
(`_STYLE`, `_requirements()`, `_acceptance_table()`, etc.), not a component file** — a different
kind of change from every other screen in this queue, and this is the plain statement of that
difference D-spec-render asked for.

## Two scoped-clause resolutions, decided at P1/P2, still governing at P4

`IDENTITY.md`'s rejection test was written assuming every mock can reach `hub/ui/src/index.css`.
This screen cannot: `SpecFrame.tsx` renders it in a sandboxed iframe (`sandbox="allow-scripts"`,
no `allow-same-origin`) with `srcDoc`, and `spec_render.py`'s `_STYLE` is deliberately its own,
separate token namespace — `hubTheme.ts`'s own comment states its four semantic hues
(`--aw-accent`/`--aw-warn`/`--aw-ok` plus `color-scheme`) are "not the Hub's to recolour."

- **Clause 1 (colour)**, resolved at P1: every colour in both mocks resolves to a token already
  declared in `spec_render.py`'s own `_STYLE` block, not the Hub's — same rule (no invented hue,
  no arbitrary hex), applied to this document's actual, different vocabulary.
- **Clause 3 (motion)**, resolved at P2, needed only by `considered.html`: added
  `--aw-dur-fast`/`--aw-dur-base`/`--aw-ease` to this document's own `_STYLE`, value-identical to
  the Hub's `--dur-fast`/`--dur-base`/`--ease` (150ms/250ms, `cubic-bezier(0.16,1,0.3,1)`) — a
  mirror of the existing scale, not an invented one, gated the same way the Hub's own
  `prefers-reduced-motion` handling is (`--aw-dur-* : 0ms` under the media query).

Both resolutions are stated in each file's own header comment, not only here, so a reader who
opens `considered.html` cold sees the reasoning without needing this document.

## The decision P1 left open, closed at P2: one file or two?

`RESEARCH.md` asked whether to build a fourth file demonstrating the standalone
(OS-preference-driven) theme path separately from the Hub-embedded (`data-theme`-forced) path.
Decided **no** — both mocks already carry all three cascade layers a real opening of this document
would hit: `:root` (light default), `@media (prefers-color-scheme: dark)` (the standalone path,
live whenever the review toolbar hasn't forced a theme), and `:root[data-theme="light"|"dark"]`
(the Hub-embedded path, forced exactly the way `hubTheme.ts` forces it). A fourth file would
duplicate all this content for zero new token combination.

## Research → ten findings → ten fixes

Full sourcing lives in `RESEARCH.md`: `spec_render.py` read in full (533 lines, including its own
design notes on anchor-stability and "no navigation script here, the shell owns it," treated as
binding constraints, not decoration); `SpecFrame.tsx`, `hubTheme.ts`, `SpecDocumentPanel.tsx` read
in full to confirm what is a *different, already-styled* React surface out of S5's scope (the
shell's breadcrumb, phase/coverage bars, and 200px outline sidebar) versus what constrains the mock
anyway (no sticky TOC inside the document — the shell already owns one; the three-layer cascade
must stay intact); a real generated document,
`spec/capabilities/task-lifecycle-governance/spec.html` (1204 lines, 32 requirements, a 110-row
table), read in full rather than sampled, specifically for density; the legacy
`.agents/skills/aw-spec-apply/html-spec-conventions.md` read as design reference only (per
`CLAUDE.md`, `aw-*` skills are product source to implement, not a workflow to run); and all 384 T3
Code sourcemaps grepped for a comparable surface — the only hit was a syntax-highlighting grammar
file, confirming **T3 Code has no document-authority screen at all**, unlike every other screen in
this queue, so external WebSearch research (API-docs scannability, long-document reading UX,
badge/status-pill design — three sources, all cited in `RESEARCH.md`) carried correspondingly more
weight this pass.

1. **Modal MUST/SHOULD/MAY was colour-on-text**, the weakest signal in the document for what should
   be its strongest one. Both variants render it as a filled pill (`color-mix` of the existing tone
   token over `--bg` — no new hue, only its fill added), matching the legacy convention's own
   pill idiom, a legitimate steal *within* `spec_render.py`'s existing tokens.
2. **Rationale prose regularly outweighs the requirement it explains** (FR-21 in the sampled
   document runs roughly triple the length of FR-21 itself) yet rendered with the same `<p>` tag,
   differing only by a muted colour. Both variants add a small-caps "Why" label and a left rule,
   subordinating it visually instead of relying on colour alone.
3. **108 of 110 acceptance rows have an empty Given cell** (confirmed against the document's own
   `Limits` section, which names this as a known translation gap: `scenarios-state-no-starting-state`),
   yet the column claimed equal width regardless. Both variants narrow it via `<colgroup>` and
   render a muted em dash instead of blank space claiming width.
4. **No local sense of position** inside a 32-requirement section the shell's outline sidebar only
   indexes at section granularity. A CSS-counter-only "Requirement N of 10" label — no script,
   since `spec_render.py` already knows `len(payload.requirements)` at render time.
5. **No copy-anchor affordance**, despite anchor stability being a real, stated guarantee of the
   renderer. A copy-link button beside each requirement's id, using a small inert clipboard
   script — confirmed this does **not** cross the renderer's stated no-navigation-script boundary,
   since it copies to the clipboard and never intercepts a click or adds same-document navigation.
6. **Tasks rendered as bare trailing muted text** for their `satisfies` links. Both variants render
   tasks as bordered rows with `satisfies` chips, matching how Requirements/Acceptance already
   present the same relationship.
7. **Map children ran as one unbroken list** with no visual separation between siblings. A divider
   between `.aw-map-item`s in both variants; `considered.html` adds a hover fill.
8. **The in-frame breadcrumb was bare adjacent links.** A chevron separator in both variants — full
   deduplication against the shell's *own* breadcrumb (`SpecDocumentPanel.tsx`) is out of scope,
   confirmed at P1 to be a different, already-styled surface.
9. Left alone, correctly — the bare "Loading…" text this finding named lives in
   `SpecDocumentPanel.tsx`, not in this document at all.
10. **The summary line was already the best-styled part of the document**, with everything below it
    regressing to plain paragraphs. Kept as-is in `restrained.html`; `considered.html` gives it a
    light card treatment so it doesn't read at the same visual weight as the plain prose beneath it.

Everything else already good — and deliberately **not** touched: the three-layer theme cascade and
`hubTheme.ts`'s neutral-only override (a tested, previously-bug-fixed contract — its own comment
records a prior incident where a re-grounded surface once inverted every lifted block because only
the background moved, not the whole ramp); the phase/rigor/modal colour *assignments* themselves
(only their weight was the gap, never the hue); anchor stability; and the deliberate absence of an
in-document navigation script.

## Two real bugs found by looking, not by reading source — both fixed

**P3 — the `#acceptance`/`#requirements` id-on-`<h2>` bug.** In both files,
`<section><h2 id="acceptance">Acceptance criteria</h2><table>...` put the `id` on the `<h2>`, not
on an ancestor of the `<table>`, so every rule scoped `#acceptance table`, `#acceptance col.*`,
`#acceptance td.aw-cell-empty`, `#acceptance tr[data-group]` (and, in `considered.html`,
`#acceptance tbody tr:hover`) silently matched nothing — confirmed by pixel-sampling a hover
screenshot at pure white throughout the column. The same misplacement existed on `#requirements`,
used only for `counter-reset: aw-req`, but it accidentally still counted 1–10 correctly through
CSS's implicit-root-counter fallback when no ancestor establishes a named counter in scope — lucky,
not correct. Fixed by moving both ids onto their enclosing `<section>`, matching the pattern
`#tasks` already used correctly. Verified anchor-neutral first (grepped both files for any
`href="#acceptance"`/`href="#requirements"` — none exist; the shell's own outline sidebar consumes
`toc-ready` postMessage anchors, not reproduced inline here).

**P4 (this pass) — the same class of bug, found by generalizing the P3 fix rather than assuming it
was the only instance.** Having just fixed two sections with this exact id-placement mistake, this
pass checked the other four: `#summary`, `#evidence`, `#open-questions`, and `#map` all carried the
identical pattern (`<section><h2 id="...">`). None of them was **currently** broken —
`#open-questions li`, `#map .aw-map-item`, `#summary p` and `#evidence li` all resolved correctly
because, unlike `#acceptance`/`#requirements`, nothing in either file's CSS was actually scoped as
`#open-questions ...` or `#map ...` (`.aw-map-list`/`.aw-map-item` are styled by plain class
selectors, confirmed by grep). So this was a **latent** inconsistency, not a live defect: the exact
same landmine `#acceptance` already stepped on, sitting unarmed in four more sections, one CSS rule
away from silently going inert again the next time this document is extended. Fixed for
consistency and to close that landmine before it can be stepped on again — moved all four ids onto
their enclosing `<section>`, matching `#tasks` and the now-fixed `#requirements`/`#acceptance`.
Checked anchor-neutrality the same way (grepped both files for `href="#summary"` etc. — none
exist). Re-verified with a small Playwright probe asserting `#summary p`, `#evidence li`,
`#open-questions li`, `#map .aw-map-item`, `#tasks li`, and `#requirements .aw-requirement` all
resolve to their expected counts in both files — all six passed in both — then re-screenshotted
both variants in both themes at full page height and read every image: identical to the pre-fix
renders (this fix has zero visual effect today, by design — it only forecloses a future
silent-failure mode), nothing regressed.

## What P4's second look otherwise confirmed, not changed

- The `data-first="true"` accent border marking a new requirement's first acceptance row
  (`considered.html`) does render — confirmed via `getComputedStyle` (`2px rgb(9,105,218)` vs. the
  ordinary `1px` border colour) and a tight crop at the boundary, not merely asserted from the CSS.
  It reads as a quiet, correctly subtle cue at normal viewing distance, consistent with "considered
  detail, not literal texture" — not boosted further.
- `considered.html`'s map-item hover (a `--surface` fill) is visible and legible in both themes;
  `restrained.html` correctly shows no hover fill there, matching its own stated minimalism.
  `prefers-reduced-motion: reduce` collapses `--aw-dur-fast`/`--aw-dur-base` to `0ms` (confirmed via
  `getComputedStyle` under Playwright's `reduced_motion="reduce"` context emulation, not assumed
  from the media query text) without breaking layout.
- Re-ran the full P3 hover/focus-visible battery (`testbed/scratch/shot_s5_p3.py`, kept from that
  pass) after the id fixes — every state (requirement hover, acceptance-row hover, task-card hover,
  copy-button and nav-link focus-visible via real `Tab` traversal) still renders identically to
  P3's confirmed-good state, in both themes, in both files.

## What was rejected, and under which clause

Nothing from `RESEARCH.md`'s ten findings was discarded — all ten passed validation at P2 and
shipped. The one idea considered and not built: a fourth, cascade-path-specific file (see "The
decision P1 left open" above) — not a rejection under any `IDENTITY.md` clause, but a scope call
that both existing files already cover the material.

## Verification summary across all four passes

- P2: `py -3.11` + Playwright loading each file via `file://` (no server — these are static
  documents), both themes, full-page screenshots, read and checked against the rejection test.
  Honestly flagged clause 7 (interactive states) as spot-read in the stylesheet, not yet triggered.
- P3: closed that gap — real `.hover()` and real `Tab`-key focus traversal (not `.focus()`, since
  Chromium's focus-visible heuristic does not reliably arm on programmatic focus) on a requirement,
  an acceptance row, a task card, a copy button, and a nav link, in both files and both themes.
  Found and fixed the `#acceptance`/`#requirements` id bug this way.
- P4 (this pass): generalized that fix to the four remaining sections carrying the same pattern,
  verified all six section/content selectors resolve correctly in both files with a Playwright
  count probe, re-ran the full P3 interaction battery to confirm no regression, and separately
  confirmed `prefers-reduced-motion` behaves as declared via computed-style inspection.
- All verification screenshots were deleted after reading, per this queue's established
  no-committed-screenshots precedent (`.gitignore`'s blanket `*.png` rule, recorded in
  `dead_ends_inherited` for whoever reaches queue item `Z`) — `git status --short` confirmed only
  the intended `.html`/`.md` files remained before each commit.

**S5 is now fully done — all four passes (P1–P4) complete and verified.**
