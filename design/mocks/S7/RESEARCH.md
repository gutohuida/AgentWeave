# S7 research — the overview screen

P1 of the four-pass protocol. No mock built this pass; this is the research this screen's mocks
(P2) will draw from.

## What this "screen" actually is — one component, six sub-sections

Confirmed by reading `hub/ui/src/components/overview/OverviewPage.tsx` in full, including its
comments:

| Section | Source | Role |
|---|---|---|
| Header | inline in `OverviewPage` | Plain `h1` + one-line subtitle (agent/task counts, project name) |
| Budgets | `<AccountingPanel />` (`components/accounting/AccountingPanel.tsx`), built on `SettingsSection`/`SettingsRow` | Token totals, per-agent usage chips, budget input |
| Agent health grid | `AgentHealthCard`, defined inline in this same file | One card per connected agent: status dot, name, task/message counts, `ContextUsageIndicator`, last-seen, latest status message |
| Workspace summary | inline, `.lifted-surface` buttons | Three nav shortcuts: Tasks / Spec / Jobs |
| Question interrupt | `<QuestionInterruptCard />` (`components/questions/`) | Already covered by S6 — out of scope here except where it touches this page's rhythm |
| Task summary | inline | Status pill chips (count per `task.status`), hand-rolled color mapping |
| Activity ticker | inline | Horizontal scroll of the last 10 SSE events as pill chips |

This is the **landing surface and first impression** — the operator's eye lands here before
anything else, and it is also the only screen that summarizes budget, agents, tasks and live
activity together. Its plainness is not one component's problem; it's six differently-weighted
inline blocks stacked with uniform `space-y-6` and almost no shared visual grammar between them.

## What's already good — do not undo

- `AgentHealthCard`'s comment (lines 19-23) is a deliberate, reasoned choice: it intentionally does
  **not** reuse `<StatusDot />`'s `animate-ping` halo, using a static glow shadow instead so a
  `stalled` agent (running but heartbeat-dead) reads distinctly from merely `idle`. Any mock must
  keep sourcing color from `getStatusConfig`, not re-invent agent-status semantics.
- The `recentEvents` `useMemo`'s dependency array is explained at length (lines 99-106): the three
  query results are deliberately-wrong-looking deps standing in for a buffer mutation React can't
  see directly. Not a bug to "fix" in a mock; the eslint-disable is intentional and documented.
- `ContextUsageIndicator`'s `compact` mode (used here) is already token-driven and reasonably
  restrained — no changes needed to it, only to how its host card frames it.
- ChoosingTasks/Spec/Jobs as the three workspace shortcuts (not more, not fewer) matches
  progressive disclosure — the page doesn't try to surface everything, just the highest-traffic
  destinations.

## Gaps found in the current component, verified by reading it

**Header** (lines 120-126): plain `h1` at 14px/600 weight + an 12px subtitle line, no icon, no
accent, no visual separation from the section below it. It is the *least* visually weighted text
on the page even though it's nominally the page title — `AccountingPanel`'s embedded `<h2>` (via
`SettingsSection`, see below) renders larger (`text-base`/16px) than this page's own `<h1>`.

**`AccountingPanel` / `SettingsSection` reuse is a fit problem, not just a styling one**
(`SettingsSection`/`.settings-section` in `index.css:471-503`): that CSS class was built for a
**dedicated, full-width settings page** — `padding: 28px clamp(20px,4vw,48px) 40px`, a
`min-height: 76px` row rhythm, `width: min(100%, 920px)` — and carries **no border or background
of its own**; it relies on a settings page's chrome around it. Embedded directly into
`OverviewPage`'s `space-y-6` stack, it is the only un-bordered, heavily-padded slab sitting between
a bordered agent-card grid above (implicitly, once card-styled) and bordered task chips below. It
reads as a page fragment pasted into a different page, not a native overview widget.

**`AgentHealthCard`** (lines 18-78):
- `transition: 'border-color 0.15s'` is a **literal ad-hoc value**, not `var(--dur-fast)` — this is
  exactly the pattern IDENTITY.md measures as the actual problem (9 token uses vs. 44 ad-hoc). The
  duration (150ms) happens to match `--dur-fast` by coincidence, but the token itself isn't used, so
  a future scale change wouldn't reach this component.
- Only `border-color` transitions on hover — no elevation lift, no background shift, no scale. Rest
  state and hover state differ by one border shade only.
