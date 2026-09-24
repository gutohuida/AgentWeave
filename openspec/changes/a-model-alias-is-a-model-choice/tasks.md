## 0. Rounds and decision

- [x] 0.1 R2: re-derive the proposal independently. Grep every caller of `ProviderDescriptor.model`, `get_provider` and `model_is_declared`, and every place a stored `Runner.model` is compared or rendered (including `hub/ui/src`). Confirm design D1's table is complete. Record the result in `design.md`'s round log
- [ ] 0.2 R3: a second independent re-derivation. `openspec validate a-model-alias-is-a-model-choice --strict` passes
- [ ] 0.3 The operator answers D2's alias question (accept as written / accept and normalise / refuse), recorded in `spec-queue/DECISIONS.md`. If the answer is "refuse", withdraw this change and close F221 as fixed by `568f868`

## 1. Tests first — each fails on today's code

- [ ] 1.1 Design test 1: every door accepts `opus`, and the routes store `"opus"`
- [ ] 1.2 Design test 2: `build_command` passes `--model opus` as written
- [ ] 1.3 Design test 3: `model_unrecognised` is false for an alias
- [ ] 1.4 Design test 4: an unknown model's refusal lists the aliases
- [ ] 1.5 Delete `test_a_published_alias_is_refused_naming_the_id_it_stands_for`, naming this change in the commit
- [ ] 1.6a Design test 7 (UI): the composer `ModelPicker` shows an alias-stored runner's model, not the provider default
- [ ] 1.6 Design test 6 (UI): the `Latest` group, in catalog order, and a stored alias selected with no `Unrecognised` chip

## 2. The fix

- [ ] 2.1 `ProviderDescriptor.model` resolves aliases (design D1). Rewrite `undeclared_model_reason` without the alias branch, listing aliases among the accepted values
- [ ] 2.2 `agents.py` find-or-create names an alias runner `"<provider label> — <alias> (latest)"`
- [ ] 2.3 Rewrite `worker.model_is_declared`'s docstring (the two gates stay equal, now including aliases)
- [ ] 2.4 UI: `resolveCatalogModel` in `api/modelCatalog.ts`; `RunnerForm`, `AgentCreateDialog` and the checkpoint-model select offer the `Latest` group; `ModelPicker.tsx:55` resolves aliases; `storedIsDeclared` counts an alias; `runnerOptionLabel` renders an alias, if it exists
- [ ] 2.5 Run `py -3.11 -m pytest hub/tests/ -q` with `claude` stripped from PATH, then the CLAUDE.md lint block, then `make ui`. Commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive

- [ ] 3.1 On the trial Hub `:8010`: create a runner on `haiku` through the form, bind an agent to it, and run one real turn (Haiku, per the cheap-models rule). Record `turn_usage.model`, which should be the full id the CLI resolved, while `runners.model` still reads `haiku`
