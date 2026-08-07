# Handoff: Hub UI mock alignment implemented and verified

**Date:** 2026-08-04T15:04:31+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `89b837e`
**Agent:** T3 Code / Codex (gpt-5.6-sol)
**Previous handoff:** `.claude/handoffs/handoff-0001-2026-08-04-1153-local-multi-project-closeout.md`
**Status:** chunk complete

## Goal

Bring the Hub shell back into close visual alignment with the approved full mock, fix transparent
project dialogs and corrupted project symbols, and let an operator create a runner-bound agent from
the UI before returning to the specification-screen roadmap.

## Current state

The approved `2026-08-04-hub-ui-mock-alignment` implementation is complete and verified. The shell
now has related rail/header/content planes, a project header, compact tabs, bounded content, readable
Lucide project controls, opaque focus-trapped dialogs, and an Add agent journey. The backend creates
Hub-owned project agents only from launchable same-project runners and optional same-project
charters, emits `agent_created`, and leaves worktree provisioning to the first writing turn.

The change is archived, its seven requirements are current specs, the umbrella visual-language
wording is reconciled, and commit `89b837e` contains only the scoped implementation/spec/build
paths. Concurrent user changes remain intact and outside that commit.

The disposable Hub remains running on `http://127.0.0.1:8010` as PID 3228 with project
`proj-b9c0eebb`. It now contains `codex-alpha`, `codex-beta`, and UI-created `codex-gamma`.

## Files touched

- `hub/hub/api/v1/agents.py` — typed operator agent-creation endpoint, validation, event; finished.
- `hub/hub/api/v1/runners.py` — project runner launchability endpoint; finished.
- `hub/tests/test_operator_agent_creation.py` — backend creation/isolation contracts; finished.
- `hub/ui/src/App.tsx` — recomposed shell and agent-dialog wiring; finished.
- `hub/ui/src/api/agents.ts` — project-keyed create mutation and invalidation; finished.
- `hub/ui/src/api/runners.ts` — runner launchability hook; finished.
- `hub/ui/src/components/agents/AgentCreateDialog.tsx` — accessible creation dialog; finished.
- `hub/ui/src/components/common/Icon.tsx` — FolderPlus/ChevronRight/UserPlus mappings; finished.
- `hub/ui/src/components/layout/PaneResizer.tsx` — responsive resizer marker; finished.
- `hub/ui/src/components/layout/ProjectHeader.tsx` — project identity/actions/theme/setup; finished.
- `hub/ui/src/components/layout/ProjectTabs.tsx` — compact mock-aligned tabs; finished.
- `hub/ui/src/components/layout/Sidebar.tsx` — mock-aligned rail and valid project controls; finished.
- `hub/ui/src/components/overview/OverviewPage.tsx` — quieter cards and task/spec/job summary; finished.
- `hub/ui/src/components/projects/ProjectManagerModal.tsx` — defined opaque surface and focus hook; finished.
- `hub/ui/src/hooks/useDialogFocus.ts` — Escape, focus trap, and focus restoration; finished.
- `hub/ui/src/hooks/useSSE.ts` — `agent_created` subscription/invalidation; finished.
- `hub/ui/src/index.css` — approved light/dark mock tokens, lifted surface, bounded/responsive shell; finished.
- `hub/ui/src/__tests__/agentCreationUi.test.tsx` — header/dialog/error/keyboard contracts; finished.
- `hub/ui/src/__tests__/hubVisualLanguage.test.ts` — token/surface/icon/shell source contracts; finished.
- `hub/hub/static/ui/index.html` — rebuilt production entry; finished.
- `hub/hub/static/ui/assets/index-B6UnVD_F.js` — rebuilt production JS; finished.
- `hub/hub/static/ui/assets/index-BL6FHekx.css` — rebuilt production CSS; finished.
- `hub/hub/static/ui/assets/index-C1Emr8q3.js` — obsolete production JS removed.
- `hub/hub/static/ui/assets/index-Di_AFhey.css` — obsolete production CSS removed.
- `openspec/changes/2026-08-04-hub-ui-mock-alignment/` — approved proposal/design/tasks/deltas; ready to archive.
- `openspec/changes/2026-07-30-hub-native-experience/proposal.md` — related-plane reconciliation; finished.
- `openspec/changes/2026-07-30-hub-native-experience/specs/hub-visual-language/spec.md` — superseded one-plane wording; finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — dated successor note; finished.
- `.claude/handoffs/handoff-0002-2026-08-04-1504-hub-ui-mock-alignment.md` — this handoff.
- `.claude/handoffs/LATEST.md`, `.claude/handoffs/handoff-0001-*`, `Makefile`, `.claude/skills/`,
  `scripts/`, `src/agentweave/templates/skills/{handoff,resume}.md`,
  `tests/test_handoff_resume_templates.py`, old untracked handoffs, and
  `openspec/explorations/2026-08-03-specification-authority-technical.md` — concurrent/pre-existing
  user work; preserve and do not stage with this change.

