# Handoff 0003: Hub contextual navigation — sections 1–3 landed, 4–7 partial, suite red

**Date:** 2026-08-04T17:55:51+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `89b837e`
**Model:** implementation — `unknown — the implementing session did not record it and did not
finish its handoff`. Its prose and workflow match the Codex/T3 session that wrote handoff-0002,
but that is inference, not evidence. This handoff file was reconstructed from the working tree and
live test runs by `claude-opus-5[1m]` (Claude Code).
**Agent:** implementation — unknown CLI; reconstruction — Claude Code
**Iteration commits:** none — all of this iteration's work is uncommitted in the working tree on
top of `89b837e`. The review boundary for `/review-iteration` is therefore `89b837e..<worktree>`,
not a commit range.
**Previous handoff:** `.claude/handoffs/handoff-0002-2026-08-04-1504-hub-ui-mock-alignment.md`
**Status:** in progress — implementation is roughly 60% of `tasks.md` and `npm test` is red

## Goal

Implement the approved change `openspec/changes/2026-08-04-hub-contextual-navigation/`: make the
left rail contextual (project mode vs. configuration section mode), give every activatable element
real hover/press/selected feedback by adopting the already-written-but-unused `Button` primitive,
rebuild the agent conversation surface against the mock (borderless floating header, ground-plane
stream, lifted composer over a gradient fade), and re-lay the eight environment screens as titled
settings-row sections.

The *why*: the previous change (`2026-08-04-hub-ui-mock-alignment`, commit `89b837e`) recomposed
only the shell. Operator review found the conversation screen untouched, configuration reachable
from two places with its navigation stranded inside the content area, and — the sharpest problem —
that `hub/ui/src/components/ui/button.tsx` defined a complete control primitive that **no component
imported**, leaving nearly every control in the product visually inert under the pointer.

## Current state

Read this section carefully: **`tasks.md` on disk is badly out of date.** It marks only section 1
complete, but sections 2, 3, 4 and 5 are substantially implemented in the working tree. Nothing in
sections 2–7 is checked off even where the code exists. Do not trust the checkboxes; trust the
per-task status below, which was derived by reading the actual diff.

### Verified complete

- **1.1–1.6 Interaction foundation.** `--row-hover` / `--row-active` / `--row-selected` defined in
  both `[data-mode="dark"]` (8/11/7% of `--text`) and light (5/9/6%). Global control baseline now
  sets `background-color: transparent` at rest and `var(--accent)` on hover, excluding
  `[data-slot="button"]`, `.row-item`, and `.row-action`. `.row-item` shared row treatment,
  `.row-action` group-hover reveal (with `.row-group:hover` / `:focus-within` / `[data-persistent]`
  escapes), and global `input[type=number]` spinner suppression for WebKit and Firefox all landed.
- **2.1 / 2.2 Control adoption in the shell and conversation.** `Sidebar`, `ProjectHeader`,
  `ProjectTabs`, `App.tsx`, `ConversationControls`, and `Composer` now import and render
  `@/components/ui/button`. `AgentTimeline` uses the new `.fold-control` / `.work-disclosure` CSS
  rather than the `Button` primitive — deliberate, those are `<summary>` and pill elements, not
  buttons — but note that means 2.2 is satisfied by two mechanisms, not one.
- **3.1–3.4, 3.6, 3.7 Contextual rail.** `Sidebar` takes a `destination` prop and derives
  `data-mode="section" | "project"` from `isConfigurationDestination(destination)` — no component
  state, as 3.1 requires. Section mode renders a `rail-section-back` control, the configured
  project's name, and the eight sections as `.row-item` rows with `aria-current="page"`. Each
  project row carries a `.row-action` gear labelled `Configure <project name>`, persistent for the
  active project. `Add agent` is a row at the end of each expanded project's agent list
  (`rail-add-agent-<projectId>`). `environment` is removed from `PROJECT_TABS`;
  `environmentDestination`, `parseDestination`, and the `?tab=environment&section=…` URL contract
  are intact — `parseDestination` now branches on `rawTab === 'environment'` *before* the
  `PROJECT_TABS` membership check, which is what keeps deep links resolving after the removal. The
  gear and Add-agent buttons are gone from `ProjectHeader`.
