# S8-agents rationale — the agent roster and its settings

Second `S8` sub-screen (jobs closed 4/4 first; logs+activity and the command palette remain).
Four passes (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this document).

## The queue item's premise was wrong, and mocking started from the correction

The queue named `AgentsPage`, `AgentCard`, `AgentSettingsPage`. Two of the three do not render:
there is no `AgentsPage.tsx` at all (the roster lives inline in the project rail, not a standalone
grid), and `AgentCard.tsx` is dead code — real git history, zero live importers, superseded when
the roster moved into the rail-tree shape and never deleted. Only `AgentSettingsPage.tsx` is a
current destination. Rather than mock components nothing renders, this pass mocked the surfaces an
operator actually opens today: **`AgentTree.tsx`** (the rail rows, embedded in `Sidebar.tsx`) and
**`AgentSettingsPage.tsx`** together with **`AgentSettingsControls.tsx`** (the field widgets) and
`Sidebar.tsx`'s `agentSettings` nav branch. `AgentCard` is recorded here as a dead-code finding, not
mocked as a living screen.

## Research → three findings, one of them a missing feature

Full sourcing lives in `RESEARCH.md`: the components read in full including their comments (two
deliberate non-bugs found and left alone — `Isolation`'s read-only-by-design row, and
`unavailable_reason` staying a plain `<p>` rather than `role="alert"` because "no branch" is no
longer a blocking error); two `WebSearch` passes (presence/roster row patterns; settings-navigation
patterns at scale); and two T3 Code sourcemap analogues (`SettingsSidebarNav.tsx` for icon-per-
section at a comparable seven-section count, and `AgentsPanel.tsx`'s `AgentRow` for the
fixed-height-row discipline — *"Agent rows reserve three fixed lines for identity, activity, and
metrics; changing data must never change their height"*).

1. **Agent identity data dropped from the rail.** Model, message count, context usage and
   last-seen all exist on `AgentSummary` and are computed today only for the dead `AgentCard` — the
   live tree row shows none of it. An operator scanning the rail cannot tell which agent is near its
   context limit or which model an agent runs without opening it. Mocked as `considered.html`'s
   fixed two-line row (T3 `AgentRow` precedent), returned as a **variant axis, not shipped** — the
   product decision of whether the rail wants this data back belongs to the operator, not a mock.
2. **`AgentTree` rows are hand-rolled markup that doesn't reuse `SidebarItem`**, one component away,
   which already carries a considered hover/active language (animated left indicator, token-driven
   backgrounds) the tree never adopted. Both mocks give the row that same recipe.
3. **`AgentSettingsControls`' fields are raw native HTML** (`<select>`, `<input type=checkbox>`,
   `<textarea>`) with inline styles, never touching `_system/controls.html`'s (U0b) vocabulary built
   specifically for this gap. Both mocks swap in `.ctl-select`/`.ctl-switch`/`.ctl-textarea`
   verbatim — a literal substitution, not a redesign.

