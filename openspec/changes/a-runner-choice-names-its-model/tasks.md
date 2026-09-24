## 0. Rounds

- [x] 0.1 R2: re-derive the proposal independently against `AgentSettingsControls.tsx`, `ProjectSettingsPanel.tsx`, `RunnersPage.tsx` and `schemas/runners.py`. Grep `hub/ui/src` for every other `<option>` rendered from a runner and add any it finds to design D2. Record the result in `design.md`'s round log
- [ ] 0.2 R3: a second independent re-derivation. `openspec validate a-runner-choice-names-its-model --strict` passes

## 1. Tests first — each fails on today's code

- [ ] 1.1 `hub/ui/src/__tests__/runnerOptionLabel.test.ts`: the four rows of design D1. Two same-named runners with different models get different labels
- [ ] 1.2 Extend `runnerPickerCannotRun.test.tsx`: two same-named `claude` runners, served in `created_at` order, render distinct options, and each names its model's catalog label
- [ ] 1.3 Extend `projectSettingsPanel.test.tsx`: the checkpoint-runner and title-runner options name their model

## 2. The fix

- [ ] 2.1 Add `hub/ui/src/lib/runnerLabel.ts` with `runnerOptionLabel` (design D1)
- [ ] 2.2 Use it in `AgentSettingsControls.tsx` (`RunnerPicker`) and in both `ProjectSettingsPanel.tsx` selects
- [ ] 2.3 Run `cd hub/ui && npm run lint && npx vitest run`. Then run `make ui` (or `scripts/refresh_ui_bundle.py`) and commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive

- [ ] 3.1 On the trial Hub `:8010`, create two `claude` runners named `Twin` on two declared models. Read the runner select's options in an agent's Settings, then both runner selects in project settings. Record the option texts verbatim
