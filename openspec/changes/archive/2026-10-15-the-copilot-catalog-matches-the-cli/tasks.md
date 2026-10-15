# Tasks — The Copilot catalog matches the CLI

## 0. Rounds and decision

- [x] 0.1 R2: compare this proposal against the code independently. Also run one *prompted* Copilot turn with `--model claude-opus-4.7` on a trial Hub, and record whether a mid-turn `session.model_change` names the substitute. Today's `_model` (`copilot_acp.py:1560-1593`) would then already emit `copilot.model_substituted`, and D3 becomes about timing rather than absence.
  - done 2026-10-12 on the work PC. The comparison is in design.md's round log. The prompted turn was **not** run: R2 was instructed to send no prompt. It moves to task 3.2, whose drive sends one anyway; record there whether a mid-turn event named `claude-sonnet-5`.
- [x] 0.2 R3: an independent comparison against the code, re-deriving D3 and D4's arguments, including R2's D3 ordering (after agent selection) and D4 row 2 (one-shot workers).
  - done 2026-10-12 on the work PC. The comparison is in design.md's round log, and the consumer table is in D4 (R3). No prompt was sent.
- [ ] 0.3 Record the operator's answers to wpc3-a … wpc3-g in `spec-queue/DECISIONS.md`. Then amend D1, D2, D3, D4 and D5 if the answers differ from the recommendations. wpc3-f and wpc3-g must be answered before 1.11, 1.13 and 2.9, and before any MODIFIED block for wpc3-g is written (R3 recommends wpc3-f (4) and wpc3-g (1)).

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 Copy `evidence/help-config-1.0.94-3.txt` to `tests/fixtures/copilot/help-config-1.0.94-3.txt` with the UTF-8 BOM stripped, and delete `help-config-1.0.90.txt`.
  - Point `HELP_CONFIG` (`tests/test_model_catalog_drift.py:396`) at the new fixture.
  - Update the count assertion (`:415`; R3 correction, R2 said `:413`) to 30, and assert that `claude-haiku-5.5` and `grok-4.7` are in the list.
  - The agreement test (`:430`) then fails with 6 drifts.
- [ ] 1.2 `hub/tests/test_model_catalog.py` `TestCopilotCatalog`:
  - `validate_overrides("copilot", {"model": "claude-haiku-5.5"})` is accepted.
  - `{"model": "claude-opus-4.7"}` is refused, and the reason names `claude-haiku-5.5`.
- [ ] 1.3 `validate_overrides` with `stored`:
  - `stored={"model": "claude-opus-4.7"}` with the same override is accepted and kept in `accepted`.
  - `stored={"model": "gpt-5.5"}` with `claude-opus-4.7` is refused. (R3: this fails today too, with a TypeError, because there is no `stored` parameter. It is a control only once the signature exists.)
  - `stored=None` behaves as today. This is a control once the signature exists.
- [ ] 1.4 Trigger route (`hub/tests/`, beside the existing `runtime_overrides` trigger tests). **R3 correction:** R2's version passes on today's code, because `claude-opus-4.7` is still declared, so its resend already returns 200 and `bogus-model` already returns 400.
  - A conversation whose stored `runtime_overrides.model` is `copilot-retired-model`, an id neither the old nor the new catalog declares, written directly to the row, gets the same override sent again. It returns 200 with the value kept. This fails today with a 400.
  - The same conversation sent `bogus-model` returns 400. This is a control.
  - Regression control: a conversation stored on `claude-opus-4.7` and resent returns 200, both today and after 2.1.
- [ ] 1.5 `ConversationResponse.model_unrecognised`:
  - true for the stored `claude-opus-4.7`.
  - false for `claude-haiku-5.5`.
  - false, as a control, when there are no overrides.
- [ ] 1.6 The drift script (**R3: rewritten**; see D2). Monkeypatch `resolve_copilot_executable` and `subprocess.run`, then assert:
  - The comparison still reads `which("copilot") help config`.
  - The output names the version compared against.
  - The output also names the Hub binary's version, from `[<resolved exe>, "--no-auto-update", "--version"]`.
  - A differing Hub version is reported without changing the exit code.

  This fails today, because neither version is printed. Also assert that the script's own loader imports `hub/hub/copilot_probe.py` by path with the Hub package not importable. A bare `spec_from_file_location` plus `exec_module` fails on `@dataclass` (R3, measured), so the loader must register the module in `sys.modules` first, as `read_catalog` does at `:148-152`.
