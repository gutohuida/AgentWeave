# S2 research — task board + task cards

The operator's own words, verbatim, from `STATE.json`'s queue: *"The cards look very plain, with no
texture, no animation or fine details just a box with things written on it and the task board the
same."* Named explicitly as the worst offender. This pass reads the current code end to end before
touching anything, per `screen_pass_protocol`.

## What was read

- **`TaskCard.tsx`** (full, including comments). Encodes several deliberate decisions worth naming
  up front so a mock doesn't undo them: `isBlocked` gets **purple**, not amber, because purple/amber
  here are opposites (an agent that dropped work vs. one that correctly stopped and asked) and
  colouring them alike "would teach the operator to read the signal that means 'someone did the
  right thing' as a problem." `has_open_divergence` renders an amber "Stalled" pill — renamed from
  an earlier label after the operator asked *"what is a dropped task?"* on 2026-08-10. `isLive`
  (an agent actually running right now, from `assignee_status === 'running'`) gets a pulsing green
  ring (`task-live-pulse`, design D12) that is explicitly never the *only* carrier of that fact — the
  "running" status pill nearby says the same thing in words, and the ring drops out cleanly under
  `prefers-reduced-motion` while the static box-shadow itself stays. F5 moved every actionable control
  (status transitions, full description, requirements) into `TaskDetailDrawer`; the card itself is a
  summary now, opened by clicking anywhere on it.
- **`TasksBoard.tsx`** (full). Seven columns (`blocked` deliberately has none of its own — R3, folded
  into "In Progress" as a card treatment instead, because giving it a column both widens an
  already-crowded board and makes cards travel out-and-back for no real progress). Column headers are
  `sticky` with a documented `-12px` offset hack, added directly in response to an operator complaint
  on 2026-08-10 ("when I scroll down I lose what each column means") — any header restyling has to
  keep this working. Assignee filter chips, a collapsed-by-default "Rejected" section, and a
  requirement-filter banner for cross-tab navigation from the spec tab (F4).
- **`TaskDetailDrawer.tsx`** (full). A centred modal over a dimmed backdrop, not a side panel —
  this reverses the file's *original* right-edge geometry on the operator's own explicit 2026-08-17
  direction, quoted in the file: *"I don't want a ticket that takes the whole screen like navigating
  to a new screen. Just that central popup that floats in the middle."* Only the body scrolls
  (design D8); the field grid, status-transition menu (constrained to the allowed-transitions set so
  an illegal move is never offered), the blocking-reason capture flow, the divergence-policy chooser,
  and the requirement links (with rejection reasons shown inline) are all already considered UI, just
  under-styled.
- **`TaskIntegrationNote.tsx`** (full). Renders merge/skip/fail outcomes as plain coloured `<p>`
  text with no container — see finding 8 below.
- **`Badge.tsx`** (full) — found a real bug while reading it, not just a styling gap; see finding 1.
- **`hub/ui/src/index.css`** — confirmed the exact tokens available: `--row-hover/-active/-selected`,
  `--lift-hi`/`--press-lo`, `--dur-fast/base/slow`, `--ease`, the `--radius*` scale, the 8-colour
  `--agent-*` scale, and the `task-live-pulse` keyframe (already exists, already gated on
  `prefers-reduced-motion`, must not be redesigned).

## External research