Two ideas were mocked as **missing features and flagged, not implemented**, per the
pre-authorization: field-level settings search (T3 ships it at the same seven-section count;
AgentWeave's plain list does not) and small leading icons per settings-nav section (present in T3's
equivalent, absent here — the icon addition itself *was* mocked since it's cheap and purely visual,
the *search* was not, since it's a real feature).

## What was rejected, and under which clause

Nothing from `RESEARCH.md`'s three core findings failed validation — all three passed
`IDENTITY.md`'s rejection test in P2 (recorded there in full): existing `--agent-1..8` dots and
`ContextUsageIndicator`'s own amber/red thresholds (clause 1), the existing `SidebarItem` hover/
active recipe (clauses 1/3), and U0b's already-validated control vocabulary (clauses 1/4). Nothing
was discarded outright. The one thing narrowed rather than rejected: full field-level settings
search was *scoped down* to icons-only for this mock, since building real search behaviour is a
feature this queue item's mandate doesn't cover — noted above, not silently dropped.

**Two variants, not three**, per the same reasoning S7 recorded: this surface is two distinct
targets (rail row, settings pane) rather than one focal interaction, and a third "expressive" degree
was judged to restate `considered.html`'s ideas with more adjectives rather than show a genuinely
different degree at this surface's scale.

## P2 — a self-inflicted bug, corrected in the open

The first mock draft named its own settings-row scratch classes `.settings-row`/
`.settings-row-control` — real, live classes already defined in `hub/ui/src/index.css:471-503`
(`display:flex`, `min-height:76px`, `flex:none; min-width:180px` on the control). Because the mock
imports the real stylesheet, those rules applied alongside the mock's own and fought unpredictably
per row, collapsing one `<select>` to roughly a third of its sibling's width despite identical
markup. `RESEARCH.md`'s own earlier claim ("not present in index.css") was wrong and is corrected
in-place rather than silently fixed, so a later pass doesn't repeat the same false premise. Renamed
to `.arow`/`.arow-control` (grepped `index.css` first to confirm no collision) and reverified both
select boxes render at the intended shared width.

## P3 — a real `uishot.py` compatibility bug, fixed and generalized

Both mocks booted `data-mode="dark"` with a bare, unlabelled toggle. `scripts/uishot.py`'s dark
capture path looks for a button whose accessible name is exactly `"Switch to dark mode"` — the real
app's own convention (`ProjectHeader.tsx`: `aria-label={mode === 'light' ? 'Switch to dark mode' :
'Switch to light mode'}`) — and clicks it once; there is no light-mode-toggle path, since the real
app always boots light. Against a mock that already booted dark with no matching label,
`--theme dark` silently captured the (already-dark) default with nothing to click, and `--theme
light` had no route to light at all — the tool would have appeared to work while quietly capturing
the same theme twice. Fixed by matching the real app exactly: both mocks now default
`data-mode="light"`, and `toggleMockTheme()` flips `aria-label`/`title` the same way
`ProjectHeader.tsx` does. Verified `py -3.11 scripts/uishot.py --theme light|dark` against both
files **unmodified** — this closes the "decide once" question raised in P2 for every later S8
sub-screen: default light, label the toggle the real app's way, and no mock needs a one-off
Playwright workaround again.

Re-screenshotted all four captures (2 variants × 2 themes) after the fix and ran a fresh clause-by-
clause critique against `IDENTITY.md` (full detail in `RESEARCH.md`'s "P3 — iterate" section):
tokens-only held (two `rgb()`/`rgba()` shadow-alpha literals per file, matching `index.css`'s own
idiom at lines 321/535/548, not chromatic colour); durations held (the staggered row-entrance delay
and skeleton shimmer aren't `--dur-*` values, but neither is the app's own only other looping
animation, `task-live-pulse` at a hardcoded `2.4s` — the scale reads as scoped to discrete
transitions, not ambient ones); radius held (`.ctl-switch`'s pill shape traces to U0b's already-
validated pattern, reused not invented). No clause failures.

## P4 — real interaction and narrow-viewport verification, no defect found

P2 and P3 both worked from screenshots read by eye. P4 used a different method — actually driving
the page — specifically because that's the class of bug static review structurally can't catch (S7
found a real overflow bug this way; this pass looked for the same class of thing here and confirmed
there wasn't one, which is itself the point of running the check rather than assuming clean).

- **Real keyboard `Tab` walk**, both files, checking `document.activeElement` after each press
  rather than reading a `:focus-visible` rule off a screenshot: every interactive element in tab
  order — theme toggle, expander buttons, agent rows, row-menu buttons, the add-agent row, the
  settings-back button, every settings nav item — received the visible focus ring
  (`box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--ring)`) exactly as declared. No element was
  skipped, no ring failed to render.
- **420px narrow-viewport reflow check** (the same width S6/S7 used as precedent), both files:
  `document.documentElement.scrollWidth` measured exactly `420` in both — no overflow. The rail
  frame (250px) and the settings shell (`max-width: 940px` but built on `flex`/`min-width: 0`
  throughout) both compress cleanly.
- **Real mouse-hover check** on the row-menu button's opacity reveal (`.agent-row-group:hover
  .row-menu-btn { opacity: 1 }`): an initial fast read returned a false alarm (opacity still `0`
  immediately after `Locator.hover()`), traced to the check itself racing the `--dur-fast`
  transition rather than a mock defect — a `getComputedStyle` read after a short wait (or a plain
  `mouse.move` to the element's centre with a settle delay) showed the reveal completing correctly
  (opacity ≈ 0.96–1.0) in both files. Recorded here so a later screen's P4 doesn't mistake the same
  timing artifact for a real bug.
- **Toggle click, both files**: clicking `.theme-toggle` flips `data-mode` to `dark` and the
  `aria-label` to `"Switch to light mode"`, confirming the P3 fix works via a real click, not just a
  declared handler.

No fix was needed this pass. Verification scripts and screenshots were deleted after use, per this
run's established no-committed-screenshots precedent (`.gitignore`'s blanket `*.png` rule) —
`git status --short` before committing showed only `RATIONALE.md` (new) and `index.html` (this
screen's entry added).

## Verification summary across all four passes

- P2: Playwright loading each file via `file://`, both variants × both themes, full-page screenshots
  read and checked against the rejection test; one real CSS-collision bug found and fixed.
- P3: `scripts/uishot.py`'s real capture path exercised end to end (not a one-off script), a genuine
  tool-compatibility bug found and fixed at the mock, and a fresh clause-by-clause critique with no
  failures.
- P4 (this pass): real keyboard-driven focus-visible walk, a real 420px-viewport reflow check, and a
  real mouse-hover interaction check — no defect found, one false alarm in the check itself
  correctly diagnosed and ruled out rather than "fixed" against nothing.

**S8-agents is now fully done — all four passes (P1–P4) complete and verified.**
