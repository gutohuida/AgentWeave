# S1 rationale — conversation + composer + left navigation

Four passes across three iterations (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this
document). The main screen: `ConversationView`, `AgentTimeline` (`MessageEntry`, `WorkRow`,
`OutboundMessageEntry`), `Composer` + its control row, `Sidebar`/`AgentTree`/`SidebarItem`.

## Research → changes

Full findings and sourcing live in `RESEARCH.md`. Summary of what each of the six verified gaps
became in the mocks:

1. **No copy-to-clipboard on any message.** Extended the product's own `.row-item`/`.row-action`
   hover-reveal idiom (already used in the sidebar) onto message rows — not a new interaction
   language, wider application of one that already exists.
2. **`ComposerSpecControl`'s armed state had no visual effect** (`data-active` was set but nothing
   in `buttonVariants.ts` or `index.css` read it for a non-`.row-item` control) — the single
   strongest finding, a present-tense bug in the shipped UI, not a matter of taste. Fixed with the
   same `.row-item[data-active]` recipe (`--surface-3`/`--border-hi`), never `--blue` — this is a
   mode, not a selection (IDENTITY.md clause 2).
3. **The composer's send button collapsed "sending" and "disabled for an unrelated reason" into
   one dimmed state.** Gave it four real states: idle / ready / busy-spinner / disabled.
4. **`ContextUsageIndicator` was a bare 4px bar plus a native `title`.** Replaced with a compact
   ring in restrained, and a `ControlPill`-shaped rich popover (used/budget/turns/auto-compact
   note) in considered — reusing a popover shape the product already has elsewhere for a different
   control, not inventing a new one.
5. **Timestamps carried no path to precision.** Restrained: native `title` with full date/time.
   Considered: a matching tooltip bubble, same disclosure shape as the context popover.
6. **The empty state, folded-turn pill, and work-block disclosure predated U0a's motion
   vocabulary.** Applied `--dur-fast`/`--ease` chevron-rotate and disclosure transitions; the
   empty state gained a bordered icon tile (restrained) and, in considered, a reduced-motion-gated
   expanding-ring cue plus a one-press quick-start row against the two agents already in the tree —
   RESEARCH.md flags this as a missing *feature*, not merely unstyled, mocked per the
   pre-authorised note rather than implemented.

Two variants, not three: "restrained" (smallest fix per finding) and "considered" (the same six
fixes taken further — rich popovers, hover-lift, a live-dot, an actionable header title). A third
"expressive" reading was rejected before being built — RESEARCH.md's six findings don't carry
enough range to make a third degree meaningfully different from "considered" without inventing
decoration for its own sake, which the rejection test's clause 7 ("texture means considered
detail, not literal texture") rules out.

## What was rejected, and under which clause

- **`ComposerBannerStack`'s "peeking" glass banner stack** (T3 reference) — the *idea* (show only
  the front item, a coloured cap hints at what's behind) is usable, but T3's implementation is a
  `glass` surface. Rejected as-is under **clause 7** (no glass/gradient/shadow-as-decoration); not
  carried into either mock even in restated form, since this screen's findings didn't call for a
  banner stack at all — nothing here queues multiple simultaneous banners today.
- **A third "expressive" variant** — rejected under **clause 7**'s texture-means-detail reading and
  clause 5 ("the same application, improved"): a third degree with no new finding to justify it
  would have meant inventing motion or ornament rather than fixing something, which is a jump in
  design language, not a refinement of one.
- **Any new hue.** The considered variant's live-dot and empty-state ring both reuse `--green` (the
  same "something is live" semantic the run indicator already carries); the armed spec pill and
  every hover/selected state stay on `--surface-3`/`--border-hi`/`--row-active`. `--blue`/`--ring`
  appears only on the composer's own focus ring in both variants — checked directly against
  screenshots each pass, not just against the source. **Clause 2.**
- **Folding the inbound message branch.** `AgentTimeline.tsx`'s own comment specifies this
  asymmetry deliberately (a reply the operator is reading for stays fully open); both variants keep
  it. Not a rejection under the rejection test — a decision this pass was told not to revisit at
  all (see P1's "must not redesign" list).

## The two judgement calls from P3/P4

1. **Considered's context-usage popover overlaps the operator's own message bubble when pinned
   open.** Investigated against real popover/dropdown conventions (GitHub's notification panel, VS
   Code hover cards, any header dropdown menu) — transient content-covering on hover is the
   standard, accepted pattern for this class of control, and it clears the instant the pointer
   leaves. The demo pins it open (`data-force="hover"`) purely so a static screenshot can show its
   content at all (rejection-test clause 7); that pin is a demo artefact, not a live-usage
   condition. **No structural fix** — recorded here rather than left ambiguous. If `ControlPill`'s
   popover shape is reused for this control later, the same tradeoff already exists at every other
   site that uses it today.
2. **The live-composition panel's last message was clipped mid-line by the frame's own overflow
   boundary**, found only by screenshotting and reading the render, not from the source. Root
   cause: neither mock scrolled its `.timeline` to the newest entry on load, while the real
   product's `AgentOutputPanel.tsx` always does — its own comment states the simple case directly,
   `scrollTop = scrollHeight`, specifically because a conversation must show its newest entry
   regardless of window focus. **Fixed** in both variants: `.timeline` elements are scrolled to
   `scrollHeight` in the mocks' existing `<script>` block, immediately after the theme-toggle
   handler. Re-verified by cropping the same region before and after — the tail message and the
   working indicator now render fully above the composer in both themes, both variants.

## What's already good and was left alone

Carried forward verbatim from `RESEARCH.md`'s P1 findings, and confirmed still true after building:
the per-agent bubble colour system, the deliberately neutral operator bubble (the exact comment
IDENTITY.md cites), the `.row-item`/`.row-action` hover-reveal convention, the two-signal working-
indicator gating, and the fold-nothing-automatically model. None of these were touched — both
mocks change appearance only, never the interaction model those comments protect.