- No visible `:focus-visible` treatment at all — this is a `<button>` (keyboard-reachable, used for
  primary navigation to an agent's conversation) with zero custom focus styling; it falls back to
  whatever the browser default is, which on a near-black charcoal surface is often close to
  invisible. IDENTITY.md explicitly calls interaction states (including focus-visible) in scope and
  "barely used."
- No press/active state.
- No stagger or fade-in when the grid populates on load — cards appear all at once, no motion at all
  applied here (0 of the 9 places IDENTITY.md counted are in this file).
- The glow shadow only appears when `statusCfg.pulse` is true; for a merely `idle` agent there is no
  visual event marking a status *change* (an agent going from `waiting` to `idle`, for instance,
  updates instantly with no transition on the dot's color or shadow).

**Workspace summary buttons** (lines 162-173, `.lifted-surface`): `.lifted-surface`
(`index.css:317-322`) defines only a resting-state shadow (`0 1px 2px rgb(0 0 0 / 0.08), inset 0 1px
var(--lift-hi)`) — **no hover rule, no active rule, no transition property at all**. Three
primary-navigation buttons (Tasks / Spec / Jobs) currently give zero feedback on hover beyond
whatever `cursor: pointer` implies. No icons on these buttons either, despite `Icon.tsx` already
mapping `task_alt` (`ListChecks`) and `schedule` (`Clock`) — plausible icons for two of the three
that go unused here.

**Task summary chips** (lines 188-216): status→color is a **hand-rolled ternary local to this
file** (`in_progress` → blue, `under_review` → amber, `approved` → green, `revision_needed` /
`rejected` → red, else `--text-2`) — grepped `hub/ui/src` for a shared task-status color config and
found none; `TaskCard.tsx`/`TasksBoard.tsx` (the actual Tasks screen, reviewed at S2) do their own
status coloring independently too. Two screens derive the same five-way mapping separately with no
shared source of truth — not a visual gap exactly, but the kind of duplication that lets the two
screens' colors silently drift apart. Visually: chip hover only changes background
(`hover:bg-[var(--row-hover)]`, one of the few places in this file that *does* use a design token
correctly) but the colored dot itself has no transition and no motion.

**Activity ticker** (lines 218-265): fixed `height: 28`, `overflow-x-auto`, no visible scroll
affordance — no edge fade/gradient mask hinting there's more to scroll, no scrollbar styling, no
snap. Each pill has a colored dot (warning=amber, else=green) but the dot itself never transitions
and there's no entry animation when a new event arrives at the front of the list — a fast-moving
ticker that should feel "live" currently just replaces its DOM content silently.

**Empty state — agents** (lines 148-160): centered text-only box, "No agents connected. Run
`agentweave start` to connect agents." No icon, no illustration, no visual weight beyond the
`--surface`/`--border`/`--radius` box already shared by every other bordered block on the page.
This is IDENTITY.md's own named example: "Empty states — currently the plainest thing in the
product."

**Loading state** (lines 109-115): a single line of muted text, "Loading…" — no skeleton shaped
like the agent-card grid that's about to arrive, matching IDENTITY.md's flagged loading-state gap
directly.

**No section dividers or grouping**: six blocks of very different visual weight (plain header,
un-bordered settings slab, bordered card grid, un-bordered nav buttons, bordered chip row, ticker)
sit in one `space-y-6` flex column with identical 24px gaps between all of them — the eye has no
cue for which blocks are related versus incidental neighbors.

## External research

**Search: "dashboard overview screen UI UX design patterns 2026 at-a-glance status cards
information hierarchy"**

- Strategic minimalism: every element on screen must earn its place; a strong 2026 pattern combines
  a sidebar (unrelated here — AgentWeave already has one), a **card-based metric strip (4-6 KPIs)**,
  and a flexible content grid.
- Progressive disclosure — show the minimum needed to decide the next action, reveal more on
  request — is named the single most important 2026 dashboard pattern. AgentWeave's own three-button
  workspace summary already does this in spirit (a shortcut, not the full detail); it just needs the
  visual treatment to say so.
- F/Z-pattern scanning: decision-critical KPIs top-left, trends/charts center, deep tables/filters
  bottom or side. Useful for ordering, less directly for AgentWeave's operator-tool shape, but
  supports moving the agent-health grid (the most decision-relevant "is something broken" signal)
  above the budget panel rather than below it, and keeping the raw activity ticker lowest.
- [Dashboard Design Principles: The Definitive Guide (2026) — UXPin](https://www.uxpin.com/studio/blog/dashboard-design-principles/)
- [50 Best Dashboard Design Examples for 2026 — Muzli](https://muz.li/blog/best-dashboard-design-examples-inspirations-for-2026/)
- [Dashboard UI Design Principles & Best Practices Guide 2026](https://www.designstudiouiux.com/blog/dashboard-ui-design-guide/)

**Search: "operator dashboard empty state first-run design patterns 2026 zero state"**

- An empty state should look like it belongs to the product (same colors, type, spacing, button
  styles) and should tell the user their next action, not just report absence.
- A first-run dashboard benefits from a state that names the concrete next step ("Run `agentweave
  start`" already does this — AgentWeave's copy is sound, only its visual weight is thin) and,
  where a populated version exists, showing what the populated shape will look like builds
  confidence faster than plain text alone.
- [Empty states — Cloudscape Design System](https://cloudscape.design/patterns/general/empty-states/)
- [Empty state UX examples and design rules that actually work — Eleken](https://www.eleken.co/blog-posts/empty-state-ux)
- [SaaS Empty State Design: 9 Patterns That Drive Activation — Pixxen](https://pixxen.com/blog/saas-empty-state-design/)

## T3 Code — direct analogues, read from sourcemaps

T3 Code (a coding-agent chat client) has no literal "overview/dashboard" screen — its home surface
is a thread list, not a project-summary page — so the useful analogues are component-level, pulled
from `index-DiDfaONg.js.map`'s `sourcesContent`:

**`ContextWindowMeter.tsx`** — closest analogue to `ContextUsageIndicator`. Notable differences:
a **circular ring gauge** (SVG `<circle>` with animated `stroke-dashoffset`, `transition-[stroke-
dashoffset,stroke] duration-500 ease-out motion-reduce:transition-none`) inside a hoverable popover,
not a linear bar — color escalates to an error/danger token only past a 90% threshold (`isOverloaded`),
otherwise a muted neutral. The popover reveals extra detail (total processed tokens, an
auto-compaction note) on hover rather than showing it all inline. AgentWeave's compact indicator is
already appropriately restrained for a small card (a ring would compete with the status dot for
attention in the same 8px space) — the actually transferable idea is **the 500ms eased transition on
value change** and **an escalation threshold color**, not the ring shape itself, and correctly
respects `motion-reduce`.

**`ThreadStatusIndicators.tsx`** — the dot+tooltip+label pattern (`ThreadStatusLabel`): a small
colored dot (`animate-status-pulse` when live), wrapped in a `Tooltip`, with the text label
optionally hidden at narrow widths (`hidden md:inline`) so the dot alone still communicates status
in a compact context. Directly validates `AgentHealthCard`'s existing dot-plus-label shape; the gap
is that AgentWeave's dot has no tooltip and no pulse-on-transition when status actually *changes*,
only a static `pulse` boolean sourced from the status config.

**`NoActiveThreadState.tsx`** — its empty state (`Empty`/`EmptyHeader`/`EmptyTitle`/
`EmptyDescription` components) centers a **title + description pair inside a generously-padded
max-width container** (`max-w-lg px-8 py-12`) rather than one plain sentence in a small box. A title
("Pick a thread to continue") separate from supporting detail reads as considered; AgentWeave's
current empty state collapses both into one run-on sentence. Structure worth adopting (title +
detail, not the exact copy or the sizing, which would violate IDENTITY.md's density clause on this
much smaller card).

**`ProviderStatusBanner.tsx`** — its container class name literally includes `alert-glass`
(`className="alert-glass relative inline-flex items-center gap-3 rounded-xl border ..."`), i.e. a
glassmorphic backdrop-blur treatment. **Explicitly not transferable** — IDENTITY.md clause 7
forbids glass outright. Read for the icon/message/dismiss layout shape only (icon left, stacked
title+message, dismiss button top-right), which is unremarkable and already close to how
`QuestionInterruptCard` is built (S6).

## Missing features to mock and flag (not implement)

1. **Icons on the workspace-summary buttons** (Tasks / Spec / Jobs) — `task_alt`/`schedule` already
   exist in `Icon.tsx`'s map; a "Spec" equivalent would need checking, not inventing a new source.
   This is closer to a styling gap than a feature, but it changes the buttons' information content
   (icon = faster recognition), so noting it here rather than assuming.
2. **A shared task-status color/label config**, used by both `OverviewPage` and `TaskCard`/
   `TasksBoard` instead of two independent hand-rolled mappings. Out of scope to *implement* here
   (mocks only, and this queue item is UI-only) but worth flagging since a mock that "fixes" the
   overview's chip colors without this shared source would just be a third independent copy.
3. **A populated-preview empty state** for the agent grid (research finding above) — showing a
   greyed-out sketch of what a populated grid looks like, not just prose. This is a genuine
   options-widening idea, not required.

## What P2 will build

`design/mocks/S7/<variant>.html`, two or three degrees of refinement per IDENTITY.md, reconstructing
the whole overview page (header, budgets, agent grid, workspace shortcuts, task summary, activity
ticker) with realistic content — several agents in different statuses (including `stalled`), a
populated and an empty variant of the agent grid, and all interactive states demonstrated
(hover/focus-visible/press on cards, buttons and chips). Both themes, per the standard protocol.
