# S4 research — the task DAG / dependency board

The operator's own words, verbatim, from `openspec/explorations/2026-08-21-the-execution-graph-in-the-panel.md`:
*"The edges are kind of broken. They're static on the page. If I expand the 2 done they just don't
make sense anymore. We can see which are done but the UI looks bad. […] The UI is just kind of
ugly. The links should not be static."* Also: *"The execution graph […] should be on the right panel
with the spec and the others. To access the lineage fast."* This pass reads the exploration doc and
the current code end to end before touching anything, per `screen_pass_protocol`.

## What was read

- **`openspec/explorations/2026-08-21-the-execution-graph-in-the-panel.md`** (full). Diagnoses cause
  1 (the stale-edges bug) precisely, leaves cause 2 ("ugly") and placement genuinely open, and
  poses four questions this mock is partly answering by demonstration rather than by fiat — see
  findings 1, 2 and the panel-embedding section below.
- **`DependencyBoard.tsx`** (full, including comments). `useEdgeLines` measures each edge's two
  cards via `getBoundingClientRect` after layout and draws a plain SVG `<line>` between them —
  `stroke="var(--border-hi)"`, `strokeWidth={1.5}`, no arrowhead, no marker, no hover state, no
  highlighting. Layers collapse when every task in them is terminal (`isTerminalTask`); the toggle
  is a bare chevron + "N done" text button. Off-board prerequisites render as dashed pill buttons
  in a row above the layers — but confirmed by reading `useEdgeLines` closely, they are **never
  connected by a line to anything** (line 76: `if (!fromEl || !toEl) continue`), so an off-board
  reference reads as a floating chip with no visual tie to the card that names it.
- **`dependencyBoardLayout.ts`** (full). Longest-path depth assignment, terminal-status set,
  three-way stall-state classification (`gated` / `waiting_on_review` / `gated_on_rejected`) —
  already-considered logic, not a styling gap; a mock must keep surfacing this distinction, not
  simplify it away.
- **`DependencyBoardView.tsx`** (full). The document picker above the board: plain rounded-pill
  buttons, `outstanding/total` as bare tabular-nums text, no icon differentiating "no document"
  from a real spec board, and a one-line muted "structure hint" sentence explaining edges are
  read-only here (design D5) sitting unstyled below it.
- **`hub/ui/src/store/panelTabsStore.ts`** — confirmed `IndexTabId = 'specs' | 'files' | 'loops'`.
  **There is no `tasks`/`dag` index tab today.** Panel-embedding this screen (per the exploration
  and `decisions_for_user` D-dag-placement) is therefore a missing-feature note, not a pure
  styling exercise — noted plainly rather than invented as if it already existed.
- **`TaskCard.tsx`** — the same card S2 already researched in depth renders inside every layer
  here unchanged. Not re-researched from scratch; S2's findings (no hover elevation, no press
  state, priority-badge colour bug, same-shaped pills) apply identically inside the DAG, so this
  mock's card treatment should read as the *same* refined card S2 arrived at, not a third variant.
- **`design/mocks/_system/foundations.html`** — the elevation tiers (`tier-1/2/3`, inset
  `--lift-hi` + graduated `box-shadow`) and the motion scale are the vocabulary this mock draws
  its layer-panel and edge-highlight treatment from, rather than inventing new depth cues.

## An additional, code-verified cause the exploration doc didn't name

The exploration doc's cause 1 (the `layoutKey` staleness) explains why edges are **wrong** after an
expand. Reading `useEdgeLines` further shows a second, earlier problem in the same mechanism: while
a layer is *collapsed*, its cards are unmounted entirely (`{expanded && (...)}` at
`DependencyBoard.tsx:282`), so any edge touching a task inside that layer hits the same
`if (!fromEl || !toEl) continue` guard used for genuine off-board references — **the edge simply
does not exist while collapsed, with no affordance saying a connection is hidden there.** This is
very likely a large part of "the links should not be static": a collapsed "2 done" row doesn't just
lose detail, it silently severs every line running through it, and nothing on the row communicates
that. This mock demonstrates a fix (a hidden-edge count on the collapse toggle) as a **variant**,
not a source change — `limits` keeps this screen mock-only.

## External research