- **3.5 Section column removal.** `App.tsx` no longer renders the 160px `<nav>` inside the content
  area; the environment branch renders only `environmentPages[section]`, and `ProjectTabs` is
  suppressed entirely when `destination.tab === 'environment'`.
- **4.1 / 4.2 Settings-row layout for one panel.** New
  `hub/ui/src/components/environment/SettingsSection.tsx` exports `SettingsSection` (title,
  description, optional actions slot) and `SettingsRow` (label + explanation on the left, control
  right-aligned in a 180px-min column). `ProjectSettingsPanel` is ported, `max-w-3xl` is gone, and
  explanation copy is written for hop budget, per-turn delivery cap, agent budget, token budget,
  agent jobs, and directory. Save success (`role="status"`) and failure (`role="alert"`) are both
  reported in-section.
- **5.1–5.8 Conversation surface.** `AgentOutputPanel`'s header is now
  `.conversation-header-surface` — no fill, no rule, `color-mix(in oklab, var(--bg) 88%,
  transparent)` with a 12px backdrop blur — and `ConversationControls` moved from the footer into
  it. The literal `←` is replaced by an `arrow_left` icon Button with `aria-label="Back to
  project"` (`ArrowLeft` was added to `Icon.tsx`). `Stop turn` and `Fold all turns` are now header
  buttons; `Fold all turns` was removed from the overflow menu, which keeps conversation
  switching, handoff, and agent details. The filled footer strip is replaced by
  `.conversation-composer-fade` (gradient to `--bg`) wrapping a max-820px column holding the banner
  stack, the continuity line, and `.conversation-composer-surface` — own fill, `--border-hi`
  outline, `--radius-content`, drop shadow, and a `:focus-within` treatment on the whole surface.
  The `AgentTimeline` measure widened from 760px/18px gaps/px-5 to 960px/21px gaps/px-[30px].
- **6.2** `openspec validate 2026-08-04-hub-contextual-navigation --strict` → `valid`.

### Not done

- **2.3** Only `ProjectSettingsPanel` of the eight environment panels adopts the primitive.
- **2.4** No audit of activatable elements outside the shell / conversation / environment screens.
- **2.5** No source contract was added. `hub/ui/src/__tests__/hubVisualLanguage.test.ts` is
  byte-for-byte unchanged (`git diff --stat HEAD` lists no entry for it), so nothing asserts that
  shell components use the primitive instead of `<button style={…}>`.
- **3.8** Back control reaches the project overview in one action — implemented and covered by the
  new unit test, but not confirmed live in a browser.
- **4.3** `QualityHealthPanel`, `InstructionsPage`, `RunnersPage`, `ChartersPage`, `WorktreesPanel`,
  `DiagnosticsPanel`, `AccountingPanel` are all untouched. This is the single largest remaining
  chunk. Consequence: of the five requirements in the `project-environment-settings` delta spec,
  only the `settings` section satisfies them; seven sections do not.
- **4.4–4.7, 5.9, 7.6–7.8** All confirmation/live-check tasks. None were run.
- **6.1** No reconciliation was written into
  `openspec/changes/2026-07-30-hub-native-experience/`. That change's wording still forbids
  project-scoped views from appearing in the navigation region, which the contextual rail now
  directly contradicts. `git status` shows no modification under that directory.

### The blocker

`npm test` in `hub/ui` is **red: 1 failed | 374 passed (375 tests); 1 failed | 45 passed (46
files).**

`hub/ui/src/__tests__/App-mount.test.tsx:193` — the test
`'Environment contains Quality, Instructions, Runners, Charters, Worktrees, Diagnostics, Budgets,
and Settings'` still does `fireEvent.click(screen.getByTestId('project-tab-environment'))`. That
test id no longer exists: task 3.6 removed `environment` from `PROJECT_TABS`, so `ProjectTabs`
never renders it. The test was not updated when the tab was removed. Everything after that line in
the test is still valid — the `environment-section-*` ids do exist, they just live in the rail now
instead of the content column.

## Files touched

Every path below was cross-checked against `git status --short` and `git diff --stat HEAD`.

**This iteration's work (uncommitted):**

