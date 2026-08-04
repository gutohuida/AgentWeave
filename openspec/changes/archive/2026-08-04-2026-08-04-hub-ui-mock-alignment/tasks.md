# Implementation plan

## Working protocol

1. Re-read proposal, design, both delta specs, and the reachable mock screens before every phase.
2. Tests open every phase; implementation begins only after the failing contract is demonstrated.
3. Preserve current project/conversation routes and feature behavior while changing presentation.
4. Commit each verified phase with a title naming `Hub UI mock alignment`.
5. Use only `testbed/` for live AgentWeave state.

## 0. Baseline and visual contracts

- [x] 0.1 Add token/reference tests covering mock palette, defined dialog surfaces, radii, motion,
      fonts, and absence of undefined semantic token references.
- [x] 0.2 Add shell/component tests for project header actions, absence of the permanent desktop
      status strip, bounded content hierarchy, and narrow/desktop composition.
- [x] 0.3 Capture current shared-browser evidence at 1280×800 and a narrow viewport in both themes;
      record the intentional differences from the mock.
- [x] 0.4 `/handoff`.

## 1. Shell and visual language

- [x] 1.1 Align canonical dark/light tokens, default rail width, control states, and lifted surfaces
      to the mock; retain self-hosted fonts and reduced-motion behavior.
- [x] 1.2 Recompose the desktop shell into the mock's project rail, project header/actions, compact
      tabs, and bounded content plane; relocate global status/settings affordances without hiding
      actionable conditions.
- [x] 1.3 Recompose Overview into the mock's quiet agent, attention, task/spec/job, and recent
      activity hierarchy using live data and current destinations.
- [x] 1.4 Apply the shared visual primitives to project tabs, environment sub-navigation, empty
      states, and dialogs touched by the shell so no screen reads as a legacy island.
- [x] 1.5 Verify light/dark, keyboard, reduced motion, resizable rail, narrow/wide layouts, and mock
      comparison scenarios.
- [x] 1.6 `/handoff`.

## 2. Project controls and dialogs

- [x] 2.1 Add failing tests proving project dialogs have a defined opaque panel fill over a scrim in
      both themes and preserve focus/Escape behavior.
- [x] 2.2 Replace the undefined `--surface-1` usage and align the project dialog with the shared
      lifted-surface primitive.
- [x] 2.3 Add failing tests rejecting literal/mojibake project action glyphs and asserting Lucide
      open/create/expand/collapse icons with accessible names.
- [x] 2.4 Implement the icon controls and the mock's visible `+ Add project` affordance without
      conflating open-existing and create-new actions.
- [x] 2.5 Verify open, create, expand, collapse, focus restoration, and typed-error flows live.
- [x] 2.6 `/handoff`.

## 3. Operator agent creation

- [x] 3.1 Add backend tests for successful creation, shared name validation, duplicate refusal,
      same-project runner/charter enforcement, launchability refusal, stable color assignment, SSE,
      and no eager worktree.
- [x] 3.2 Implement the typed project-scoped operator agent-creation endpoint and service.
- [x] 3.3 Add frontend tests for the project-header Add agent action, name/runner/optional-charter
      dialog, disabled launchability reasons, inline failures, query invalidation, and navigation to
      the created agent.
- [x] 3.4 Implement project-keyed creation hooks and the accessible Add agent dialog.
- [x] 3.5 Live-create a third Codex agent in the testbed, confirm it appears immediately, launch one
      minimal turn, and verify its isolated worktree is provisioned only then.
- [x] 3.6 `/handoff`.

## 4. Closeout

- [x] 4.1 Run focused and complete Hub/UI suites, TypeScript, production build, changed-file
      Ruff/Black, strict OpenSpec validation, and `git diff --check`.
- [x] 4.2 Copy the verified UI build into `hub/hub/static/ui` and confirm the packaged Hub serves the
      same bundle without a staleness warning.
- [x] 4.3 Live-verify the mock comparison, project dialogs/icons, and new-agent flow at wide/narrow
      widths in light/dark mode using the shared browser.
- [x] 4.4 Sync the implemented requirements, reconcile the umbrella visual-language and
      agent-identity notes, archive the change, and commit.
- [x] 4.5 Final `/handoff`.

## Verification evidence

- The visual contracts failed on all five pre-change assertions, then passed after implementation.
- Shared-browser verification covered 1280×800 and 390×800. At 390 px the shell stacks, the rail
  spans 390 px, the resizer is hidden, and document width remains 390 px. Computed dark tokens were
  `rgb(16,19,27)` background, `rgb(23,27,42)` rail, and `rgb(20,24,39)` header.
- The live agent dialog computed an opaque white panel over `rgba(0,0,0,0.4)` in light mode.
- `codex-gamma` was created from runner `runner-d6739934` with the QA charter. Its worktree did not
  exist at creation, appeared on run `run-71112661`, and the turn returned exactly `READY`.
- Complete verification: Hub 602 passed / 8 skipped; UI 373 passed; TypeScript and production build
  passed; changed Python files passed Ruff and Black; packaged UI freshness passed 5 tests; strict
  change validation and `git diff --check` passed. ESLint could not start because the repository's
  ESLint 9 setup has no `eslint.config.*` file.
