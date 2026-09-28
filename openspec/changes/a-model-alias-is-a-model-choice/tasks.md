## 0. Rounds and decision

- [x] 0.1 R2: re-derive the proposal independently. Grep every caller of `ProviderDescriptor.model`, `get_provider` and `model_is_declared`, and every place a stored `Runner.model` is compared or rendered (including `hub/ui/src`). Confirm design D1's table is complete. Record the result in `design.md`'s round log
- [x] 0.2 R3: a second independent re-derivation. `openspec validate a-model-alias-is-a-model-choice --strict` passes
- [x] 0.3 The operator answered D2's alias question in the daily review, recorded in `spec-queue/APPROVALS.md`'s 2026-09-27 row: "D2.2: aliases are stored as written; a runner-registry MODIFIED delta was added. The Add-agent default stays `claude-sonnet-5`." — option C, matching design.md's recommendation. No `spec-queue/DECISIONS.md` row: the question was answered directly in review, not left open

## 1. Tests first — each fails on today's code

- [x] 1.1 Design test 1: every door accepts `opus`, and the routes store `"opus"`: `POST /runners`, `POST /agents`, **and `PATCH /runners/{id}`** on an existing runner (operator review), plus `validate_overrides` and `worker.model_is_declared` — `hub/tests/test_a_model_alias_is_a_model_choice.py`
- [x] 1.2 Design test 2: `build_command` passes `--model opus` as written — same file
- [x] 1.3 Design test 3: `model_unrecognised` is false for an alias — same file
- [x] 1.4 Design test 4: an unknown model's refusal lists the aliases — same file
- [x] 1.5 Deleted `test_a_published_alias_is_refused_naming_the_id_it_stands_for` (`hub/tests/test_a_refusal_says_what_would_work.py`), naming this change in a docstring left in its place; its now-unused `OPUS` fixture constant removed too
- [x] 1.6a Design test 7 (UI): the composer `ModelPicker` shows an alias-stored runner's model, not the provider default — `hub/ui/src/__tests__/modelPicker.test.tsx`
- [x] 1.6 Design test 6 (UI): the `Latest` group, in catalog order, and a stored alias selected with no `Unrecognised` chip — `hub/ui/src/__tests__/runnersUi.test.tsx`, plus `AgentCreateDialog`'s own Latest-group test in `agentCreationUi.test.tsx` and `runnerOptionLabel`'s alias-naming tests

## 2. The fix

- [x] 2.1 `ProviderDescriptor.model` resolves aliases (design D1). Rewrote `undeclared_model_reason` without the alias branch, listing aliases among the accepted values
- [x] 2.2 `agents.py` find-or-create names an alias runner `"<provider label> — <alias> (latest)"`
- [x] 2.3 Rewrote `worker.model_is_declared`'s docstring (the two gates stay equal, now including aliases)
- [x] 2.4 UI: `resolveCatalogModel` + `catalogModelLabel` in `api/modelCatalog.ts`; `RunnerForm`, `AgentCreateDialog` and the checkpoint-model select offer the `Latest` group; `ModelPicker.tsx` resolves aliases (`current`) and its active mark compares `model.id === current?.id`; `storedIsDeclared` counts an alias; `runnerOptionLabel` renders an alias's model part as `{alias} (latest)` (design D2; a Hub-created alias runner reads `Claude Code — opus (latest) (claude)`, tested)
- [x] 2.5 `py -3.11 -m pytest tests/ -q`: **553 passed, 3 skipped**. `py -3.11 -m pytest hub/tests/ -q` with `claude` stripped from PATH: first run **1 failed, 5093 passed, 86 skipped** — `hub/tests/test_worker.py::test_a_model_is_checked_against_the_catalog_before_anything_is_spawned` still asserted the pre-D1 behaviour (`assert not model_is_declared("claude", "haiku")`), a stale regression this change's own tasks never touched that file to update. Fixed the assertion and its comment to match D1 (a declared alias now passes this gate); second run **5094 passed, 86 skipped**. `ruff check` + `black --check --target-version py311` on every touched Python file including the fix: clean. `cd hub/ui && npx vitest run`: **168 files, 1731 tests passing**. `npm run lint`: clean. `py -3.11 scripts/refresh_ui_bundle.py --check`: bundle already matches current source, no rebuild needed. Committed `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive

- [ ] 3.1 On the trial Hub `:8010`: create a runner on `haiku` through the form, bind an agent to it, and run one real turn (Haiku, per the cheap-models rule). Record `turn_usage.model`, which should be the full id the CLI resolved, while `runners.model` still reads `haiku`