- `hub/ui/src/index.css` — row-state tokens for both themes, default hover fill on the control
  baseline, number-spinner suppression, `.row-item`, `.row-action`/`.row-group`,
  `.settings-section`/`.settings-row`, `.conversation-header-surface`,
  `.conversation-composer-fade`/`-surface`, `.work-disclosure`/`.fold-control`; finished for the
  scope reached so far.
- `hub/ui/src/lib/navigation.ts` — `environment` removed from `PROJECT_TABS`; `WorkspaceDestination`
  split so `environmentSection` is required on the `tab: 'environment'` arm; new
  `isConfigurationDestination` type guard; `parseDestination` reordered to branch on
  `rawTab === 'environment'` first; finished.
- `hub/ui/src/components/layout/Sidebar.tsx` — `destination`/`onOpenEnvironment`/`onAddAgent` props,
  `data-mode` section vs. project, section-mode nav, per-project gear, Add-agent row, Button
  adoption; finished.
- `hub/ui/src/App.tsx` — Sidebar wiring, environment section column removed, `ProjectTabs`
  suppressed in environment, `agentCreateOpen` boolean replaced by `agentCreateProjectId` so the
  dialog creates into the rail-clicked project rather than the currently selected one, Button
  adoption on the retry control; finished.
- `hub/ui/src/components/layout/ProjectHeader.tsx` — Add-agent and gear removed; theme toggle and
  setup ported to Button; finished.
- `hub/ui/src/components/layout/ProjectTabs.tsx` — `environment` label removed, tabs render as
  `Button` + `.row-item` with `data-active`; finished, but see "Watch items" — the active-tab
  treatment changed character and has not been looked at.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — header rebuilt, controls relocated into it,
  icon back control, composer fade + lifted surface; finished.
- `hub/ui/src/components/agents/ConversationControls.tsx` — Button adoption, `Stop` → `Stop turn`,
  `Fold all turns` promoted out of the overflow menu; finished.
- `hub/ui/src/components/agents/Composer.tsx` — textarea de-chromed (border/radius/fill removed,
  colour `--text-3` → `--text`) since the wrapper is now the surface; send button → primary Button;
  finished.
- `hub/ui/src/components/agents/AgentTimeline.tsx` — measure/gutters/spacing widened,
  `.fold-control` and `.work-disclosure` classes; finished.
- `hub/ui/src/components/common/Icon.tsx` — `arrow_left` → `ArrowLeft`; finished.
- `hub/ui/src/components/environment/SettingsSection.tsx` — **new, untracked.** `SettingsSection` +
  `SettingsRow`; finished.
- `hub/ui/src/components/environment/ProjectSettingsPanel.tsx` — ported to the settings-row layout
  with written explanations, `required` added to the numeric inputs, success reporting added;
  finished.
- `hub/ui/src/__tests__/projectRail.test.tsx` — two new tests: gear + Add-agent callbacks, and
  section-mode derivation / one-action back; finished and passing.
- `hub/ui/src/__tests__/conversationControls.test.tsx` — updated for the header placement and the
  4-item overflow menu; finished and passing.
- `hub/ui/src/__tests__/agentCreationUi.test.tsx` — inverted to assert Add agent is *absent* from
  `ProjectHeader`; finished and passing.
- `hub/ui/src/__tests__/App-mount.test.tsx` — **NOT touched, and this is the bug.** Still clicks the
  removed `project-tab-environment`. Needs updating.
- `hub/hub/static/ui/index.html`, `hub/hub/static/ui/assets/index-DMlXiq3k.js` (added),
  `hub/hub/static/ui/assets/index-BBRjPn8j.css` (renamed from `index-BL6FHekx.css`),
  `hub/hub/static/ui/assets/index-B6UnVD_F.js` (deleted) — rebuilt bundle, staged. Confirmed
  current: `pytest hub/tests/test_ui_staleness.py -q` passes.
- `openspec/changes/2026-08-04-hub-contextual-navigation/` — **new, untracked.** `.openspec.yaml`,
  `proposal.md` (approved 2026-08-04), `design.md`, `tasks.md`, `mock-contextual-nav.html`
  (the 36KB reference mock — the visual authority for this change), and four spec deltas:
  `hub-workspace-shell` (4 requirements), `agent-conversation-workspace` (6),
  `hub-interaction-feedback` (6), `project-environment-settings` (5). Validates strict.

