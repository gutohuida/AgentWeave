# S8-agents research — the agent roster and its settings

Second sub-screen of queue item `S8` (`jobs` closed 4/4, then `agents`, then `logs`, then the
command palette — `pre_authorised`: "do not start a later S8 sub-screen while an earlier one has
unfinished passes"). This pass reads the current code end to end before touching anything, per
`screen_pass_protocol`.

## The queue item's premise does not match the current tree — corrected before mocking

The queue names three components: `AgentsPage`, `AgentCard`, `AgentSettingsPage`. Two of the three
do not exist as rendered surfaces:

- **There is no `AgentsPage.tsx`.** `Glob` for it returns nothing, and `App.tsx` never imports one.
  AgentWeave has no standalone "all agents" grid — the roster lives inline in the project rail.
- **`AgentCard.tsx` is dead code.** `grep -rn "AgentCard"` across `hub/ui/src` turns up exactly two
  hits outside its own file: `lib/agentStatusConfig.ts`'s doc comment ("Previously duplicated in 2
  components (AgentCard, AgentInfoTab)") and its own test,
  `__tests__/agentCardCollaboration.test.tsx`. Nothing in `App.tsx`, `Sidebar.tsx` or `AgentTree.tsx`
  imports it. `git log` on the file shows real commits (`1c37f6f`, `0cc5df7`, `534cb64`) — it was a
  working component once, superseded when the roster moved into the rail-tree shape, and never
  deleted. **`AgentInfoTab`**, its cited sibling, is further gone: it exists nowhere but that same
  comment and one test's `describe` label in `__tests__/rowMenus.test.tsx`.
- **`AgentSettingsPage.tsx` is real and current** — a destination (not a dialog) rendered from
  `App.tsx:368`, reached via `Sidebar.tsx`'s `agentSettings` branch.

So this pass mocks the surfaces that actually render an operator's agent roster today:
**`AgentTree.tsx`** (the rail rows — expand/collapse, status, attention, the row menu) embedded in
**`Sidebar.tsx`**'s project view, and **`AgentSettingsPage.tsx`** together with
**`AgentSettingsControls.tsx`** (the field widgets each settings section actually renders) and
`Sidebar.tsx`'s `agentSettings` branch (the settings section nav list + back control). `AgentCard`
is noted in `RATIONALE.md` as dead code found, not mocked as a living screen — mocking a component
nothing renders would not show the operator anything they can open.

## What was read

- **`AgentTree.tsx`** (full, including comments). One row per agent: expand chevron, a colored dot
  keyed to `agentColorVars(agent.color_index)` (the 8-agent scale), the name, an attention dot
  (`--amber`, shown only while collapsed — expanding surfaces the same signal via each conversation
  row) and a running/idle dot (`--green` vs `--text-3`). Expanding reveals `ConversationRow`s,
  grouped consecutive loop firings via `LoopFiringGroup`, capped at `CONVERSATION_DISPLAY_CAP = 7`
  with a documented rationale (three agents × seven rows = 25, still fits without scrolling — "cheap
  to revisit against a real project"). A `RowMenu` (three-dot, hover/focus-revealed per the
  operator's 2026-08-08 call against a right-click pattern) offers new conversation / settings /
  show archived. **No avatar, no model badge, no message count, no last-active time, no context
  usage anywhere in this tree** — every one of those fields exists on `AgentSummary`
  (`agent.display_model`, `.message_count`, `.active_task_count`, `.last_seen`,
  `.context_usage`) and is rendered by the *dead* `AgentCard`, not by the live tree. That is a real
  "information that is lacking" finding, not styling: an operator scanning the rail cannot tell
  which agent is near its context limit or which model an agent runs without opening it.
- **`AgentCard.tsx`** (full). Confirms the shape above once existed: status dot + label, model +
  `EXT` (self-registered) + `CANNOT COLLABORATE` badges, a stats row (`msgs` / `tasks` / relative
  last-seen), a compact `ContextUsageIndicator`, and a truncated latest-status line. Read for what
  it did right (a genuinely denser card than the tree row) rather than as something to revive
  verbatim — reviving *this exact component* is a product decision (does the rail want a card-list
  or the tree it has now?) outside a styling mock's authority; what is in scope is asking whether the
  *data* it surfaced belongs back in the tree row, which P2 explores as a variant axis.
- **`AgentSettingsPage.tsx`** (full, including comments). Seven sections (`identity` / `execution` /
  `charter` / `interaction` / `context` / `access` / `workspace`), each a `SettingsSection` of
  `SettingsRow`s. Two comments record deliberate decisions not to undo: the `Isolation` row is
  read-only by design (flipping a worktree agent to shared checkout mid-flight could strand
  uncommitted work — a control needs its own change with a migration story, not a mock); and the
  `unavailable_reason` note under Working directory is a plain `<p>`, not `role="alert"`, because "no
  branch" stopped being a blocking error and became informational — amber + `role="alert"` would
  misannounce it to a screen reader.
- **`AgentSettingsControls.tsx`** (full, including comments). Every field control here is a raw HTML
  element with inline styles: `<select>` (permissions, runner, charter, checkpoint mode, threshold
  unit), `<input type="number">` (waiting seconds, checkpoint threshold), `<input type="checkbox">`
  (the four grants), `<textarea>` (description). None of them use the styled control vocabulary
  `_system/controls.html` (U0b, already built this run) defined specifically for this gap — its own
  section header states it plainly: *"No custom checkbox, radio, toggle or styled select exists
  today — all four built from the same border/hover/focus recipe."* This screen is the first real
  consumer of that vocabulary rather than a second screen inventing its own.
- **`SettingsSection.tsx`** (full). `<section>` + heading + description + an `actions` slot, rows as
  a label/description pair beside a control slot. Structurally sound; entirely unstyled beyond
  `settings-section`/`settings-row` CSS classes (not present in `index.css` — likely a global
  utility class defined elsewhere, effectively plain box + text with no border, shadow, spacing
  rhythm, or hover/focus treatment visible in the component itself).
- **`Sidebar.tsx`**'s `agentSettings` branch (lines ~224-260). A back button, an "Agent settings" /
  agent-name header, then a bare `nav` of seven `row-item` buttons — no icons, no grouping, no
  search. Compare `SettingsSidebarNav` below.
- **`SidebarItem.tsx` and `RowMenu.tsx`** (full). The two shared primitives most of this screen
  actually composes from. `SidebarItem` already carries a considered hover/active language (a
  4px-tall left indicator that animates in on `height`, token-driven hover/active backgrounds,
  transitions on the motion scale) that `AgentTree`'s own rows do *not* reuse — the tree rows are
  hand-rolled `row-item`/`row-group` markup, not `SidebarItem` instances, so whatever polish
  `SidebarItem` has does not reach the roster.

## External research

- **Presence/roster rows** (Setproduct's avatar-UI writeup, Shadcn/ReUI avatar docs, ServiceNow
  Horizon `now-avatar`): a status dot belongs at the lower-right of an identity mark, filled for
  "live" and hollow/muted for "settled," and should be used sparingly — reserved for the fact that
  actually matters (here: is this agent running right now), not decorated onto every row regardless
  of relevance. AgentWeave's existing green/grey dot on `AgentTree` already follows this; the gap is
  everything *besides* the dot.
  ([Setproduct](https://www.setproduct.com/blog/avatar-ui-design),
  [ReUI avatar](https://reui.io/components/avatar),
  [ServiceNow Horizon](https://horizon.servicenow.com/workspace/components/now-avatar))
- **Settings navigation** (Bricx Labs' settings-page patterns, onething.design's nav pattern
  roundup): sectioned single-page layouts work for five or fewer categories; beyond that, search
  becomes load-bearing rather than optional. AgentWeave's agent settings has seven sections — past
  the five-section rule of thumb these sources give, which is a concrete reason to look at what T3
  Code does at a comparable count (below) rather than assume the plain list scales.
  ([Bricx Labs](https://bricxlabs.com/blogs/settings-page-ui-examples),
  [onething.design](https://www.onething.design/post/top-website-navigation-design-patterns))
- **T3 Code `SettingsSidebarNav.tsx`** (recovered from `index-DiDfaONg.js.map`). Seven sections
  (general/appearance/keybindings/providers/source-control/connections/archived — the same order of
  magnitude as AgentWeave's seven) rendered as `SidebarMenuButton`s each with a small leading icon
  (`mt-0.5 size-3.5`), plus a `/`-key-activated search box that filters a flattened index of every
  settings *field* (not just section titles) and highlights/scrolls to the match — `searchSettings`,
  arrow-key result navigation, Enter to jump. The icon-per-section detail is cheap and directly
  applicable (AgentWeave's seven section labels are bare text today); full field-level search is a
  bigger feature than this mock's mandate and is noted as a "missing information" candidate for
  `RATIONALE.md` rather than built.
- **T3 Code `AgentsPanel.tsx`** (recovered from the same map). Not a settings surface, but the
  closest thing T3 Code has to "many agents, glanceable." Its `AgentRow` is instructive on density
  discipline: a fixed-height grid (`grid-cols-[0.375rem_minmax(0,1fr)_auto] grid-rows-[...]`) with a
  code comment stating the rule explicitly — *"Agent rows reserve three fixed lines for identity,
  activity, and metrics; changing data must never change their height"* — so a row never reflows
  when its live data updates. Metrics (`model · N tok · N tools · run N`) render in
  `font-mono tabular-nums text-muted-foreground/70`, visually subordinate to the identity line. This
  is the sharpest available precedent for *why* `AgentTree`'s current single-line row cannot simply
  grow a second line of metadata without a stated height contract — worth carrying into P2's variant
  that adds model/context data back to the row.

## What is missing versus merely unstyled

Per `pre_authorised`'s explicit invitation ("If a screen's research turns up a missing FEATURE
rather than a styling gap, mock it and note it in `RATIONALE.md`"):

1. **Agent identity data dropped from the rail.** Model, message count, context usage and last-seen
   all exist on `AgentSummary` and are computed today only for the unrendered `AgentCard`. The tree
   row shows none of it. This is the clearest concrete case IDENTITY.md's "information that is
   lacking" clause anticipates.
2. **No field-level settings search**, unlike the seven-section precedent T3 Code ships at a
   comparable section count.
3. **Section icons** in the settings nav — present in T3 Code's equivalent list, absent in
   AgentWeave's.

Everything else is a styling gap, not a missing feature: `AgentSettingsControls`' raw native
`<select>`/`<input type=checkbox>` should become the U0b vocabulary's `.ctl-select`/`.ctl-switch` (a
literal swap-in, not a redesign — U0b was built for exactly this), `SettingsSection`/`SettingsRow`
need the elevation and spacing rhythm U0a defined, and `AgentTree` rows need the hover/press/focus
states `SidebarItem` already has but the tree does not reuse.

## Plan for P2

Two mock targets, each with restrained/considered variants (light + dark, per
`pre_authorised`):

1. **The rail roster** (`AgentTree` embedded at sidebar width, ~230px) — apply `SidebarItem`-grade
   interaction states to the agent row, and explore *whether* model/context/last-seen data returns
   to the row without breaking `CONVERSATION_DISPLAY_CAP`'s density math, following the T3
   fixed-height-row discipline so it does not reflow.
2. **Agent settings** — `AgentSettingsPage`'s Identity/Execution/Interaction sections (the three
   with the widest control variety: text, select ×3, checkbox ×2, number ×2) restyled with U0b's
   control vocabulary, plus the settings-section nav list with icons added per section.

Both stay within IDENTITY.md clause 1 (existing tokens only) and clause 3 (the existing radius
scale) — nothing here needs a new geometry, only the vocabulary already built in `_system/`.