- [ ] 1.7 Adapter session-start model check. The `session/new` fixture is shaped and ordered exactly as `evidence/r2-probe-claude-opus-4.7.log`: result keys `models`, `configOptions`, `modes`, `sessionId` in that order (R2 correction; R1's probe printed them sorted), with `currentModelId` `claude-sonnet-5`. The agent-selection `session/set_config_option` answer follows, carrying the same `model` option. With `claude-opus-4.7` requested, assert:
  - exactly one `copilot.model_substituted`, emitted after agent selection and before the first prompt, with facts `requested` and `resolved`;
  - the turn's usage sample has `model == "claude-sonnet-5"`;
  - a later mid-turn `session.model_change` emits no second diagnostic.
- [ ] 1.7a (R2) The agent-selection answer's `model` option reports a value different from `session/new`'s `currentModelId`: the diagnostic names the agent-selection value. Fails today and under R1's D3. (R3: this answer's shape on 1.0.89-1 is assumed; task 3.2 records the real one, and this fixture is corrected if it differs.)
- [ ] 1.8 Controls and edge cases for 1.7:
  - Requested `auto` gives no session-start diagnostic. Control.
  - Requested `claude-haiku-5.5`, matching `currentModelId`, gives no diagnostic. Control.
  - A result without `models` or `configOptions` (the 1.0.88 shape) gives no diagnostic and no exception. Control.
  - A `session/load` result with a mismatch gives one diagnostic. Not a control: it fails today (R3).
  - (R3) An agent-selection answer shaped like the only captured one (1.0.88: `configOptions` = `mode`, `agent`, `allow_all`; no `model`). It replaces `options` (`copilot_acp.py:2552`), so the check falls back to `models.currentModelId` and gives one diagnostic. Fails today.
  - (R3) The diagnostic's list of offered models excludes `auto`.
