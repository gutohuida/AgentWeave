# S4 rationale — the task DAG / dependency board

Four passes (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this document).
`DependencyBoard.tsx` / `DependencyBoardView.tsx`, mocked both standalone (its own page) and
panel-embedded (per `decisions_for_user` D-dag-placement, since a `tasks`/`dag` panel tab does not
exist today — see `RESEARCH.md` finding 8). The operator's own words framed this screen twice: once
in the original brief ("the links should not be static... the UI is just kind of ugly") and once in
`openspec/explorations/2026-08-21-the-execution-graph-in-the-panel.md`, which this pass read in full
before touching anything, per `screen_pass_protocol`.

## Research → changes

Full findings and sourcing live in `RESEARCH.md` (GitHub Actions' run-graph status-icon idiom,
Airflow's colour-coded graph view, React Flow's orthogonal-edge and `animated`-edge guidance, and a
direct reading of `DependencyBoard.tsx`, `dependencyBoardLayout.ts`, `DependencyBoardView.tsx`,
`panelTabsStore.ts`, and `TaskCard.tsx`). Ten verified gaps, all confirmed against the actual
component before building anything, plus one code-verified cause the exploration doc itself didn't
name (collapsed layers don't just go stale on expand — while collapsed they silently drop every edge
that passes through them, with no affordance saying a hidden connection exists).

1. **Edges were visually inert** — a flat `--border-hi` line, same weight regardless of what it
   connects, no arrowhead, direction implied only by vertical position. Both variants add an
   arrowhead (`marker-end`) and colour that means something: grey for a normal dependency, amber
   when the target is gated on an unmet prerequisite, red when gated on a *rejected* one, green and
   animated when the source task is actively running (`isLive`, no new data — `TaskCard.tsx:94`
   already computes this).
2. **Collapsed layers silently dropped every edge through them**, with zero signal. Both variants
   add a hidden-link count to the collapse toggle ("3 done · 3 links hidden"); `considered` goes
   further with a dashed ghost stub beneath the toggle showing where a hidden connection continues,
   per `pre_authorised`'s licence to demonstrate a fix as a variant rather than a source change.
3. **No lineage-on-hover** — the exploration doc's own stated want ("to access the lineage fast")
   had no mechanism. `considered` adds hover-to-highlight: ancestors and descendants light up with
   `--ring` (the same token every existing selection state already uses — clause 2 of the rejection
   test, no new accent), everything else dims to 32% opacity, and a collapsed layer's toggle
   highlights too so a lineage running through hidden cards stays legible without expanding it.
4. **Off-board prerequisite chips floated with no connecting line at all** — confirmed by reading
   `useEdgeLines`'s own guard (`if (!fromEl || !toEl) continue`). Not rebuilt as a new layout; both
   variants keep the chip and its owning-document label exactly as-is, since finding 4 in
   `RESEARCH.md` is about the *disconnection*, not the chip's content.
5. **The collapse toggle carried no information beyond a bare count.** Addressed by finding 2's
   hidden-link count on both variants.
6. **The document picker bar was undifferentiated pills** with `outstanding/total` as plain text.
   Both variants add an icon distinguishing a real spec document from the standing "no document"
   board and a thin SVG progress ring/bar (`stroke-dasharray`, no new colour) under the label.
7. **The structure hint sentence had no visual anchor.** Both variants give it its own bordered strip
   instead of a bare line of muted text below the picker.
8. **No panel-embedded form exists.** `panelTabsStore.ts`'s `IndexTabId` is a closed
   `'specs' | 'files' | 'loops'` union with no `tasks` member. Both variants' panel-embedded mock is
   captioned plainly as a proposal, not shipped machinery, matching S3's precedent for the same kind
   of caveat.
9. **The layer stall-summary sentence** (the one piece of this screen doing real synthesis — naming
   whether a layer is gated on an unmet vs. a rejected prerequisite, design D8) **had the least
   visual weight of anything on the board.** Both variants give it a bordered strip of its own,
   matching finding 7's treatment.
10. **Loading states were a bare `Loading tasks…` line** (`DependencyBoard.tsx:169`,
    `DependencyBoardView.tsx:40`) while the zero-tasks case already used the shared `EmptyState`
    component. Both variants replace the text line with shape-matched skeleton rows from
    `foundations.html`'s primitives, extending the same treatment the empty case already had rather
    than inventing a third pattern.

## A real bug found by looking, not by reading source (P4)

Both `restrained.html` and `considered.html` gave `layer0`'s card container the `hidden` HTML
attribute *and* a `.layer-cards { display: grid; ... }` class rule. The `hidden` attribute's
built-in effect is a User-Agent stylesheet rule, `[hidden] { display: none }`, at specificity
`(0,1,0)` — identical to a single class selector. When two rules tie on specificity, the one that
comes later in cascade order wins, and an author stylesheet is always applied after the UA
stylesheet — so `.layer-cards`'s `display: grid` silently overrode the UA's `display: none`, and the
`hidden` attribute did nothing. The JS data model (`boardState[prefix].collapsed = new Set([0])`)
correctly treated layer 0 as collapsed for edge computation — 4 edges instead of 7, "3 links hidden"
on the label — but the cards themselves rendered fully visible underneath a toggle whose chevron
pointed right (collapsed) and whose label said cards were hidden. On first load, every mock in this
pair contradicted its own collapse indicator.