- **Kanban card texture/motion trends**: hover feedback should read as depth (shadow expansion or a
  slight lift/scale) and a background shift, not just a border recolour; hover can reveal detail
  without an extra click; explicit states — hover, focus, dragging, completed — are expected.
  ([Layout Scene](https://www.layoutscene.com/card-ui-design-patterns-guide-2026/),
  [BricxLabs](https://bricxlabs.com/blogs/card-ui-design-examples))
- **Jira/Asana**: the baseline information a card carries — title, status, assignee, date — is
  already all present on AgentWeave's card; the gap isn't information, it's how that information is
  differentiated visually.
  ([Miro on Jira cards](https://miro.com/blog/jira-cards-visual-project-management-case/),
  [Asana board view](https://www.usecarly.com/blog/how-to-use-board-view-in-asana/))
- **Linear's issue rows**: near-black surfaces, **hairline borders and inset shadows instead of drop
  shadows** for depth, a priority glyph + muted mono id + status ring + coloured label pills + a
  tinted avatar. This is close validation, not a new direction — AgentWeave's charcoal/hairline-border
  identity (`IDENTITY.md`) is already the same family; the gap is that AgentWeave's badges are all one
  undifferentiated pill shape rather than the icon/glyph-plus-pill mix Linear uses to make a row
  scannable by shape, not just by reading text.
  ([Identity Forge on the Linear design system](https://identityforge.io/learn/linear-design-system))
- **Drag-and-drop kanban practice**: drop zones sized generously enough to not require precision;
  the destination column highlights once a card is dragged most of the way there; the interaction
  has explicit microstates (idle → hover → grab → move → drop); keyboard/ARIA equivalents
  (`aria-grabbed`, arrow-key movement) matter for accessibility.
  ([LogRocket](https://blog.logrocket.com/ux-design/drag-and-drop-ui-examples/))
- **T3 Code** (structure only — nothing quoted at length or carried over, per `IDENTITY.md`'s
  reference-material rule; files extracted to `testbed/scratch/t3ref/` for reading and deleted
  immediately after):
  - `ProposedPlanCard.tsx` — a `rounded-[24px]` card (the same 24px AgentWeave already reserves for
    `--radius-content`), a header row of `Badge + truncated title + overflow-menu icon button`, and a
    collapsed body with a bottom fade-out gradient plus an explicit "Expand/Collapse" button rather
    than relying on a bare chevron. The fade-out-into-a-secondary-action idiom is a candidate for a
    task card whose description or requirement list runs long.
  - `ComposerPreviewAnnotationCards.tsx` — a compact "chip card": a thumbnail or icon square on one
    edge, a label, and a row of small `icon + count` stats (`TargetStat`), with a corner remove button
    that only appears on hover (`group`/`group-hover`) and a subtle `scale-[1.03]` on the thumbnail on
    hover. The `icon + count` stat idiom maps directly onto a task's own counts (requirement links,
    acceptance criteria, deliverables) that today are only visible after opening the drawer.

## What's actually missing from *this* screen, specifically

Concrete, code-verified — not "make it nicer" notes.

1. **The priority badge is a real bug: it always renders neutral grey, never colour-coded.**
   `TaskCard.tsx:309` and `TaskDetailDrawer.tsx:257` both call `<StatusBadge status={task.priority} />`,
   but `Badge.tsx`'s `STATUS_STYLES` map (`Badge.tsx:29-38`) is keyed by *task status* values
   (`pending`, `in_progress`, `under_review`, …) — it has no entries for `low`/`medium`/`high`/
   `critical` (confirmed against the Hub's own source of truth,
   `hub/hub/schemas/tasks.py:26`: `_PRIORITIES = ["low", "medium", "high", "critical"]`). Every
   priority value falls through to `STATUS_STYLES.pending ?? NEUTRAL`, so a `critical` task and a
   `low` one render an *identical* grey pill today. This is exactly the "colour coding" the operator
   asked for in `STATE.json`'s brief, and it isn't a styling opinion — it's a dictionary lookup miss.
   Worth fixing in the mock (a real `PRIORITY_STYLES` map) and flagging as a genuine product bug in
   `RATIONALE.md`, separate from the visual-refinement work.
2. **No elevation or lift on card hover.** The only feedback today is a border-colour swap via
   inline `onMouseEnter`/`onMouseLeave` handlers (`TaskCard.tsx:111-116`) — not even a CSS `:hover`
   rule. `--lift-hi`/`--press-lo` and a considered elevation scale (built in `_system/foundations.html`)
   exist and are unused here, on the one surface in the product where "this whole box is a button"
   (F5) is the entire interaction model.
3. **No press/active state.** Nothing distinguishes mousedown from hover; clicking to open gives zero
   transient feedback before the drawer appears.
4. **Column empty states are bare.** `TasksBoard.tsx`'s per-column body renders nothing when a column
   has zero tasks — just the sticky header showing "0" over blank space. `EmptyState` exists and is
   used for the whole-board case (line 77) but never per-column, and a 7-column board will routinely
   show several empty columns at once.
5. **No drag-and-drop — a missing feature, not a style gap.** Confirmed by reading both files fully:
   no `draggable`, no dnd library import anywhere in `TasksBoard.tsx` or `TaskCard.tsx`. Every status
   change routes through the drawer's status menu or the card's "start work" menu. This is the single
   most standard kanban interaction and it doesn't exist. Per `pre_authorised`, worth mocking and
   noting — not implementing.
6. **The badge row is all same-shaped pills — nothing scannable by shape.** Status, priority,
   assignee, assignee-status and assigner all render as the same rounded pill differing only by
   colour/text. No icons anywhere in the row (`Icon` is the sanctioned vocabulary per
   `_system/controls.html`; none is used here), so reading a column means reading words, not
   recognising shapes — the opposite of what the Linear-style research above shows.
7. **Requirement chips and informational badges share identical visual weight.** Both are
   `text-[10-11px]` pills on `var(--surface-3)`, so a chip that navigates to a specification
   (`TaskCard.tsx:192-219`) and a chip that's purely informational ("from: builder",
   `TaskCard.tsx:360-376`) don't read as different *kinds* of thing at a glance — only on hover/click
   does the difference become apparent.
8. **`TaskIntegrationNote` breaks the card's own pattern.** Every other fact on the card is a pill or
   a bordered block; the merge outcome — arguably the highest-stakes fact on an *approved* card, since
   it answers "did the work actually land" — is a bare `<p>` with only a text colour
   (`TaskIntegrationNote.tsx:53-64`). No icon, no background, no border.
9. **No `tabular-nums` on the card's relative timestamp** (`TaskCard.tsx:380-382`), unlike other
   numeric spots in the product that already use it — `IDENTITY.md` names this exact micro-detail as
   present-but-underused.
10. **The description clamp (`line-clamp-2`) and the drawer's fade-out-and-expand idiom seen in T3's
    `ProposedPlanCard` don't currently exist together** — the card hard-truncates with no visual cue
    that more exists beyond the clamp itself (no gradient fade, no "…" affordance beyond the browser's
    own line-clamp ellipsis).

## What's already good and must not be redesigned

- The purple-for-blocked / amber-for-stalled distinction (`TaskCard.tsx:79-85`) — deliberate,
  documented, semantically opposite signals. Don't recolour or merge them.
- The "Stalled" wording and its amber tone (`has_open_divergence`) — already renamed once after a
  direct operator complaint about unclear jargon (2026-08-10). Don't rename or retint it again.
- The live-pulse ring (`task-live-pulse`, design D12) — already respects
  `prefers-reduced-motion` (the static box-shadow survives, only the animation drops), already never
  the sole carrier of the "running" fact. Extend the same *idiom* — a static cue plus an optional
  animation layer — to other states rather than inventing a second motion language.
- Sticky column headers with the `-12px` offset hack — fixed in direct response to the operator
  losing column context while scrolling. Any header restyling must keep this working.
- The centred-modal drawer geometry — reversed from an earlier side-panel design on the operator's
  own explicit 2026-08-17 direction. Do not reintroduce a side panel here.
- `blocked` folded into "In Progress" rather than an 8th column (R3) — do not give it a column.
- F4's requirement chips and F5's "card is a summary, drawer is where the work happens" split — both
  are considered decisions grounded in real usage feedback, not accidental omissions.

## Next

P2: validate every finding above against `IDENTITY.md`'s rejection test (in particular clause 5 —
"the same application, improved"), then build `design/mocks/S2/<variant>.html` — two or three
variants exploring degree of refinement, with realistic task content spanning all seven statuses plus
a blocked card, a stalled/divergent card, and an approved card with a merge outcome, in both themes.