- [ ] 1.9 Adapter session-start effort check: requested `max` with `reasoning_effort.currentValue` `medium` emits one `copilot.effort_substituted` with facts `requested`, `resolved` and the offered values. Requested `high` with a matching value emits nothing; this is a control.
- [ ] 1.10 Runner `model_unrecognised` for a stored `claude-opus-4.7` runner is true after the refresh. (R3 correction: not a control. It fails today, because `claude-opus-4.7` is still declared, so the flag is false. The flag's code exists; the test pins it against the new list.)
- [ ] 1.11 (R2) `run_worker` on a non-provider Copilot runner stored on `claude-opus-4.7`, spawn stubbed. Today it spawns; after 2.1 alone it returns `unknown_model` (`worker.py:348-349`). Write the assertion wpc3-f chooses:
  - refusal kept: assert `unknown_model`. This fails on today's code.
  - tolerated: assert a spawn with the stored model. This is a **regression control**: it passes today, fails after 2.1 alone, and must pass again after 2.9.
  - Either way it must exist before 2.1 lands.
- [ ] 1.12 (R3) `hub/ui` vitest for `ModelPicker`: with `effectiveModel="claude-opus-4.7"` and a Copilot catalog that does not declare it, the pill reads `claude-opus-4.7 — unrecognised` and never contains `latest (now Auto)`. Today `current` falls back to Auto (`ModelPicker.tsx:58-59`) and `catalogModelLabel` (`modelCatalog.ts:113-115`) renders `claude-opus-4.7 — latest (now Auto)`, so this fails. Control: a declared model renders its label unchanged.
- [ ] 1.13 (R3; only if wpc3-f is answered (4)) Write-time validation:
  - `PATCH /manager/jobs/{key}` with `{"model": "bogus-model"}` on a Copilot job returns 400. It returns 200 today.
  - A non-provider project `checkpoint_model` set to `bogus-model` returns 400. It returns 200 today.
  - Resaving the unchanged stored value returns 200. Control.

## 2. Implementation

- [ ] 2.1 `hub/hub/model_catalog.py:186-219`: replace `_COPILOT_MODEL_IDS` with the 30 ids of D1, in order, and update the comment to name 1.0.94-3 and D3. Also update the second comment, in the `copilot` entry at `:352-357`, which still names "build 1.0.88" (R2).
- [ ] 2.2 `validate_overrides(cli, overrides, stored=None)`: skip the model check when the override model equals `stored["model"]`. Pass `conversation.runtime_overrides` from `agent_trigger.py:1998`.
- [ ] 2.3 `ConversationResponse` gains a `model_unrecognised: bool`, computed where the response is built, against the bound runner's CLI. Add it to the UI type `hub/ui/src/api/`.
- [ ] 2.3a (R3) `ModelPicker` (`hub/ui/src/components/agents/ModelPicker.tsx:58-61`): when `effectiveModel` is set but `resolveCatalogModel` returns null, label the pill `<value> — unrecognised` (matching `RunnersPage.tsx:390`) instead of falling back to the default's alias label. R2 said "no rendering change", but proposal.md promises the pill says so; this task is what keeps that promise. Also give `ProjectSettingsPanel`'s checkpoint-model select (`:341-359`) an option for a stored undeclared value, so it stops displaying "Use the runner's model". Follow `.claude/rules/hub-ui.md`: rebuild, refresh `hub/hub/static/ui`, and commit it with `hub/ui/src`. Run `npx vitest run` and `npx tsc --noEmit`.
- [ ] 2.4 `scripts/check_model_catalog.py:378-394` (**R3: rewritten**; see D2):
  - Keep comparing against `which("copilot") help config`, the newest build, which is what D1 tracks.
  - Print that build's `--version`.
  - Also resolve the Hub's binary through `hub.copilot_probe.resolve_copilot_executable(None)` (`copilot_probe.py:156`), imported by path with `sys.modules` registration before `exec_module`, as `read_catalog` does. Print its `--no-auto-update --version` labelled "Hub (unpinned runners)", and say when it is older. That is information only, not a drift.
  - Update the docstring: rerun after `copilot update`.
- [ ] 2.5 `hub/hub/copilot_acp.py`:
  - Add a `_session_start_selection(response, options, requested_model, requested_effort)` helper. Call it once, **after** the agent-selection `session/set_config_option` (`:2539-2552`) has updated `options`, and before the first prompt; this covers both `session/new` (`:2513-2515`) and `session/load` (`:2486-2490`). (R2 correction: R1 called it straight after `session/new`/`session/load`.)
  - It reads the `model` option's `currentValue` from `options` first, then `response["models"]["currentModelId"]`.
  - It emits through the same diagnostic path as `_model`, and sets `mapper.resolved_model`.
  - It never raises.
- [ ] 2.6 Add the wording of `copilot.effort_substituted` beside `copilot.model_substituted`'s.
- [ ] 2.7 Update `openspec/specs/model-catalog/spec.md` from this change's delta at archive time.
- [ ] 2.8 Run `ruff`, `black --check` and `mypy src/`, then `pytest tests/test_model_catalog_drift.py hub/tests/test_model_catalog.py hub/tests/test_copilot_acp_mapper.py -q`, plus the trigger, worker, manager and drift-script test files, and `cd hub/ui && npx vitest run && npx tsc --noEmit`.
- [ ] 2.9 (R2) Implement wpc3-f's answer in `hub/hub/worker.py:348-349` (and the spec), or, if the refusal is kept, record it in the release notes. Blocked on 0.3. (R3) Under option (4), this also adds the write-time checks to `api/v1/manager.py`'s PATCH and to `projects.py:586-603` for non-provider runners, with the runner registry's `current` tolerance, and updates `model_is_declared`'s docstring.

## 3. Live verification

- [ ] 3.1 On the trial Hub `:8010`, which must never be `:8000`, trigger a Copilot agent with `runtime_overrides.model = "claude-haiku-5.5"`. Expect 202/200, not 400, and `turn_usage.model == "claude-haiku-5.5"`.
- [ ] 3.2 Write `claude-opus-4.7` into a trial conversation's `runtime_overrides`, then send from the dashboard composer:
  - The send is accepted.
  - A `copilot.model_substituted` diagnostic appears, naming `claude-sonnet-5`.
  - The turn's usage row records `claude-sonnet-5`.
  - (moved from 0.1 by R2) Record from the run's raw events whether a mid-turn `session.model_change` also named `claude-sonnet-5`; if it did, only one diagnostic may appear.
  - (R3) Record the raw agent-selection `session/set_config_option` answer on this build, and whether it carries a `model` option. Correct the 1.7/1.7a fixtures if its shape differs.
  - (R3) Let the titler run on that conversation. Record whether `copilot -p --model claude-opus-4.7` substitutes the model or errors.
- [ ] 3.3 Run `py -3.11 scripts/check_model_catalog.py --provider copilot` and paste its output into this change, including both version lines. **R3 correction:** expect **zero** drifts against the newest build, which D1 was copied from, plus an information line naming the Hub's older build (1.0.89-1 here). R2 expected nine drifts because its D2 compared against the Hub's build; R3 reverted that.