- **GitHub Actions' run graph**: an icon *left of* each job name carries status (queued / running /
  success / failed), colour-coded, with lines for dependencies between jobs — the same "icon +
  colour, not colour alone" idiom S2 already borrowed from Linear for task cards. Confirms the
  card-level status glyph direction should extend to DAG nodes, not diverge for this screen.
  ([GitHub Docs — monitor workflows](https://docs.github.com/en/actions/how-tos/monitor-workflows))
- **Airflow's graph view**: colour-codes the *current run's* state per node and is described as the
  primary way operators debug a stuck pipeline — validates that a DAG view earns its keep most when
  a viewer can tell "why is this stuck" at a glance, which is exactly `layerStallSummary`'s job
  today, just unstyled.
  ([ThinhDA — comparing workflow architectures](https://thinhdanggroup.github.io/airflow-prefect-dagster/))
- **React Flow's edge taxonomy**: bezier is the library default, but **step/smoothstep (orthogonal)
  edges are recommended specifically for flowcharts and technical diagrams** over freehand diagonal
  lines — directly applicable, since today's edges are raw point-to-point diagonals with no routing
  at all. An orthogonal or smoothstep path (vertical-then-horizontal-then-vertical, still drawn as
  one `<path>` with the existing `--border-hi` stroke and 1.5px weight) would read as considered
  routing rather than a debug overlay, without touching layout, colour or the crossing-minimisation
  scope task 8.12 already deferred. React Flow also documents an `animated` edge property — the
  standard idiom for "this connection is currently active" in pipeline UIs (a moving dash offset) —
  which maps directly onto an edge whose destination card is live (`task.assignee_status ===
  'running'`, the same condition `TaskCard.tsx:94` already computes as `isLive` — no new data),
  giving the graph genuine *motion tied to real state* rather than the fully static
  rendering the operator called out, while staying inside `IDENTITY.md`'s existing motion scale and
  respecting `prefers-reduced-motion` the same way `task-live-pulse` already does.
  ([React Flow — Edge types](https://reactflow.dev/examples/edges/edge-types),
  [React Flow — Edge API reference](https://reactflow.dev/api-reference/types/edge))
- **DAG visualization at scale** (general): past a handful of nodes, minimaps and pan/zoom become
  standard, and overlapping-edge reduction matters more than any single node's styling. AgentWeave's
  boards are small (a handful of layers, few tasks each, confirmed by reading `groupByDepth`'s
  output shape) — a minimap or zoom control would cost chrome for a graph this size and was
  considered and **rejected** here, not overlooked; noted so a future pass doesn't reintroduce it
  as an assumed best practice.
  ([Tom Sawyer Software — directed graph visualizer](https://blog.tomsawyer.com/directed-graph-visualizer))

## What's actually missing from *this* screen, specifically

1. **Edges are visually inert.** A 1.5px `--border-hi` straight line, same weight and colour
   regardless of what it connects — a completed→completed edge looks identical to a
   completed→gated one. No arrowhead; direction is implied purely by top-to-bottom position, which
   breaks down for two cards in the same layer with a shared un-drawn ancestor two layers up.
2. **Collapsed layers silently drop edges through them** (see finding above) — not just the
   diagnosed staleness-on-expand, but zero signal that a hidden connection exists while collapsed.
3. **No lineage-on-hover/select.** The exploration doc's own stated want — *"to access the lineage
   fast"* — has no mechanism today. Hovering or opening a card does not highlight its ancestor or
   descendant chain; every edge is always the same weight regardless of what's selected.
4. **Off-board references float with no connecting line at all**, confirmed above — a chip that
   claims a relationship to something on this board but is drawn nowhere near it, disconnected from
   the layer that actually names it.
5. **The collapse toggle carries no information beyond a count.** "2 done" + chevron is the entire
   affordance — no preview of which tasks, no hover expansion, no indication of hidden edges (see
   finding 2).
6. **The document picker bar is undifferentiated pills** — same visual treatment as any other pill
   in the product, no icon distinguishing a real spec document from the standing "no document"
   board, `outstanding/total` as plain text with no visual proportion (a thin progress bar or ring
   would read faster than two numbers).
7. **The structure hint is a lone sentence with no visual anchor** — sits directly under the picker
   with no icon or container, easy to miss entirely despite explaining a real constraint (D5: edges
   are read-only here).
8. **No panel-embedded form exists at all** — confirmed via `panelTabsStore.ts`: `IndexTabId` has no
   `tasks`/`dag` member. Per D-dag-placement this mock demonstrates both a standalone page and a
   plausible panel-embedded layout (narrower column, layers likely needing to stack rather than
   flow), but the panel form is a proposal, not a reflection of shipped tab machinery.
9. **The layer stall-summary sentence is plain, unstyled text** — the one piece of this screen doing
   real synthesis work (task 8.8 / design D8's "name the layer's stalled state, not only each
   card's") gets the least visual weight of anything on the board.
10. **No empty/loading treatment beyond a text line** — `isLoading` renders bare "Loading tasks…"
    text (`DependencyBoard.tsx:169`) and `DependencyBoardView.tsx:40` the same for boards; the
    zero-tasks case does use `EmptyState` (good — see below) but the loading case does not match it.

## What's already good and must not be redesigned

- **The three-way stall classification** (`gated` / `waiting_on_review` / `gated_on_rejected`,
  design D8) — real synthesis, not a display choice. A mock must keep naming all three distinctly,
  only give the sentence better visual weight.
- **Longest-path depth / top-to-bottom layering** (task 8.1/8.2) — correct and deliberate; not a
  layout to relitigate.
- **The partly-finished-layer-never-collapses rule** (design D9) — a layer with any unfinished task
  always shows every card. Do not make collapse more aggressive.
- **Off-board references are named, not hidden** (task 8.7) — the chip itself, and the fact it
  states the owning document, stays; only its total visual disconnection from the graph is the gap.
- **`EmptyState` on the zero-tasks case** — already uses the shared component; extend the same
  treatment to the loading case rather than replacing either.
- **The document picker defaulting to the first real board, "no document" last** (`useTaskBoards`'s
  own sort) — not a layout to change, just to give better visual treatment.

## Next

P2: validate every finding above against `IDENTITY.md`'s rejection test (clause 5 above all), then
build `design/mocks/S4/<variant>.html` in **two forms per variant** — standalone and
panel-embedded — per the pre-authorised instruction to mock both placements from
`decisions_for_user` D-dag-placement, with realistic multi-layer graph content including a
collapsed terminal layer, an off-board reference, a `gated_on_rejected` card and a live/running
card, in both themes.
