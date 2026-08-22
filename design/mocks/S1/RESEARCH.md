# S1 research — conversation + composer + left navigation

P1 (explore) only. No mock built yet — that is P2, the next iteration. Same discipline as the
`_system` passes: read the current product and its comments first, external research second,
findings validated against `design/IDENTITY.md`'s rejection test before anything is carried
forward.

## What was read

**Current product**, in full: `ConversationView.tsx` (586 lines — the shell that hosts the
timeline, composer and panel), `AgentTimeline.tsx` (966 lines — `MessageEntry`, `WorkRow`,
`WorkBlockDisclosure`, `OutboundMessageEntry`, the working indicator, folded-turn pills),
`Composer.tsx` (370 lines) + its control row (`ComposerModelControls.tsx`, `ComposerTriggerMenu.tsx`,
`ComposerSpecControl.tsx`), `ConversationControls.tsx` (the header's resting control set — Stop,
Checkpoint, Fold all, `ContextUsageIndicator`), `ContextUsageIndicator.tsx` itself, and
`AgentOutputPanel.tsx`'s header/body/composer wrapper (lines 840–1010, to see how the pieces above
actually compose on screen). On the navigation side: `Sidebar.tsx` (510 lines — project rows,
`CompactRail`), `AgentTree.tsx` (263 lines — agent rows, conversation rows, the row menu wiring),
`SidebarItem.tsx` (134 lines — the generic nav-row primitive used by top-level and sectioned items).
Also `buttonVariants.ts` in full, to check a specific hypothesis below against the actual CSS rather
than assuming.

Every file's own comments were read, not skipped. Several encode a decision this pass must not
undo:

- **The operator bubble is deliberately neutral** (`AgentTimeline.tsx` lines 816–820): it used to be
  a 14% `--blue` wash and was removed for reading "as leftover navy against the charcoal palette."
  `--blue` is reserved for focus/selection. IDENTITY.md already names this comment explicitly — it
  is the standard, not a target.
- **The working indicator lives above the response, not in the composer** — moved there per an
  operator request (2026-08-18), and its exact gating (`runVisiblyActive`, two terminal signals) is
  tuned against several since-fixed bugs (lingering tail, stop-then-send). The mock must keep it in
  the same place and not simplify away the two-signal gating; a mock only changes how it *looks*.
- **Outbound peer messages fold; inbound peer messages never do** (design.md phase 6) — a
  deliberate asymmetry (delegation the agent sent reads like a tool call; the reply it's read for
  stays fully open). Do not fold inbound in the mock.
- **No end-of-turn "Completed" text for a normal run** — the operator explicitly doesn't want one;
  "Worked for Xs" is what replaced it. A mock must not reintroduce a closing message.
- **The row-action hover pattern already exists** (`.row-item` / `.row-action` in `index.css`,
  used by `AgentTree.tsx`'s per-agent `RowMenu` and `Sidebar.tsx`'s project rows) — hover/focus-within
  reveals an action that costs no space at rest. This is infrastructure already in the product,
  not something to invent.

## External research

Two `WebSearch` calls (chat/conversation UI: message grouping, timestamps, composer affordances;
sidebar/nav treatments for a dense tool) plus a close read of the T3 Code sourcemaps for the
directly equivalent surfaces — `MessagesTimeline.tsx`, `ChatComposer.tsx` +
`ComposerPrimaryActions.tsx` + `ComposerBannerStack.tsx`, `ChatHeader.tsx`, `ContextWindowMeter.tsx`,
`ThreadStatusIndicators.tsx`, `Sidebar.tsx`, `NoActiveThreadState.tsx`, `DraftHeroHeadline.tsx` —
extracted to `testbed/scratch/t3ref/` for reading and deleted immediately after (gitignored,
throwaway; nothing from it is quoted here at length, per IDENTITY.md's reference-material rule —
findings are restated as structure, not source).

Confirmed findings, general web research:

