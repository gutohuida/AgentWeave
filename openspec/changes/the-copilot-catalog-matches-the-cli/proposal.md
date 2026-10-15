# Proposal — The Copilot catalog matches the CLI

Finding **WPC-3 (medium)**, from the work-PC Copilot drive (`.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md:53-58`). This is Round 1, written 2026-10-12 and verified against HEAD `6208e9a5`, with Round 2's corrections (same day) marked **R2** and Round 3's marked **R3**. Nothing here is implemented yet.

## Why

`CATALOG["copilot"]` is a fixed tuple, `_COPILOT_MODEL_IDS` (`hub/hub/model_catalog.py:186-219`). Its comment says it is "build 1.0.90 … in its order", and it is exactly that: it matches `tests/fixtures/copilot/help-config-1.0.90.txt` entry for entry. The CLI has moved since. The repository's own drift script, run against today's `copilot help config` (`evidence/help-config-1.0.94-3.txt`), reports six drifts and exits 1:

```
[declared but gone]   claude-opus-4.7, gemini-3.5-flash, gemini-3.6-flash, kimi-k2.7-code
[listed but undeclared] claude-haiku-5.5, grok-4.7
```

The cost is concrete. The drive's `POST /agent/trigger` with `runtime_overrides.model = "claude-haiku-5.5"` got a 400 twice (`hub.log` lines 208 and 389), "not a model 'copilot' declares". The rejection comes from `validate_overrides` (`model_catalog.py:634-676`), reached from `agent_trigger.py:1998-2004`. Yet Copilot runs `claude-haiku-5.5` on this account: `session/new` with `--model claude-haiku-5.5` answers `currentModelId: "claude-haiku-5.5"` (`evidence/r1-probe-claude-haiku-5.5.log`). The catalog refused a model the CLI would have run.

Both guards against this exist, and neither fired:

- **The pinning test** (`tests/test_model_catalog_drift.py:396`, `:415`, `:430`) compares the catalog with a captured fixture. The fixture is still 1.0.90, so it stays green.
- **The live drift script** (`scripts/check_model_catalog.py --provider copilot`) is a manual step by design (archived D13 R2, its own docstring). Nobody reran it when the CLI updated. It also asks a different binary from the one the Hub runs:
  - The script runs `copilot help config` through the npm shim, which auto-updates to 1.0.94-3.
  - The Hub spawns the native `copilot.exe` with `--no-auto-update` (`copilot_acp.py:1944`; `copilot_probe.py:55`). On this machine that is **1.0.89-1** (`evidence/help-config-no-auto-update-1.0.89-1.txt`).
  - The two help texts disagree in both directions. 1.0.89-1 lists none of `claude-haiku-5.5`, `claude-sonnet-5.5`, `gpt-6.1-sol`, `grok-4.6` or `grok-4.7`, but it still lists all four removed models. Its ACP `session/new` nevertheless accepts `claude-haiku-5.5` and `claude-sonnet-5.5`.
  - **R3:** so the model list is the service's, not the build's. Every model 1.0.89-1 offers live on this account is in the newest help, and none of the four removed models is offered. The catalog and the drift script therefore both follow the newest help. The Hub's build is named for information only (D1, D2).

**The help text is a static document. What the account can run is a different list.** `session/new` answers with `models.availableModels`: 22 entries on this account, each with a premium multiplier. That list contains no `grok-*`, `kimi-*`, `mai-*`, `claude-fable-*`, `claude-sonnet-4.6` or `gpt-6.1-sol`. A model outside that list, whether removed (`claude-opus-4.7`) or newly documented (`grok-4.7`), is **silently replaced by `claude-sonnet-5` at session start**. No `session.warning`, `session.error` or `session.model_change` event is sent (`evidence/README.md`).

**A model that leaves the catalog does not leave the database.** A runner, a project's `checkpoint_model`, a manager job, or a conversation's stored `runtime_overrides`, keeps the old value after a refresh. Four things happen to it:

- **Peer, scheduled and inherited triggers** use the stored value "trusted rather than re-validated per turn" (`agent_trigger.py:1008-1022`). They pass `--model <removed>`, and Copilot swaps it silently.
  - The Hub's `copilot.model_substituted` diagnostic (`copilot_acp.py:1560-1593`) listens only to mid-turn session events. It never reads `session/new`'s `currentModelId`.
  - `turn_usage.model` falls back to the *requested* model (`copilot_acp.py:2355`) when no event names one. So the record can name a model that never ran.
- **The dashboard composer** seeds its pending overrides from `conversation.runtime_overrides` (`AgentOutputPanel.tsx:297-310`) and resends them on every send (`:1058`). After a refresh, a conversation stored on a removed model gets a **400 on every operator message** until the operator changes the model pill.
- **Runners** already handle this case: `_reject_undeclared_model` tolerates the stored value on update (`runners.py:33-53`, `:216`), and `RunnerResponse.model_unrecognised` makes the dashboard say "— unrecognised" (`schemas/runners.py:58-89`). Conversations have neither.
- **R2: one-shot workers do not.** Checkpoints, distillation, vault checks and vault reports run on a stored model (`project.checkpoint_model` or `job.model`, else `runner.model`), and `run_worker` refuses any model the catalog does not declare (`worker.py:348-349`), with no tolerance for a stored one. After the refresh, all of that background work stops with `unknown_model` for anything stored on a removed id. R1 missed this; it is design D4 row 2 and question wpc3-f.
- **R3: the composer pill misnames it.** `ModelPicker` falls back to the default model when the stored value is undeclared, and so labels the pill "`claude-opus-4.7` — latest (now Auto)". That presents a removed model as an alias of Auto, while Copilot runs `claude-sonnet-5` (`ModelPicker.tsx:58-61`, `modelCatalog.ts:113-115`). The project settings' checkpoint-model select shows "Use the runner's model" for the same value.

