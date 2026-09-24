## 0. Rounds

- [x] 0.1 R2: re-derive the proposal independently against `AgentSettingsControls.tsx`, `ProjectSettingsPanel.tsx`, `RunnersPage.tsx` and `schemas/runners.py`. Grep `hub/ui/src` for every other `<option>` rendered from a runner and add any it finds to design D2. Record the result in `design.md`'s round log
- [x] 0.2 R3: a second independent re-derivation. `openspec validate a-runner-choice-names-its-model --strict` passes

## 1. Tests first — each fails on today's code

- [ ] 1.1 `hub/ui/src/__tests__/runnerOptionLabel.test.ts`: the rows of design D1, in the pinned format `{name} — {model part} ({cli})`. Two same-named runners with different models get different labels
- [ ] 1.1b Same file (operator review): a runner shaped as the Hub creates it (`name: 'Claude Code — Opus 5.5'`, `cli: 'claude'`, `model: 'claude-opus-5-5'`, the name `agents.py:713` builds) renders `Claude Code — Opus 5.5 (claude)`, with the model label occurring exactly once; the same runner with `model` changed to Haiku renders both labels; with `{ model: <haiku id> }` passed as the override it names Haiku
- [ ] 1.2 Extend `runnerPickerCannotRun.test.tsx`: two same-named `claude` runners, served in `created_at` order, render distinct options, and each names its model's catalog label
- [ ] 1.3 Extend `projectSettingsPanel.test.tsx`: the title-runner options name each runner's own model; the checkpoint-runner options name the fixture's `checkpoint_model` (Haiku, `:46`) whatever each runner records, and each runner's own model once `checkpoint_model` is cleared (operator review; `checkpoint_trigger.py:153`)

## 2. The fix

- [ ] 2.1 Add `hub/ui/src/lib/runnerLabel.ts` with `runnerOptionLabel` (design D1)
- [ ] 2.2 Use it in `AgentSettingsControls.tsx` (`RunnerPicker`) and in both `ProjectSettingsPanel.tsx` selects; the checkpoint-runner select passes `{ model: form.checkpoint_model }`
- [ ] 2.3 Run `cd hub/ui && npm run lint && npx vitest run`. Then run `make ui` (or `scripts/refresh_ui_bundle.py`) and commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive

- [ ] 3.1 On the trial Hub `:8010`, create two `claude` runners named `Twin` on two declared models. Read the runner select's options in an agent's Settings, then both runner selects in project settings. Record the option texts verbatim