Found by looking at the "collapsed" baseline screenshot taken before any click in this pass's
Playwright verification and noticing the three done cards were plainly visible despite the
right-pointing chevron and hidden-count label — not by reading the JS, which looked correct in
isolation. Confirmed with `getComputedStyle(el).display` on `#sa-layer0-cards` at page load: `grid`,
not `none`, despite `hasAttribute('hidden')` returning `true`. Fixed with the standard idiom for this
exact tie — `.layer-cards[hidden] { display: none; }`, an attribute selector on the same class,
specificity `(0,2,0)`, unambiguously above the plain class rule — in both files, for both the `sa-`
and `pe-` prefixed boards (the only two elements using `hidden` in either file). Re-verified
programmatically (`display: none` at load, `hasAttribute('hidden'): true`) and by re-running the
full edge/hover verification script: all edge counts (4→7 on expand, 7 constant in `considered`) and
hover-highlight counts (6 active / 3 dim / 4 edge-active / 3 edge-dim) were unchanged, confirming the
fix touched only the initial-paint visibility and nothing about the redraw logic. Re-screenshotted
all four collapsed baselines (both variants × both themes) and read them directly: layer 0 now
renders correctly collapsed on load, matching its own chevron and hidden-count label, in both themes.

## What was rejected, and under which clause

- **Crossing-minimisation or a different routing algorithm for `restrained`.** `restrained`'s own
  subtitle says so explicitly: straight point-to-point lines, no new routing — that's `considered`'s
  job. Giving `restrained` orthogonal routing too would blur the restrained/considered distinction
  into two names for the same thing, which is its own failure of clause 5 ("a reader would call it
  the same application... not a different design language" applies between variants of *this*
  screen just as much as against the shipped product).
- **A minimap or pan/zoom control.** Considered explicitly in `RESEARCH.md`'s external-research
  section and rejected there: AgentWeave's boards are small (a handful of layers, few tasks each,
  confirmed by reading `groupByDepth`'s output shape), and minimap chrome would cost space for a
  graph this size without solving a real problem here. Noted so a later pass doesn't reintroduce it
  as an assumed best practice.
- **Building the panel `tasks`/`dag` tab for real**, or wiring `IndexTabId` to include it. A missing
  feature, not a styling gap (`RESEARCH.md` finding 8) — mocked and captioned, per `limits`'s
  mock-only constraint; C6 is the sole exception to that constraint and this isn't it.
- **A third "expressive" variant.** Same reasoning S3 gave for the same choice: this is a technical
  diagram meant to communicate structure at a glance, not a surface where more visual weight helps
  the reader — an expressive treatment risks reading as noise on top of a DAG rather than refinement,
  which is its own way of failing clause 7 ("no... surface treatment for texture's sake").
- **Redesigning the off-board reference chip itself**, rather than only its connection. Finding 4 is
  about the missing line, not the chip's content or position — the exploration doc's own diagnosis
  and task 8.7 both keep the chip as a named, visible reference; only its total disconnection from
  the graph was the gap.

## What's already good and was left alone

Carried forward from `RESEARCH.md`'s P1 findings, confirmed unchanged after building and two full
render-and-read passes: the three-way stall classification (`gated` / `waiting_on_review` /
`gated_on_rejected`, design D8) — real synthesis, both variants keep naming all three distinctly and
only improve the sentence's visual weight; longest-path depth / top-to-bottom layering (tasks
8.1/8.2); the partly-finished-layer-never-collapses rule (design D9); the off-board reference chip's
content (task 8.7); the document picker's document-first sort (`useTaskBoards`'s own ordering, "no
document" always last); `EmptyState` on the zero-tasks case, whose treatment finding 10 only extends
to the loading case rather than replacing. `TaskCard.tsx` itself is not re-researched here — S2
already did that work in depth, and both variants' cards deliberately read as the *same* refined card
S2 arrived at (its hover elevation, press state, and status-glyph vocabulary), not a third,
DAG-specific card design.

## Both placements, deliberately, per D-dag-placement

Both variants ship in two forms — standalone (full-width, its own screen) and panel-embedded
(narrower, single-column stacking, compact pills) — because the operator's placement preference is
explicitly undecided (`decisions_for_user` D-dag-placement) and `pre_authorised` licenses mocking
both rather than guessing. The panel-embedded form is captioned as illustrative machinery, matching
how S3 already handles a comparable "this doesn't exist as a real tab yet" caveat. The lineage-hover
mechanism is identical in both forms — verified in this pass by hovering a card in the panel-embedded
`considered` mock and confirming the same active/dim/edge-active/edge-dim counts as the standalone
board.