- Message clustering (same sender within a short window collapses to one avatar/name/timestamp)
  is the single pattern that makes a thread read as a conversation rather than a log — already
  true here in spirit (`MessageEntry` doesn't repeat a name-plus-avatar block per line within a
  turn's `WorkRow`s), but not literally applied across consecutive same-participant bubbles in a
  multi-agent exchange.
- Timestamps are conventionally unobtrusive at rest with the exact value available on demand
  (relative/short label visible, full precision behind a hover disclosure), not either extreme
  (always-verbose or entirely hidden).
- A composer's primary action should visibly distinguish idle / sendable / sending / disabled —
  four states, not two.

Confirmed findings, T3 Code (structure only, no code carried over — the stack differs and
IDENTITY.md is explicit that only structure transfers):

- **Per-message hover-reveal**: `MessagesTimeline.tsx` keeps the timestamp and a copy-to-clipboard
  button at `opacity-0`, revealed via `group-hover`/`focus-within`, with the visible label a short
  relative time and a `Tooltip` giving the exact timestamp on hover. This is the *same idiom*
  AgentWeave's own `.row-action` already uses elsewhere — applying it to message rows is extending
  an existing pattern into a surface that doesn't have it yet, not adding a new one.
- **Composer send button states**: `ComposerPrimaryActions.tsx` swaps the send glyph for a spinner
  while `isConnecting || isSendBusy`, and swaps to a filled stop-square while a run is active — three
  distinct visual states (idle / busy / running), not one icon that only ever dims.
- **Context/token usage as a compact ring + rich popover**: `ContextWindowMeter.tsx` is a small
  circular-progress button (SVG, one static track stroke + one animated value stroke keyed to
  percentage, colour flips to the error tone past 90%) that opens a popover on hover with the
  percentage, `used/max` token counts, and a note when the provider auto-compacts. It replaces what
  is, in this product, a bare linear bar with a native browser `title` tooltip.
- **Header title as an actionable element**: `ChatHeader.tsx`'s thread title is itself a button
  (rename / actions menu) with a chevron that fades in on hover — the affordance costs nothing at
  rest and appears exactly when the pointer suggests interest.
- **Banner stacking**: `ComposerBannerStack.tsx` shows only the front banner at rest with a thin
  "peeking" cap coloured by the next banner's severity, expanding the rest on hover. Uses a
  `glass` alert surface — **explicitly not reusable as-is**: IDENTITY.md clause 7 forbids glass.
  The *idea* (a stack that doesn't cost full height per item) is usable if rebuilt on flat surfaces;
  the implementation is not.
- **Sidebar row actions**: `Sidebar.tsx`'s own row actions are `opacity-0` → `group-hover`-revealed,
  absolutely positioned over the row's trailing edge so nothing shifts — confirms (rather than
  contradicts) the `.row-action` pattern AgentWeave already has; no change of direction needed here,
  only wider application.

## What's actually missing from *this* screen, specifically

Six concrete, verified gaps — not generic "make it nicer" — each checked against the live code
rather than assumed:

1. **No copy-to-clipboard on any message.** Grepped `AgentTimeline.tsx` for a copy affordance on
   `MessageEntry`/`OutboundMessageEntry`: none exists, for the agent's own text, the operator's
   bubble, or a peer bubble. `WorkRow`'s expanded body has no copy either. This is a real missing
   feature (pre-authorised note: mock it, note it, don't implement it), and the `.row-action`
   hover-reveal idiom already in the product is the natural fit — no new interaction language.

2. **`ComposerSpecControl`'s armed state has no visual effect — a wired dead state.** Verified
   directly: `ComposerSpecControl.tsx` sets `data-active={armed ? 'true' : 'false'}` and
   `aria-pressed={armed}` on the "Explore"/"Exploring" `Button`, but `buttonVariants.ts` (read in
   full) defines no `data-active` handling for any variant, and `index.css`'s only `data-active`
   rule is scoped to `.row-item` (lines 422–430), which this button doesn't carry. So today,
   pressing "Explore" only changes the *label* — "Explore" becomes "Exploring" — with no other
   visible difference. This is not a hypothetical: it is the current, verified behaviour of a
   control whose entire job is to announce a mode change. Directly fixable within the palette
   (an active-pill treatment analogous to `.row-item[data-active]`'s, built from `--surface-3`/
   `--border-hi`/`--row-active`, never `--blue` per clause 2 since this is a mode, not a
   selection).

3. **The composer send button has one visual state for two different waits.** `submitting` (this
   composer's own send-in-flight) and `disabledReason` (busy for an external reason, e.g. no agent
   chosen yet) both simply add `disabled` — greyed via the button base's `disabled:opacity-[0.64]`,
   with the same static send glyph either way. There is no busy/spinner state distinct from "can't
   send right now for some other reason." A real gap, cheaply fixed with the existing icon
   vocabulary (a spinner reusing `task-live-pulse`'s reduced-motion-gated rotation, not a new
   animation primitive).

4. **The context-usage read is a bare linear bar plus a native `title`.** `ContextUsageIndicator.tsx`
   (read in full) renders a 4px bar and a plain HTML `title` attribute for detail — no rich
   disclosure, no breakdown (measured turns, per-turn cost), nothing keyed to severity beyond the
   bar's own colour. The conversation header is exactly the surface T3's ring-plus-popover pattern
   targets, and AgentWeave already has the popover shape it would need (`ControlPill`'s listbox
   popover in `ComposerModelControls.tsx` — different content, same "small trigger, rich popover on
   demand" structure).

5. **Message timestamps carry no path to precision.** Every timestamp in `AgentTimeline.tsx` is
   `format(hubDate(entry.timestamp), 'HH:mm')` with no tooltip and no seconds/date anywhere in the
   timeline. A conversation running past midnight or one the operator returns to after a day away
   has no way to tell *which* HH:mm it was. Cheap, in-scope: a tooltip carrying the full date and
   time, the same disclosure shape T3 uses and one AgentWeave itself already uses for other
   truncated/summarised values (`ControlPill`'s own `title` pattern, one step short of a rich
   tooltip).

6. **The empty state, folded-turn pill, and work-block disclosure predate U0a's vocabulary.**
   `AgentTimeline.tsx`'s "No conversation yet" empty state (lines 181–191) is a bare icon + one line
   of text — exactly `EmptyState.tsx`'s plainest shape, not yet given a cause-specific treatment.
   The folded-turn pill (`FoldedTurnPill`) and the work-block `<details>` disclosure both toggle with
   no transition at all — an instant content jump where `foundations.html` already demonstrated a
   `--dur-fast`/`--ease` chevron-rotate and disclosure pattern this screen simply hasn't received
   yet. This is the highest-value place in the whole product to apply what U0a and U0b already
   built, since it is the screen the operator has open the most.

## What's already good and must not be redesigned

- The per-agent colour system on peer bubbles (`agentColorVars`, tint/border/accent) — already
  systematic, already what U0b's colour-coding rules table describes. Leave it.
- The operator bubble's deliberate neutrality (see above) — leave it exactly as is.
- The `.row-item`/`.row-action` hover-reveal convention in the sidebar — this pass *extends* it to
  the timeline, it does not replace it.
- The two-signal working-indicator gating and the folding model (nothing folds on its own; every
  turn folds only by the operator's own hand) — both are the result of specific, dated operator
  complaints being fixed. A mock changes their *appearance* only.
- `ComposerModelControls`' single `composerControlClassName` for every composer trigger pill — the
  one-shape-for-every-trigger discipline described in its own comment is correct and should be kept;
  the armed-state fix in finding 2 should compose with it, not replace it.

## Next

P2 — validate the six findings above against the rejection test (all already were, informally,
while writing them; a fuller line-by-line validation happens at the top of the mock-building pass)
and build `design/mocks/S1/<variant>.html` self-contained, importing the real tokens, with two or
three variants exploring degree of refinement per `screen_pass_protocol.P2_validate_and_mock`.
Cover: a message row with the hover-reveal copy/exact-timestamp treatment, the composer's fixed
armed-pill and busy-send states, and the context-usage ring-plus-popover — plus at least one
sidebar/tree row shown in both its resting and hover states so the mock demonstrates interaction,
not just rest (rejection-test clause 7). Realistic conversation content, not lorem ipsum, per the
protocol.
