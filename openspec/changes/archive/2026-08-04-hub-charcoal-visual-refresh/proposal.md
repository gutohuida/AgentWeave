# Charcoal ground plane, composer alignment, and chronological work

## Why

The previous change (`2026-08-04-hub-contextual-navigation`) fixed the interaction model — hover,
press, and selected states now resolve from tokens, and the rail owns contextual navigation. It did
not touch the palette, the composer's internal layout, or the order in which a turn's work is
rendered. Operator review of the running build found four things still wrong, and one piece of dead
UI.

**The palette is blue, not neutral.** The ground plane is `--bg: #10131b` and the rail is
`--rail: #171b2a` — both carry a visible blue-navy cast, and `--surface-2: #242a3c` reads
distinctly indigo against text. The operator's direction is a black/charcoal base. A hue-bearing
ground plane also competes with the eight-colour agent identity palette, which is the one place in
the product where hue is supposed to carry meaning.

**The composer's text is pushed off its own left edge.** `Composer.tsx` renders a horizontal flex
row — `[agent selector] [textarea] [send]` — so the text area begins to the right of the selector
button rather than at the composer surface's leading edge. Measured live at a 359px viewport: the
composer surface spans 299px starting at x=30, while the textarea starts at x=162 and receives only
110px. The offset is structural, so it is present at every width and severe at narrow ones. Every
comparable product (T3, Claude, ChatGPT) puts the text area full-width on top and the controls in a
row beneath it.

**The rail marks the open project with a permanent fill.** `.row-item[data-active="true"]` paints
`--row-selected` continuously, so the selected project row is always highlighted whether or not the
pointer is near it. The operator's direction is that the fill belongs to hover; the open project
still needs to be identifiable, but not by carrying a hover-weight fill at rest.

**The project header is boxed.** `ProjectHeader` draws `background: var(--top)` closed by
`borderBottom: 1px solid var(--border-region)`, which reads as a rigid box rather than a heading on
the ground plane. Its second line interpolates the working directory as one raw string —
`3 agents · C:\Users\huida\Documents\projects\AgentWeave\testbed\two-codex-agents\workspace` — which
is unreadable at a glance and truncates from the wrong end.

**A turn's work is hoisted above the prose that preceded it.** `TurnBody` partitions a turn's
entries into `work` and `rest`, renders the entire `Work · N steps` disclosure first, then all
remaining text. A turn that ran *"let me check the file"* → Read → *"now I'll edit"* → Edit renders
the work block above both sentences, so the operator reads the agent's narration stripped of the
actions it was narrating. Execution order is the only order that explains the turn.

**The theme picker does nothing.** `SetupModal` offers five themes (Purple, Blue, Green, Orange,
Rose) writing `data-theme` to the document, `configStore` persists a `ThemeId`, and **no CSS rule
in the application reads `data-theme`**. Only `data-mode` (light/dark) is wired. The control has
been inert for its whole life and misrepresents the product's capability.

## What changes

- **The ground plane becomes neutral graphite.** All surface, rail, and border tokens are respun on
  a near-neutral ramp for both modes. Hue is removed from the chrome so it remains available to the
  agent identity palette and the semantic status colours, which keep their meaning.
- **Emphasis becomes monochrome, with a single accent reserved for state.** The primary control
  fill becomes near-white on the dark ground (and near-black on the light ground). One accent hue is
  retained, but demoted: it is used only for the focus ring, the rail's active marker, and
  selection — never as a button fill.
- **The composer becomes a column.** The text area occupies the composer surface's full width on its
  own row, and the agent selector, the send control, and any future per-turn controls sit in a
  control row beneath it. Text begins at the composer's leading edge.
- **The rail's active project is marked, not filled.** `data-active` no longer paints a row fill.
  The open project is indicated by a leading accent bar and brighter, heavier label text; the fill
  is returned to hover and press alone.
- **The project header sheds its box.** No bottom rule and no fill distinct from the ground plane.
  The directory is presented as readable path segments that elide from the middle, not as one raw
  interpolated string.
- **Work renders in execution order.** A turn's entries are walked in order and *consecutive* runs of
  work are grouped into a disclosure in place. Work never moves ahead of text that preceded it.
- **The inert theme system is removed** — the picker, `ThemeId`, the persisted value, and the
  `data-theme` attribute write. Light/dark remains.

## Non-goals

- Changing what any screen does. This change governs colour, alignment, ordering, and emphasis only.
- Adding model or effort controls to the composer. The composer gains the *control row* that will
  host them; populating it belongs to `2026-08-04-hub-model-control-and-provisioning`.
- Redesigning the Spec workspace, the environment sections' content, or the overview cards.
- Changing conversation semantics: queue handling, hop budget, handoff, autoscroll, context usage,
  and provider-identity confinement keep their current specified behaviour.
- Introducing a user-selectable accent or a real multi-theme system. The dead one is removed, not
  replaced.

## Impact

- **Frontend:** `index.css` (token ramp for both modes, row-state rules, rail active marker),
  `Composer.tsx` (row → column), `ComposerAgentSelector.tsx` (control-row presentation),
  `Sidebar.tsx` (active marker), `ProjectHeader.tsx` (box removal, path presentation),
  `AgentTimeline.tsx` (`TurnBody` ordering), `SetupModal.tsx` and `configStore.ts` (theme removal),
  and the ~25 raw hex / 85 `rgba()` literals in components — chiefly `Badge.tsx` — that bypass the
  token system and would otherwise survive the recolour.
- **Backend:** none. No API, schema, or event changes.
- **Static assets:** the committed production UI bundle is refreshed after the source build.
- **Specifications:** modifies `hub-workspace-shell`; adds requirements to
  `agent-conversation-workspace` and `agent-stream-events`.

## Approval gate

Implementation MUST NOT begin until the user explicitly approves this proposal.

**Approved:** yes (2026-08-05, verbal: "Both approved. Implement both of those.")
