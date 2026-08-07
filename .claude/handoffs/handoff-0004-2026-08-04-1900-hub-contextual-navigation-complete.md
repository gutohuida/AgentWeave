# Handoff 0004: Hub contextual navigation — implementation complete and committed

**Date:** 2026-08-04T18:50:12+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `8526bea`
**Model:** claude-sonnet-5[1m]
**Agent:** Claude Code
**Iteration commits:** `89b837e..8526bea` (one commit: `8526bea` "Hub contextual navigation:
interaction feedback, rail sections, conversation surface")
**Previous handoff:** `.claude/handoffs/handoff-0003-2026-08-04-1753-hub-contextual-navigation.md`
**Status:** chunk complete

## Goal

Finish implementing the approved change `openspec/changes/2026-08-04-hub-contextual-navigation/`,
which handoff-0003 left roughly 60% done with a failing test suite. The change: make the left rail
contextual (project mode vs. configuration section mode), give every activatable element real
hover/press/selected feedback by adopting the `Button` primitive that had sat unused, rebuild the
agent conversation surface against the approved mock, and re-lay the eight environment screens as
titled settings-row sections.

The *why*: `2026-08-04-hub-ui-mock-alignment` (commit `89b837e`) recomposed only the shell.
Operator review found the conversation screen untouched, configuration reachable from two places
with its navigation stranded inside the content area, and — the sharpest problem — that
`hub/ui/src/components/ui/button.tsx` defined a complete control primitive that no component
imported, leaving nearly every control in the product visually inert under the pointer.

## Current state

**All seven of handoff-0003's "Next steps" are done, verified, and committed.** The suite that was
red at the start of this session (`1 failed | 374 passed`) is green (`376 passed`), and everything
handoff-0003 flagged as missing is now either implemented or explicitly and honestly left unchecked
in `tasks.md` with the reason recorded.

- **The failing test is fixed.** `App-mount.test.tsx`'s environment-tab test now opens configuration
  via the rail gear (`getAllByRole('button', { name: /^Configure /i })[0]`) instead of the removed
  `project-tab-environment` tab, then proceeds through the same `environment-section-*` assertions
  as before — those ids now live in `Sidebar`, not the content column.
- **Task 4.3 (the largest gap) is done.** All seven remaining environment panels —
  `QualityHealthPanel`, `InstructionsPage`, `RunnersPage`, `ChartersPage`, `WorktreesPanel`,
  `DiagnosticsPanel`, `AccountingPanel` — are ported to `SettingsSection`/`SettingsRow`
  (`hub/ui/src/components/environment/SettingsSection.tsx`, unchanged from handoff-0003, used as
  the shared primitive). Every button text, aria-label, and role the existing tests assert on
  (`runnersUi.test.tsx`, `chartersUi.test.tsx`, `accountingPresentation.test.tsx`) was preserved
  exactly — those three test files pass unmodified.
- **Task 2.5 (source contract) is done.** `hubVisualLanguage.test.ts` gained a new test,
  `'adopts the Button primitive in the shell and conversation controls rather than hand-rolled
  buttons'`, that `readFileSync`/`?raw`-imports `App.tsx`, `Sidebar.tsx`, `ProjectHeader.tsx`,
  `ProjectTabs.tsx`, `ConversationControls.tsx`, and `Composer.tsx`, asserts none contains a
  `<button` opening tag carrying its own `style={…}` attribute (regex:
  `/<button(?:(?!>)[\s\S])*?style=\{/`), and asserts each of the five (excluding `App.tsx`, which
  uses `Button` only incidentally) imports from `@/components/ui/button`.
- **Task 6.1 (spec supersession) is done.** A note block was inserted into
  `openspec/changes/2026-07-30-hub-native-experience/specs/hub-visual-language/spec.md`, directly
  under the "Navigation lists live entities; project views are reached in the content area"
  requirement, explaining that configuration (the `environment` destination) is now reached via the
  rail's section mode rather than the content area, distinguishing it from *work* views
  (tasks/specs/jobs/activity) which are unaffected. Two scenario texts in that same requirement were
  also edited in place to reflect the split (`environment` removed from the "reached within the
  content area" list; the "Adding a view does not crowd navigation" scenario scoped to *work* views).
  Both `2026-07-30-hub-native-experience` and `2026-08-04-hub-contextual-navigation` pass
  `openspec validate --strict`.
- **Task 2.4 (the open-ended audit) is done, with an important finding.** The actual defect pattern
  is a `<button>` that pins its own `background` via **inline** `style={{ background: … }}`: inline
  style specificity beats *any* stylesheet rule regardless of selector specificity, including the
  global `:hover` fill rule task 1.2 (from handoff-0003) added — so a hand-rolled button with an
  inline background stays visually inert under the pointer even after that CSS fix landed. A
  systematic grep for `<button[\s\S]*?style=\{\{[\s\S]*?background` across `hub/ui/src` found 23
  candidate files. Reading each one individually (many were false positives — the pattern matched a
  *descendant* element's background, not the button's own, or the background was `'none'`/decorative
  and intentionally chromeless) narrowed it to genuine defects, which were fixed in: `OverviewPage`
  (task-status filter pills), `AgentCreateDialog` (Cancel/Create agent), `TasksBoard` (assignee
  filter chips), `SpecPage` (Refresh spec, Repair manifest, Dismiss navigation message),
  `SpecChatPane` (send button), `SetupModal` (Connect submit — the mode/theme swatches were left
  alone; they're semantic color pickers with their own outline+scale selected-state, not inert),
  `ComposerAgentSelector` (target-agent trigger and the agent option rows), `JobCard` (Run/Pause/
  Resume/Confirm/Cancel/Delete/expand), `JobsPage` (New Job, filter tabs, Create First Job),
  `JobForm` (close, cron-example chips, Cancel/Create Job), `SpecWorkspace` (Expand/Collapse chat),
  `SpecNavigator` (document tree rows, search trigger, library/history tabs, page-outline rows — all
  converted to the shared `.row-item` treatment since they're genuinely row-list UI),
  `LogsView` (Refresh, Live/Paused toggle, severity and category filter chips — the chips keep their
  distinct semantic active colors pinned inline by design; only the *inactive* resting state was
  freed from its inline background pin so hover works), `QuestionInterruptCard` (Answer/Dismiss —
  Answer intentionally kept outside the `Button` primitive, see Key decisions), and `ErrorBoundary`
  (Try again). **Seven components were found to be dead code** — `AgentsPage`, `AgentCard`,
  `AgentDetailPanel`, `AgentActivityTab`, `StatusBar`, `MessagesFeed`, `MessageCard` — none are
  imported from `App.tsx` or any live component (confirmed by `grep -rn` for each name). They were
  left untouched: fixing unreachable code has no user-facing effect and the search cost was already
  paid. `AgentInfoTab` (live, used by `ConversationControls`'s "Agent details" dialog) and
  `AgentTimeline` were checked and already met the bar.
- **`tasks.md` now matches reality.** Every task from section 2–6 that is actually done is checked;
  three (4.5, 4.6, 4.7) are explicitly left unchecked with the reason inline — see "Not done" below.
  This required correcting the file the prior session (whoever wrote the code before handoff-0003
  reconstructed the record of it) never updated at all.

### Not done — recorded honestly, not silently dropped

- **4.5** (section fills the content region, no dead area at a wide viewport) — not confirmed; needs
  a live browser at a wide viewport. Left a watch item in `tasks.md`: `App.tsx`'s
  `workspace-content` wrapper caps at 1180px while `.settings-section-rows` caps at 920px — worth
  checking whether that produces a visible gap.
- **4.6** (numeric constraints still reject invalid input with an explanation once steppers are
  gone) — not confirmed; native HTML `required`/`min` validation UI does not reliably reproduce
  under jsdom, so this needs a live browser too.
- **4.7** (save success and save failure both reported in the section) — only `ProjectSettingsPanel`
  does this uniformly (`role="status"`/`role="alert"` in-section, from handoff-0003's work).
  `RunnersPage`/`ChartersPage` report create/delete errors via their own dialog or inline alert but
  not a section-level success message; `InstructionsPage` has its own separate "Saved" indicator;
  `AccountingPanel`'s Apply/Disable buttons report no outcome at all. Left unchecked rather than
  claimed, since it is not true across all eight sections.
- **7.6, 7.7, 7.8** (live browser checks: 1280×800/390×800 both themes, reduced motion, keyboard-only
  pass) — **no browser was launched this session.** No browser automation tool was available in this
  environment. This is the largest remaining gap between "tests pass" and "actually verified to
  look and behave correctly."
- Two **watch items** noted in handoff-0003 were not re-investigated this session (not blocking, but
  worth a look during the live pass): (1) `.conversation-composer-surface`'s box-shadow values
  (`0 20px 52px rgba(2,5,18,0.28)` and an inset highlight) are hardcoded for dark and untested in
  light mode; (2) `ProjectTabs` combines the `Button` primitive with the `.row-item` class — the
  cascade analysis in handoff-0003 concluded the *active* tab still shows correctly (fill + weight),
  but the *inactive* tab's text color changed from `--text-3` to full `--text` and the old blue
  underline is gone. This is a design judgment for the live pass, not something fixed blind.

## Files touched

All committed in `8526bea`. Cross-checked against `git show --stat 8526bea` — 57 files, +2776/-1369
(the previous session's uncommitted work plus this session's additions and the rebuilt bundle).

**New this session (on top of what handoff-0003 already listed as done):**

- `hub/ui/src/__tests__/App-mount.test.tsx` — one-line fix to the environment-tab test; finished.
- `hub/ui/src/__tests__/hubVisualLanguage.test.ts` — new Button-adoption source contract; finished.
- `hub/ui/src/components/quality/QualityHealthPanel.tsx` — ported to `SettingsSection`; finished.
- `hub/ui/src/components/instructions/InstructionsPage.tsx` — ported; finished.
- `hub/ui/src/components/runners/RunnersPage.tsx` — ported, list rows de-carded, form buttons on
  `Button`; finished. Removed the now-dead `btnBase` style-object constant.
- `hub/ui/src/components/charters/ChartersPage.tsx` — same treatment as `RunnersPage`; finished.
- `hub/ui/src/components/environment/WorktreesPanel.tsx` — ported (still a placeholder panel; no
  real content to show yet); finished.
- `hub/ui/src/components/environment/DiagnosticsPanel.tsx` — ported; finished.
- `hub/ui/src/components/accounting/AccountingPanel.tsx` — ported, token-budget row uses
  `SettingsRow` with Apply/Disable on `Button`; finished.
- `openspec/changes/2026-07-30-hub-native-experience/specs/hub-visual-language/spec.md` —
  supersession note + two scenario edits; finished.
- `openspec/changes/2026-08-04-hub-contextual-navigation/tasks.md` — checkboxes reconciled with
  reality; finished.
- `hub/ui/src/components/overview/OverviewPage.tsx` — task-status filter pills de-inlined to
  `.row-item` + Tailwind hover; finished.
- `hub/ui/src/components/agents/AgentCreateDialog.tsx` — Cancel/Create agent → `Button`; finished.
- `hub/ui/src/components/tasks/TasksBoard.tsx` — assignee filter chips → `.row-item`; finished.
- `hub/ui/src/components/spec/SpecPage.tsx` — Refresh spec, Repair manifest, Dismiss nav message →
  `Button`; finished.
- `hub/ui/src/components/spec/SpecChatPane.tsx` — send button → `Button`; finished.
- `hub/ui/src/components/layout/SetupModal.tsx` — Connect submit → `Button`; mode/theme swatches
  deliberately untouched; finished.
- `hub/ui/src/components/agents/ComposerAgentSelector.tsx` — trigger and option rows fixed;
  finished.
- `hub/ui/src/components/jobs/JobCard.tsx` — all action buttons → `Button`; removed dead `btnSmall`
  constant; finished.
- `hub/ui/src/components/jobs/JobsPage.tsx` — New Job / Create First Job → `Button`, filter tabs →
  `.row-item`; removed dead `btnBase` constant; finished.
- `hub/ui/src/components/jobs/JobForm.tsx` — close/Cancel/Create Job → `Button`, cron-example chips
  → `.row-item`; finished.
- `hub/ui/src/components/spec/SpecWorkspace.tsx` — chat expand/collapse → `Button`; finished.
- `hub/ui/src/components/spec/SpecNavigator.tsx` — document tree rows, search trigger, mode tabs,
  outline rows all converted to `.row-item`/`data-active`; `rowBase` trimmed from a full inline
  style object down to `{ fontSize: 12 }` since `.row-item`'s CSS now supplies layout; finished.
- `hub/ui/src/components/logs/LogsView.tsx` — Refresh/Live toggle → `Button`/`.row-item`; severity
  and category chips keep semantic active colors inline, inactive resting state freed of its inline
  background pin; finished.
- `hub/ui/src/components/questions/QuestionInterruptCard.tsx` — Dismiss → `Button`; Answer kept as a
  plain `<button>` with Tailwind `bg-[var(--amber)] hover:brightness-110` (see Key decisions);
  finished.
- `hub/ui/src/components/common/ErrorBoundary.tsx` — Try again → `Button`; finished.
- `hub/hub/static/ui/index.html`, `hub/hub/static/ui/assets/index-DHU9fHCd.js` (new),
  `hub/hub/static/ui/assets/index-DYT0Hhdp.css` (new) — rebuilt production bundle, superseding
  handoff-0003's uncommitted `index-DMlXiq3k.js`/`index-BBRjPn8j.css`, which are removed;
  `index-B6UnVD_F.js`/`index-BL6FHekx.css` (the bundle actually committed in `89b837e`) also removed
  as obsolete; finished and confirmed current via `pytest hub/tests/test_ui_staleness.py -q`.

**Everything handoff-0003 already listed as "finished" from the prior session** (`index.css`,
`navigation.ts`, `Sidebar.tsx`, `App.tsx`, `ProjectHeader.tsx`, `ProjectTabs.tsx`,
`AgentOutputPanel.tsx`, `ConversationControls.tsx`, `Composer.tsx`, `AgentTimeline.tsx`,
`Icon.tsx`, `SettingsSection.tsx`, `ProjectSettingsPanel.tsx`, `projectRail.test.tsx`,
`conversationControls.test.tsx`, `agentCreationUi.test.tsx`, and the full
`openspec/changes/2026-08-04-hub-contextual-navigation/` proposal/design/specs) is unchanged this
session and is now part of the same commit.

**Confirmed dead code, deliberately not touched (see Task 2.4 audit above for why):**
`hub/ui/src/components/agents/AgentsPage.tsx`, `AgentCard.tsx`, `AgentDetailPanel.tsx`,
`AgentActivityTab.tsx`, `hub/ui/src/components/layout/StatusBar.tsx`,
`hub/ui/src/components/messages/MessagesFeed.tsx`, `MessageCard.tsx`.

**Left uncommitted, not part of this change** (unchanged from handoff-0003's list, still true):
`.claude/handoffs/LATEST.md` (staged delete), `.claude/handoffs/handoff-0001-*` (staged rename),
`Makefile`, `scripts/sync_skills.py`, `.claude/skills/{handoff,resume,review-iteration}/SKILL.md`,
`src/agentweave/templates/skills/{handoff,resume}.md`, `tests/test_handoff_resume_templates.py`,
`data/agentweave.db`, five older untracked handoff files, `.claude/handoffs/reviews/`, and
`openspec/explorations/2026-08-03-specification-authority-technical.md`.

## Key decisions

New this session (handoff-0003's decisions still hold and are not repeated here):

- **The real defect is an inline `background`, not a missing class.** Task 1.2's global CSS fix
  (`button:not([data-slot="button"]):not(.row-item):not(.row-action):hover { background-color:
  var(--accent) }`) cannot help a button that sets its own `style={{ background: … }}`, because
  inline style specificity always wins over any stylesheet rule, `:hover` or not. This reframing is
  what made the task 2.4 audit tractable — grep for the inline pattern, not for "buttons without a
  particular class."
- **Semantic/status colors that must persist through hover stay inline; only the *resting* state
  moves to CSS.** `LogsView`'s severity chips (red for error, amber for warn) and
  `SpecNavigator`/`ComposerAgentSelector`'s selected rows keep their *active*-state color pinned
  inline (via `data-active` + a conditional inline `background`), because `.row-item[data-active]`'s
  generic `--row-selected` gray would erase the semantic meaning. Only the *inactive* resting state
  was freed of any inline `background` so the shared hover rule can reach it. Rejected: converting
  everything uniformly to `.row-item` — that would flatten severity chips down to gray at rest, which
  is a real information loss, not a refactor.
- **`QuestionInterruptCard`'s "Answer" button was kept off the `Button` primitive**, styled instead
  with plain Tailwind (`bg-[var(--amber)] hover:brightness-110`). Rejected: `<Button variant="ghost"
  style={{ background: 'var(--amber)' }}>` — this was tried first and is exactly the same
  inline-background-blocks-hover bug being fixed elsewhere, just introduced fresh: the ghost
  variant's `hover:bg-[var(--accent)]` Tailwind utility (itself higher-specificity than a plain
  utility, due to the `:hover` pseudo-class) would still have overridden the inline amber on hover,
  so the button would lose its urgency color right when the operator points at it. A plain button
  styled entirely through Tailwind classes (no inline style at all) avoids the conflict.
- **`SpecNavigator`'s tree rows, tabs, and outline rows converted to `.row-item` rather than
  `Button`.** These are genuinely row-list UI (a document tree, a two-way tab switch, a page outline)
  matching `.row-item`'s existing selected/hover semantics almost exactly (its CSS block is close to
  a byte-for-byte match of the component's own `rowBase` object). Using `Button` here would have
  meant fighting its button-shaped sizing variants for what is structurally a list row.
- **A pathspec-scoped `git add -A -- hub/hub/static/ui`** was used to reconcile the bundle directory
  cleanly, rather than manually tracking which of the four asset files were staged-but-stale vs.
  genuinely new. This is safe (unlike a repo-root `git add -A`, which CLAUDE.md and this project's
  history specifically warn against) because it is scoped to one directory that is entirely build
  output, not handoff scratch.
- **The commit stages exactly this change's files**, explicitly listed
  (`git add hub/ui/src openspec/changes/2026-08-04-hub-contextual-navigation
  openspec/changes/2026-07-30-hub-native-experience/specs/hub-visual-language/spec.md` plus the
  scoped static-bundle add), continuing the boundary handoff-0002 and handoff-0003 both drew around
  the concurrent handoff-tooling work. Rejected: staging everything and letting the user un-stage —
  CLAUDE.md is explicit that `git add -A` sweeps in untracked `.claude/handoffs/` scratch, and that
  scratch is larger and more varied this session than in either prior one.

## Constraints and user directives (verbatim)

Carried forward from handoff-0003 (still binding, not repeated in full) plus new ones from this
session:

- "Apply all the fixes." — the direct instruction that started this session's work; interpreted as
  the six numbered next steps handoff-0003 left, plus the verification block, since those were what
  the handoff itself framed as "the fixes."
- "There is a project in http://127.0.0.1:8010/?project=proj-b9c0eebb&tab=overview. Rebuild the UI
  for that so I can test it." — answered by rebuilding and confirming the running Hub (PID 3228) was
  already serving the new bundle hash off disk; no restart needed since it's a `StaticFiles` mount.
- "$handoff commit and handoff" — this handoff, with the commit made first per the skill's Step 2.
- All of CLAUDE.md's standing rules still apply verbatim: "This repo has no AgentWeave session, and
  must not acquire one," "Stage paths explicitly; `git add -A` sweeps in untracked
  `.claude/handoffs/` scratch," "Never mark a task complete on the strength of a plan existing," and
  the standing directive to "live-verify the prior session's claimed work still functions" on
  resume — which this session did, by actually running the previously-red suite before touching
  anything.

## Dead ends

Carried forward from handoff-0003 (`npm run lint` cannot start — no `eslint.config.js`; bare `ruff`/
`black` need `py -3.11 -m`; Vite empties CSS imports under Vitest, use `readFileSync`; `npx openspec`
fails with "could not determine executable to run" — invoke `openspec` directly). New this session:

- The first attempt at fixing `QuestionInterruptCard`'s Answer button (`<Button variant="ghost"
  style={{ background: 'var(--amber)' }}>`) reproduced the exact bug it was meant to fix — see Key
  decisions above. Caught by reasoning through CSS cascade/layer order before running it, not by a
  failing test (no test covers this component directly).
- A broad regex grep for `<button[\s\S]*?style=\{\{[\s\S]*?background` over-matched significantly:
  it flagged 23 files, but roughly a third were false positives where the matched `background`키
  belonged to a *descendant* element (e.g. `AgentInfoTab`'s copy-session-id button, whose `<code>`
  child has the background, not the button itself) or was a decorative, intentionally-chromeless
  `background: 'none'`/gradient (e.g. `AgentTimeline`'s "Show more" fade). Each file had to be read,
  not just grepped, before deciding whether to touch it.
- Tailwind cascade-layer ordering (`@tailwind base; @tailwind components; @tailwind utilities;`)
  means a plain utility class like `bg-[var(--surface)]` (utilities layer) will beat *any* `@layer
  base` rule, including a `:hover` pseudo-class rule like `.row-item:hover { background: … }`, even
  though the hover rule has higher CSS specificity — layer order overrides specificity across
  layers. This was caught before shipping (`SpecNavigator`'s search-trigger button): the fix was to
  not use `.row-item` there at all and instead pair `bg-[var(--surface)]` with an explicit
  `hover:bg-[var(--row-hover)]` utility, both in the utilities layer, where Tailwind's own variant
  ordering resolves correctly.

## Verification

**Run this session, with real results:**

- `npx vitest run src/__tests__/App-mount.test.tsx` → 9 passed (confirms the test fix in isolation
  before running the full suite).
- `npm test` in `hub/ui`, run twice more after further edits → **376 passed (46 files)**, both times.
- `npx tsc --noEmit` in `hub/ui`, run three times across the session → passed, no output, every time.
- `npx vitest run src/__tests__/hubVisualLanguage.test.ts` → 6 passed (the new contract test).
- `npx vitest run src/__tests__/agentCreationUi.test.tsx` → 4 passed.
- `npx vitest run src/__tests__/specManifestRepair.test.tsx src/__tests__/specNavigationUi.test.tsx
  src/__tests__/specWorkspace.test.tsx` → 42 passed combined.
- `npx vitest run src/__tests__/composerAgentSelector.test.tsx` → 2 passed.
- `openspec validate 2026-07-30-hub-native-experience --strict` → valid.
- `openspec validate 2026-08-04-hub-contextual-navigation --strict` → valid (checked twice: once
  before and once after the `tasks.md` reconciliation).
- `py -3.11 -m pytest hub/tests -q` → **602 passed, 8 skipped**, unchanged from handoff-0002's
  baseline; confirms zero backend regression (no backend file was touched).
- `npm run build` in `hub/ui` → passed, 2091 modules, same pre-existing chunk-size warning as every
  prior build.
- `py -3.11 -m pytest hub/tests/test_ui_staleness.py hub/tests/test_setup.py -q` → 14 passed, after
  the bundle refresh.
- Confirmed the running Hub at `http://127.0.0.1:8010/` (PID 3228, unrestarted) is serving the exact
  new bundle hashes (`curl` the root page and matched the returned `assets/index-*.js`/`.css`
  filenames against what `npm run build` produced) — this is real evidence the disk-served bundle is
  current, not a guess.

**NOT run this session — do not report these as verified:**

- **Every live browser check** (tasks 7.6, 7.7, 7.8): no viewport was inspected, no hover/selected
  state was visually confirmed, no reduced-motion or keyboard-only pass was performed. No browser
  automation tool was available in this environment. This is the single largest gap between "the
  suite is green" and "the change looks and works as designed."
- `npm run lint` — still cannot start (missing `eslint.config.js`, pre-existing repo issue, not
  something this session's changes caused or could fix in scope).
- Ruff / Black — no Python file was touched this session.
- Whether the two watch items noted in handoff-0003 (composer shadow tuned for dark only;
  `ProjectTabs`'s inactive-tab color/underline change) read acceptably — neither was re-examined.

## Git state

- Branch `hub-native-experience`. HEAD is now `8526bea` "Hub contextual navigation: interaction
  feedback, rail sections, conversation surface" (previously `89b837e`).
- **Iteration commit:** `89b837e..8526bea`, one commit, 57 files changed (+2776/-1369).
- No upstream tracking branch configured; nothing pushed, nothing to compare against a remote.
- **Still dirty** after the commit, with exactly the same set of pre-existing/concurrent files
  handoff-0002 and handoff-0003 both flagged as out of scope: `.claude/handoffs/LATEST.md` (staged
  delete), `.claude/handoffs/handoff-0001-*` (staged rename), `Makefile` (unstaged M), and untracked:
  `scripts/`, `.claude/skills/{handoff,resume,review-iteration}/`, `src/agentweave/templates/skills/
  {handoff,resume}.md`, `tests/test_handoff_resume_templates.py`, `data/`, five older handoff files,
  `.claude/handoffs/reviews/`, `openspec/explorations/2026-08-03-specification-authority-technical.md`,
  and now also this handoff file itself (`handoff-0004-…`, written after the commit, per the skill's
  own ordering) plus `handoff-0002-*`/`handoff-0003-*`, none of which have ever been committed across
  three sessions.

## Corrections to the previous handoff

- handoff-0003 said "task 4.4… Verified by reading each ported panel" was *not yet done* at that
  point — this was accurate at the time (only `ProjectSettingsPanel` existed) but is now satisfied
  for all eight panels as of this session's work.
- Everything else in handoff-0003 still holds; nothing it recorded turned out to be wrong.

## Next steps

1. **Run the live browser pass (tasks 7.6, 7.7, 7.8).** The running Hub at
   `http://127.0.0.1:8010/?project=proj-b9c0eebb&tab=overview` (PID 3228) is already serving this
   session's bundle — confirmed by `curl` above. Check: hover/selected states on every rail row, tab,
   and section row; the gear reveal on hover/focus; rail section mode entry and the one-action back
   control; a settings section with no native number-input steppers and no visible dead area at
   1280×800; the conversation surface with no filled bands and a lifted composer; repeat at 390×800;
   repeat with `prefers-reduced-motion: reduce`; do a keyboard-only pass confirming the revealed gear,
   rail back control, and header turn controls all receive visible focus.
2. **While in the browser, specifically look at the two watch items**: does
   `.conversation-composer-surface`'s shadow (tuned only for dark) look wrong in light mode? Does
   `ProjectTabs`'s inactive-tab treatment (full-strength text, no underline, per the cascade analysis
   in handoff-0003's Watch items) read as acceptable, or does it need its own explicit non-`--text-3`
   override?
3. **Decide and act on 4.7** (save success/failure reporting) if the live pass makes the
   inconsistency across the eight environment panels feel wrong in practice — currently only
   `ProjectSettingsPanel` reports both outcomes in-section.
4. **Resolve the three standing open questions from handoff-0003** (repeated below, still open —
   this session did not touch any of them, since none blocked the fixes it was asked to apply).
5. **Once the live pass is clean, decide what to do with the handoff-tooling work** that has now
   been carried uncommitted across four sessions (see Git state) — it is a coherent, unrelated unit
   that keeps getting reconfirmed as "not part of this change" without ever landing anywhere.

## Open questions for the user

Carried forward from handoff-0003, unchanged — none of these were addressed this session:

1. `data/agentweave.db` at the repository root is untracked and not gitignored. Delete it, gitignore
   it, or is it intentional scratch?
2. Should the staged-but-uncommitted handoff-tooling work (`Makefile`, `scripts/sync_skills.py`, the
   `.claude/skills/` files, the `src/agentweave/templates/skills/` files,
   `tests/test_handoff_resume_templates.py`, the `LATEST.md` delete, and the `handoff-0001` rename)
   be committed as its own checkpoint?
3. Should the `review-0002` finding (no `UniqueConstraint` on `agents(project_id, name)`, allowing
   concurrent agent creation to produce a duplicate-named agent) be fixed inside this change or
   proposed separately? It remains open and untouched.

## Read on resume

- `openspec/changes/2026-08-04-hub-contextual-navigation/tasks.md` — now accurate; shows exactly
  what's confirmed vs. what still needs the live browser pass.
- `openspec/changes/2026-08-04-hub-contextual-navigation/mock-contextual-nav.html` — the visual
  authority for the live pass in next step 1.
- `hub/ui/src/index.css` — the `.row-item`/`.row-action` row-treatment rules and the two theme
  blocks defining `--row-hover`/`--row-active`/`--row-selected`; needed to judge the watch items.
- `hub/ui/src/components/layout/ProjectTabs.tsx` — the `Button` + `.row-item` combination flagged as
  a watch item; read alongside `index.css`'s cascade to decide next step 2.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — the composer surface whose shadow needs a
  light-mode look, per next step 2.