**Pre-existing / concurrent user work — do not fold into this change's commit:**

- `.claude/handoffs/LATEST.md` (staged delete) and `.claude/handoffs/2026-08-04-1153-…` →
  `handoff-0001-2026-08-04-1153-…` (staged rename) — the chain adoption performed by the
  handoff-0002 session, still staged and never committed.
- `Makefile` — adds a `sync-skills` target invoking `scripts/sync_skills.py`.
- `scripts/sync_skills.py` — new; mirrors hand-written dev skills to `.agents/skills/` and
  `~/.codex/skills/`.
- `.claude/skills/handoff/SKILL.md`, `.claude/skills/resume/SKILL.md`,
  `.claude/skills/review-iteration/SKILL.md` — new local dev skills.
- `src/agentweave/templates/skills/handoff.md`, `src/agentweave/templates/skills/resume.md`,
  `tests/test_handoff_resume_templates.py` — the shipped product-skill versions of the above.
- `.claude/handoffs/reviews/review-0002-2026-08-04-1530.md` — kimi-for-coding/k3's review of
  `0d0f9c6..89b837e`. Verdict "Ship with follow-ups"; its [Major] finding (agent-name uniqueness is
  check-then-insert with no `UniqueConstraint` on `agents(project_id, name)`) is **still open** and
  is unrelated to this change.
- Five untracked older handoffs from the local-multi-project work, and
  `openspec/explorations/2026-08-03-specification-authority-technical.md`.
- `data/agentweave.db` — an untracked SQLite Hub database at the repository root. It is **not
  gitignored** (`git check-ignore` reports nothing), so a `git add -A` would commit it. See
  "Open questions".

## Key decisions

Taken from `design.md` and from what the diff actually does. Alternatives and their rejection
reasons are recorded so they are not re-proposed.