## Key decisions

- The approved full mock is the visual authority; T3 contributes restraint and interaction quality,
  not brand identity. A flat single-plane shell was rejected because it contradicted the mock.
- Agent creation uses existing Runner and Charter records. Templates/personas and eager worktrees
  were rejected because they conflate identity, execution, and guidance or mutate the filesystem.
- Launchability is checked in both the dialog and server. Client-only validation was rejected as stale.
- Dialog behavior uses one small shared focus hook. Leaving ad-hoc Escape-only modals was rejected
  because it did not meet the focus-trap/restoration requirement.
- The packaged bundle is committed. Leaving only source changes was rejected because native Hub
  serves `hub/hub/static/ui` directly.

## Constraints and user directives (verbatim)

- "The general feel of the UI is wrong. I want something very similar if not equal to what was mocked"
- "The button to add a project spawns a new screen that is transparent."
- "Need a button to create new agents in the UI."
- "both the button to expand the project and to create a new project have weird symbols on them."
- "Take a lot of inspiration from T3's UI"
- "approved"
- "This repo has no AgentWeave session, and must not acquire one."
- "Do the work directly."
- "Stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch."

## Dead ends

- Vite turns CSS imports in Vitest into an empty runtime module. The source contract now uses
  Node `readFileSync` with a test-only TypeScript suppression.
- T3 preview click/snapshot intermittently timed out in a hidden tab. DOM evaluation confirmed
  computed colors/layout; reopening/navigating restored focused interactions.
- Bare `ruff` and the harness Python lacked Ruff. `py -3.11 -m ruff` passed. Black required
  `--fast` because repository target syntax is newer than the checking interpreter.
- `npm run lint` cannot start: ESLint 9 finds no `eslint.config.js`. This is repository tooling,
  not a lint report from changed files.
- A second `git status` exposed concurrent unrelated changes to handoff tooling and Makefile.
  They were preserved; no broad staging was used.

## Verification

- `pytest hub/tests -q` — 602 passed, 8 skipped.
- `npm test` in `hub/ui` — 46 files, 373 tests passed.
- `npx tsc --noEmit` — passed.
- `npm run build` — passed, 2086 modules; existing duplicate-case and chunk-size warnings.
- `py -3.11 -m ruff check` on changed Python — passed.
- `py -3.11 -m black --check --fast` on changed Python — passed.
- `pytest hub/tests/test_ui_staleness.py -q` — 5 passed.
- `openspec validate 2026-08-04-hub-ui-mock-alignment --strict` — valid.
- `git diff --check` — passed before final spec reconciliation.
- Live: 1280×800 light and 390×800 dark; no narrow horizontal overflow; opaque dialog panel;
  `codex-gamma` created in UI; worktree absent at creation and present only after `run-71112661`;
  agent returned exactly `READY`.

Not tested: ESLint could not start due missing flat config. All other listed checks cover the final
implementation state.

## Git state

- Branch `hub-native-experience`; HEAD `89b837e`; dirty only from preserved unrelated work.
- All Hub UI mock-alignment implementation/spec/static files are committed in `89b837e`.
- Concurrent/pre-existing handoff-tooling, Makefile, scripts, exploration, and template changes are
  present and must not be staged with this change.

## Next steps

1. Leave the test Hub on port 8010 running so the user can inspect the result and `codex-gamma`.
2. Continue with the specification-screen roadmap change when the user is ready.
3. Preserve the unrelated staged/untracked handoff-tooling, Makefile, scripts, exploration, and
   template changes; they were intentionally excluded from `89b837e`.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/archive/2026-08-04-2026-08-04-hub-ui-mock-alignment/tasks.md`
- `openspec/changes/archive/2026-08-04-2026-08-04-hub-ui-mock-alignment/design.md`
- `hub/ui/src/App.tsx`
- `hub/ui/src/components/agents/AgentCreateDialog.tsx`
- `hub/hub/api/v1/agents.py`
- `openspec/changes/2026-07-30-hub-native-experience/specs/hub-visual-language/spec.md`