**Effort has drifted the same way.** The catalog offers `low, medium, high, xhigh, max` for every Copilot model (`model_catalog.py:370-377`). Copilot's `reasoning_effort` option is per model: `gpt-5-mini` offers `low, medium, high`, and `gpt-5.5` offers `none, low, medium, high, xhigh`. `--model gpt-5-mini --reasoning-effort max` silently becomes `medium`.

## What changes

1. **Refresh the list.** `_COPILOT_MODEL_IDS` becomes the 30 models of `copilot help config` 1.0.94-3, in that build's order, after `auto`.
   - Add `claude-haiku-5.5` and `grok-4.7`.
   - Drop `claude-opus-4.7`, `gemini-3.6-flash`, `gemini-3.5-flash` and `kimi-k2.7-code`.
   - `claude-opus-4.8-fast` and every `gpt-6*` model are already present, so they need no change.
   - The comment names the new build, and so does the second comment at `model_catalog.py:352-357`, which still names 1.0.88 (R2).
   - The pinning fixture becomes `tests/fixtures/copilot/help-config-1.0.94-3.txt`, and the tests that read it change with it (30 entries).
2. **The drift script compares against the list the catalog tracks, and names the Hub's build.** `scripts/check_model_catalog.py` keeps comparing against the newest `copilot help config` (the auto-updating shim), prints that build's version, and also prints the version of the binary the Hub spawns (`--no-auto-update`), as information. R3 reverted R1/R2's switch to the Hub's binary, which contradicted item 1 and reported nine drifts on the day of the refresh, two of them false. It stays a manual script, not a CI gate (D2).
3. **A substituted model is reported at session start, not inferred mid-turn.** After `session/new` or `session/load` **and the agent selection that follows it** (R2), and before the first prompt, the Copilot adapter compares the session's model (the `model` config option, else `models.currentModelId`) with the requested model; `auto` is excluded because it resolves later.
   - On a mismatch it emits `copilot.model_substituted` once. The diagnostic names the account's `availableModels`.
   - It records the resolved model as the model the turn ran, so `turn_usage.model` names what ran.
   - Effort gets the same treatment: the `reasoning_effort` option's `currentValue` is compared with the requested effort (D3).
   - R2: this reports a silent fallback; it does not prevent one, which the existing requirement "The Hub validates overrides before spawning" says the Hub does. Question wpc3-g.
4. **A stored model the catalog no longer declares keeps working and is visibly flagged** (D4).
   - The trigger route accepts an override whose model equals the conversation's already-stored model, as `runners.py` does for a runner's current model. A *newly* chosen undeclared model is still refused.
   - Conversation responses gain `model_unrecognised`, mirroring the runner flag. The composer's model pill names an undeclared stored model "`<id>` — unrecognised" instead of "— latest (now Auto)" (R3: previously promised here, but no task did it).
   - One-shot workers are not covered yet: their handling waits on wpc3-f (R2). R3 recommends validating a worker model when it is written (manager job, checkpoint model) and tolerating it when the worker runs.

Out of scope, offered as open questions:

- Reading the account's model list into the catalog at probe time (option (c), request R11).
- Per-model effort lists in the catalog.

## Capabilities

### Modified Capabilities

- `model-catalog`: the Copilot requirement now covers the source of the list, a stored model that has left it, and a model or effort Copilot substitutes at session start.

## Impact

- `hub/hub/model_catalog.py`: the tuple and its comment.
- `hub/hub/copilot_acp.py`: read the session's model and `reasoning_effort` after `session/new`/`session/load` and agent selection, emit the diagnostic and set `resolved_model`.
- `hub/hub/worker.py`: depends on wpc3-f (R2). Under R3's recommended option (4), `hub/hub/api/v1/manager.py` and `hub/hub/api/v1/projects.py` also gain write-time checks.
- `hub/hub/api/v1/agent_trigger.py`: tolerate the unchanged stored model.
- `hub/hub/api/v1/agent_chat.py:112` `ConversationResponse`: a computed `model_unrecognised`.
- `hub/ui/`: `ModelPicker` labels an undeclared stored model as unrecognised, and the checkpoint-model select shows it (R3). This needs a UI bundle refresh.
- `scripts/check_model_catalog.py`, `tests/test_model_catalog_drift.py`, `tests/fixtures/copilot/`, `hub/tests/test_model_catalog.py`, and new adapter and trigger tests.
- No migration: `runtime_overrides` is already JSON, and the flag is computed.
- Overlaps: none in `openspec/changes/`. Adjacent work:
  - `copilot-spend-is-counted-in-its-own-units` reads Copilot-reported spend. `availableModels[]._meta.copilotUsage` is the per-model multiplier it may want, but this change does not touch it.
  - Request R11 (`spec-queue/REQUESTS.md:293-308`) is option (c).