- **The rail owns contextual navigation.** Configuration replaces the rail's contents rather than
  opening navigation inside the content area. Rejected: keeping the in-content section column — it
  put navigation in the content region, which is what the operator objected to ("any navigation
  should be applied to the nav on the left"). Rejected: a second permanent rail — doubles the
  chrome for a screen the operator visits occasionally.
- **Rail mode is derived, never stored.** `isConfigurationDestination(destination)` computes it on
  every render. Rejected: `useState` in `Sidebar` — a deep link to `?tab=environment&section=…`
  would land with the rail in project mode, and back/forward would desynchronise it.
- **`environment` leaves `PROJECT_TABS` but stays in the URL contract.** The destination type keeps
  a `tab: 'environment'` arm and `parseDestination` special-cases it ahead of the membership check.
  Rejected: removing the destination entirely — every existing `?tab=environment` deep link would
  silently fall back to overview.
- **Row states are `color-mix` percentages of `--text`, not new hex values.** T3's 8/11/7% dark
  ratios were adopted, re-expressed against AgentWeave's own `--text` so the palette stays ours,
  and lowered to 5/9/6% in light because the ground plane sits closer to text colour. Rejected:
  copying T3's literal colours — that imports their brand, which the proposal's non-goals forbid.
- **Selected and hover are separate tokens.** `--row-selected` is deliberately *not* `--row-hover`,
  so a selected row stays identifiable while an unrelated row is hovered.
- **`.row-action` occupies layout at rest and animates only `opacity`.** Rejected:
  `display: none` → `block` on hover — it reflows the row and shifts its neighbours.
- **The global baseline gained a default hover fill.** Previously it reserved a transparent border
  and declared transitions but never set a hover background, which is why controls read as inert.
  `.row-item` and `.row-action` are excluded because they carry their own full treatments.
- **The composer is the conversation's only lifted surface.** Header and stream sit on the ground
  plane; the strip and both dividing rules are gone. Rejected: keeping a `--surface-2` footer — it
  boxes the composer together with the banner stack and continuity line, which the mock does not.
- **`Fold all turns` and `Stop turn` are header controls, not menu items.** They act on the turn,
  so they sit with the turn's state. Conversation switching, handoff, and agent details stay in the
  overflow menu as low-frequency actions.
- **The agent-creation dialog now carries the project id it was opened from**
  (`agentCreateProjectId` rather than a boolean), because the Add-agent row is per-project in the
  rail and may not be the currently selected project.

## Constraints and user directives (verbatim)

Carried forward from handoff-0002 and from this change's `proposal.md` / `design.md`; all still
binding.

- "any navigation should be applied to the nav on the left."
- "The general feel of the UI is wrong. I want something very similar if not equal to what was
  mocked"
- "Take a lot of inspiration from T3's UI"
- "Need a button to create new agents in the UI."
- "approved" (the approval gate in `proposal.md`: "Implementation MUST NOT begin until the user
  explicitly approves this proposal." · "**Approved:** 2026-08-04")
- "This repo has no AgentWeave session, and must not acquire one." (CLAUDE.md)
- "Do the work directly." (CLAUDE.md — no AgentWeave delegation in this repo)
- "Stage paths explicitly; `git add -A` sweeps in untracked `.claude/handoffs/` scratch."
  (CLAUDE.md — and now also `data/agentweave.db`)
- "Never mark a task complete on the strength of a plan existing. Only real, verified
  implementation closes a task." (CLAUDE.md)
- "on /resume, live-verify the prior session's claimed work still functions" (standing user
  directive, recorded in every handoff)

From `proposal.md` non-goals, which are constraints on what must *not* change:

- Do not redesign the Spec workspace — that is the next specification-program change.
- Do not change what any environment section does, or the runner/charter/quality/budget data models.
- Do not change conversation semantics: queue handling, hop budget, handoff, autoscroll, context
  usage, and provider-identity confinement keep their specified behaviour.
- Do not reproduce T3 branding, palette, product copy, or account surfaces.
- Backend: none. No API, schema, or event changes. (`git status` confirms zero backend files
  touched this iteration.)

## Dead ends

Carried forward from handoff-0002, since the same tooling will be hit again:

- `npm run lint` cannot start — ESLint 9 finds no `eslint.config.js`. This is repository tooling
  debt, not a lint report. Do not read its failure as a finding about changed code.
- Bare `ruff` and the harness Python lack Ruff; use `py -3.11 -m ruff`. `black` needs `--fast`
  because the repository's target syntax is newer than the checking interpreter.
- Vite turns CSS imports into an empty runtime module under Vitest, so CSS source contracts must
  use Node `readFileSync` (the pattern in `hubVisualLanguage.test.ts`) rather than importing.

New this iteration:

- `npx openspec validate …` fails with `npm error could not determine executable to run`. The
  `openspec` binary is already on PATH — invoke it directly, without `npx`.
- The Bash tool's working directory persists between calls. A `cd hub/ui` in one call leaves later
  calls rooted there; use absolute paths or re-`cd` to the repo root.

## Verification

**Run, with real results:**

- `npx tsc --noEmit` in `hub/ui` — **passed**, no output.
- `npm test` in `hub/ui` — **FAILED. 1 failed | 374 passed (375 tests); 1 failed | 45 passed
  (46 files).** The single failure is `App-mount.test.tsx:193`,
  `getByTestId('project-tab-environment')` — element not found, because task 3.6 removed that tab.
  Duration 15.10s.
- `py -3.11 -m pytest hub/tests/test_ui_staleness.py -q` — **5 passed.** The committed bundle under
  `hub/hub/static/ui` matches the current source, so `npm run build` was run after the last source
  edit.
- `openspec validate 2026-08-04-hub-contextual-navigation --strict` — **`Change
  '2026-08-04-hub-contextual-navigation' is valid`.**

**NOT run — do not report any of these as verified:**

- `pytest hub/tests -q` (the full backend suite). Not run this session. No backend file is modified,
  so it is *expected* to be unchanged from handoff-0002's 602 passed / 8 skipped — but that is an
  expectation, not a measurement. Task 7.1 is open.
- `npm run build` was not re-run by this session; its freshness is inferred from
  `test_ui_staleness` passing.
- `npm run lint` — cannot start (see Dead ends).
- Ruff / Black — no Python file was changed this iteration.
- **Every live browser check: tasks 7.6, 7.7, 7.8.** No Hub was launched and no viewport was
  inspected this session. Nothing about hover states, selected states, the gear reveal, rail
  section mode, dead area in settings sections, reduced motion, or keyboard reachability has been
  observed rendering. Handoff-0002 left a disposable Hub on `http://127.0.0.1:8010` (PID 3228,
  project `proj-b9c0eebb`, agents `codex-alpha` / `codex-beta` / `codex-gamma`); whether it is
  still up was not checked, and it would in any case be serving the older bundle unless restarted.
- Tasks 3.8, 4.4, 4.5, 4.6, 4.7, 5.9 are all "confirm …" tasks and none were confirmed.

**Watch items — noticed while reading the diff, not confirmed as defects:**

1. `ProjectTabs` renders `<Button variant="ghost" … className="row-item …">`, combining the
   primitive with the row treatment. The two overlap: Tailwind's `hover:bg-[var(--accent)]` ties on
   specificity with `.row-item:hover` and wins by source order, so tabs hover with `--accent` while
   rail rows hover with `--row-hover`. `.row-item[data-active="true"]` (0,2,0) does still beat
   `bg-transparent` (0,1,0), so the selected tab keeps its `--row-selected` fill and 550 weight.
   But ghost's `text-[var(--text)]` also beats `.row-item`'s `--text-2`, so *inactive* tabs are now
   full-strength text where they used to be `--text-3`, and the old blue 2px underline is gone.
   Net: the active tab is distinguished by a subtle fill and half a weight step. This is a design
   judgment for the operator to make at 7.6, not something to "fix" blind.
2. `.conversation-composer-surface` hardcodes `0 20px 52px rgba(2, 5, 18, 0.28)` and an
   `inset 0 1px rgba(255,255,255,0.05)`. Both are tuned for dark; neither is token-derived. Check
   how the composer reads in light mode at 7.6.
3. The environment content still renders inside `App.tsx`'s `workspace-content` wrapper
   (`width: min(100%, 1180px)`), while `.settings-section-rows` caps at 920px. Task 4.5 asks for no
   dead area at a wide viewport — with two nested caps, look at this specifically.

## Git state

- Branch `hub-native-experience`. HEAD `89b837e` "Hub UI mock alignment: restore shell and add
  agents". No upstream tracking configured for this branch.
- **Dirty.** Nothing from this iteration is committed.
- Staged (inherited from the handoff-0002 session, never committed): the `LATEST.md` delete, the
  `handoff-0001-…` rename, and the rebuilt `hub/hub/static/ui` bundle files.
- Unstaged modifications: `Makefile` plus the 15 `hub/ui/src` files listed above.
- Untracked: `hub/ui/src/components/environment/SettingsSection.tsx`,
  `openspec/changes/2026-08-04-hub-contextual-navigation/`, `scripts/sync_skills.py`,
  `.claude/skills/{handoff,resume,review-iteration}/SKILL.md`,
  `src/agentweave/templates/skills/{handoff,resume}.md`,
  `tests/test_handoff_resume_templates.py`, `data/agentweave.db`, seven handoff/review files, and
  `openspec/explorations/2026-08-03-specification-authority-technical.md`.
- No commit was made by this session, and the user was not asked to approve one, because the suite
  is red — committing a failing test suite is not a checkpoint.

## Corrections to the previous handoff

- handoff-0002 named `hub/hub/static/ui/assets/index-B6UnVD_F.js` and `index-BL6FHekx.css` as the
  committed bundle. Both have since been superseded in the working tree by `index-DMlXiq3k.js` and
  `index-BBRjPn8j.css`. Normal rebuild churn, not an error in that handoff.
- handoff-0002 said "Concurrent user changes remain intact and outside that commit" and listed them
  as still pending. That is still true, and the list has since grown by `scripts/sync_skills.py`,
  `.claude/skills/review-iteration/`, `.claude/handoffs/reviews/`, and `data/agentweave.db`.
- Everything else in handoff-0002 still holds.

## Next steps

1. **Fix `hub/ui/src/__tests__/App-mount.test.tsx`, the test starting at line 191**
   (`'Environment contains Quality, Instructions, …'`). Replace line 193,
   `fireEvent.click(screen.getByTestId('project-tab-environment'))`, with a click on the rail gear —
   `fireEvent.click(screen.getAllByRole('button', { name: /^Configure / })[0])`. That calls
   `onOpenEnvironment(projectId, 'quality')`, which navigates to the environment destination and
   flips the rail into section mode, after which the existing loop over
   `environment-section-quality` … `environment-section-settings` works unchanged, because those
   test ids now live in `Sidebar`. Then re-run `npm test` in `hub/ui` and confirm 375/375.
   `hub/ui/src/__tests__/projectRail.test.tsx:82-107` is a working reference for both interactions.
2. **Reconcile `openspec/changes/2026-08-04-hub-contextual-navigation/tasks.md` with reality** —
   check off 2.1, 2.2, 3.1–3.7, 4.1, 4.2, 5.1–5.8, and 6.2 (1.1–1.6 are already checked), and leave
   everything in "Not done" above unchecked. Per CLAUDE.md, do not check any "confirm …" task that
   has not actually been confirmed.
3. **Complete task 4.3** — port `QualityHealthPanel`, `InstructionsPage`, `RunnersPage`,
   `ChartersPage`, `WorktreesPanel`, `DiagnosticsPanel`, and `AccountingPanel` to
   `SettingsSection`/`SettingsRow`, using `ProjectSettingsPanel` as the worked example. This closes
   4.4 and most of 2.3 at the same time. Largest remaining chunk.
4. **Task 2.5** — add the source contract to `hub/ui/src/__tests__/hubVisualLanguage.test.ts`,
   asserting via `readFileSync` that `Sidebar.tsx`, `ProjectHeader.tsx`, `ProjectTabs.tsx`,
   `ConversationControls.tsx`, and `Composer.tsx` contain no `<button` carrying a `style={`
   attribute.
5. **Task 6.1** — write the supersession note into
   `openspec/changes/2026-07-30-hub-native-experience/`, recording that rail-owned contextual
   navigation replaces its wording forbidding project-scoped views in the navigation region, using
   the work-view vs. configuration distinction from this change's `design.md`.
6. **Task 2.4** — audit the rest of `hub/ui/src` for activatable elements still lacking resting,
   hover, pressed, selected, or focus states.
7. **Run the verification block (7.1–7.8)**, including a live Hub at 1280×800 and 390×800 in both
   themes, a reduced-motion pass, and a keyboard-only pass. Re-run `npm run build` and refresh
   `hub/hub/static/ui` last, since the source will have changed again.
8. **Then commit**, staging paths explicitly. `data/agentweave.db` must not be in that commit.

## Open questions for the user

1. **`data/agentweave.db` at the repository root is untracked and not gitignored.** CLAUDE.md says
   this repo must not acquire AgentWeave session state at the root, and a native Hub run from here
   would produce exactly this file. Should it be deleted, added to `.gitignore`, or is it
   intentionally kept as scratch? It was left alone this session.
2. **The staged-but-uncommitted handoff-tooling work** (the `LATEST.md` delete, the `handoff-0001`
   rename, `Makefile`, `scripts/sync_skills.py`, the three `.claude/skills/` files, the two
   `src/agentweave/templates/skills/` files, and `tests/test_handoff_resume_templates.py`) has now
   been carried uncommitted across three sessions. It is a coherent unit of work. Should it be
   committed separately, ahead of the contextual-navigation commit?
3. **The [Major] finding from `review-0002`** — no `UniqueConstraint` on `agents(project_id, name)`,
   so concurrent creation can produce two agents sharing an addressable identity — is still open and
   is not covered by this change. Fix it inside this change, or propose it separately?

## Read on resume

- `openspec/changes/2026-08-04-hub-contextual-navigation/tasks.md` — the task list; note it is stale
  and next step 2 fixes it.
- `openspec/changes/2026-08-04-hub-contextual-navigation/design.md` — the T3 ratios, the rail-mode
  reasoning, and the settings-row spec that the remaining panels must follow.
- `openspec/changes/2026-08-04-hub-contextual-navigation/mock-contextual-nav.html` — the visual
  authority for every remaining judgment call.
- `hub/ui/src/__tests__/App-mount.test.tsx` — contains the one failing test; next step 1.
- `hub/ui/src/components/environment/SettingsSection.tsx` and
  `hub/ui/src/components/environment/ProjectSettingsPanel.tsx` — the worked example the other seven
  panels must be ported to.
- `hub/ui/src/components/layout/Sidebar.tsx` — where rail mode, the gear, and the Add-agent row live.
