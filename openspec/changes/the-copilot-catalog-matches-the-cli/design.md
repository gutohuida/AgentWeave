# Design — The Copilot catalog matches the CLI

Round 1, 2026-10-12; Round 2, 2026-10-12 (corrections marked **R2**); Round 3, 2026-10-12 (corrections marked **R3**). Finding WPC-3. Evidence lives in `evidence/` (see `evidence/README.md`). Every claim marked VERIFIED was run on this machine against HEAD `6208e9a5`, without sending a prompt.

## What is true today

| Fact | Source | Status |
|---|---|---|
| The catalog equals `copilot help config` 1.0.90, in that build's order (32 ids plus `auto`). | `model_catalog.py:186-219`; `tests/fixtures/copilot/help-config-1.0.90.txt` | VERIFIED |
| Against 1.0.94-3's help there are 6 drifts: 4 gone, 2 undeclared. | `scripts/check_model_catalog.py --provider copilot --help-config evidence/help-config-1.0.94-3.txt` exits 1 | VERIFIED |
| `copilot --version` reports 1.0.94-3, but `copilot.exe --no-auto-update --version` reports 1.0.89-1. The Hub always passes `--no-auto-update`. | `copilot_acp.py:1944`, `copilot_probe.py:55`, `runner_adapters/copilot.py:51` (one-shot workers) | VERIFIED; R2 re-ran both `--version` calls. The executable is `copilot_probe.resolve_copilot_executable` (`copilot_probe.py:156`), the npm package's native `copilot-win32-x64\copilot.exe`. The npm `package.json` says 1.0.83, so neither version is the package's. |
| Against 1.0.89-1's help there are 3 drifts: `claude-sonnet-5.5`, `gpt-6.1-sol` and `grok-4.6` are not printed. | `evidence/help-config-no-auto-update-1.0.89-1.txt` | VERIFIED |
| `session/new` returns `models.availableModels` (22 on this account) and `currentModelId`, plus `model` and `reasoning_effort` config options. | `evidence/r1-probe-*.log` | VERIFIED on 1.0.89-1. The archived 1.0.88 captures had none of these. |
| A model outside `availableModels` becomes `claude-sonnet-5` at `session/new`, with no event. | the `claude-opus-4.7` and `grok-4.7` probes | VERIFIED, for the probe's window only: no event arrived in the seconds after `session/new`, with no prompt sent (R2 re-ran `claude-opus-4.7`). |
| `claude-haiku-5.5` runs, although the catalog refuses it. | the `claude-haiku-5.5` probe; `hub.log` 208/389 | VERIFIED |
| Effort is per model, and an unsupported effort becomes `medium` silently. | the `gpt-5-mini` / `gpt-5.5` / effort-`max` probes | VERIFIED. **R2** added the control R1 lacked: `gpt-5.5 --reasoning-effort high` reports `high` (`evidence/r2-probe-gpt-5.5-effort-high.log`), so the flag is honoured and `max`→`medium` is a fallback, not an ignored flag. |
| `session/new`'s result keys arrive in the order `models`, `configOptions`, `modes`, `sessionId`. | `evidence/r2-probe-claude-opus-4.7.log` (`result keys (as sent)`) | VERIFIED (R2). R1's probe printed them sorted. |
| The session also offers an `agent` config option, and the adapter selects the Hub's agent with `session/set_config_option` before the first prompt; its answer replaces `options`. The agent file carries `model:` and `reasoningEffort:` frontmatter. | `copilot_acp.py:2533-2552`; `copilot_home.py:147-159`; `agent_trigger.py:3539-3560`; `agents.py:1945` | VERIFIED by reading (R2) |
| Whether selecting the Hub's agent changes the session's current model or effort | — | UNVERIFIED (R2). Every probe selected no agent and ran under the operator's `~/.copilot`. |
| One-shot workers (checkpoint, handover, distillation, vault check, vault report) refuse a model the catalog does not declare, and their model is a *stored* value. | `worker.py:348-349`; `runner_provider.py:221-233`; `distillation.py:182`; `vault_spec_check.py:246`; `vault_reports.py:116` | VERIFIED by reading (R2). See D4. |
| With no `--model` (Auto), `currentModelId` is `claude-sonnet-5`. That is the default, not Auto's choice. | the no-model probe | VERIFIED |
| `copilot --model bogus-xyz --version` exits 0, while `--reasoning-effort bogus` exits 1. | argument-parsing probe | VERIFIED |
| `copilot.model_substituted` is emitted only from mid-turn `session.model_change` / `auto_mode_resolved` / `tools_updated`. | `copilot_acp.py:1560-1593` | VERIFIED by reading |
| Whether a mid-turn event names the substituted model when the request was a concrete model | — | UNVERIFIED. It needs a prompt (R2 or IMPL). |
| **R3:** The model list is the service's, not the build's. The Hub's own 1.0.89-1 binary offers 21 concrete models live, and every one is in D1's list (none missing). That includes `claude-haiku-5.5` and `claude-sonnet-5.5`, which its own `help config` omits. It does **not** offer `claude-opus-4.7`, which its help still lists. | `evidence/r2-probe-claude-opus-4.7.log` (`OPTION model`), compared with both help captures through `parse_copilot_models` | VERIFIED (R3). `r1-probe-claude-haiku-5.5.log` shows 1.0.89-1 reporting `currentModelId` `claude-haiku-5.5`, so it runs a model its help does not document. |
| **R3:** The only captured answer to the agent-selection `session/set_config_option` is from 1.0.88. It is `{"configOptions": [...]}` with ids `mode`, `agent`, `allow_all`, and **no `model` option**. No capture on 1.0.89-1 or later exists. | `hub/tests/fixtures/copilot_acp/turn_write_shell_mcp.jsonl` (recv id 3) | VERIFIED (R3). The shape of that answer on the Hub's current build is UNVERIFIED. |
| **R3:** Importing `hub/hub/copilot_probe.py` by path fails unless the module is put in `sys.modules` before `exec_module`. The failure is `AttributeError: 'NoneType' object has no attribute '__dict__'`, from `@dataclass` `_Verdict` (`copilot_probe.py:200`). This is the trap `read_catalog` already documents (`scripts/check_model_catalog.py:148-152`). With the registration, `resolve_copilot_executable(None)` returns the native `copilot-win32-x64\copilot.exe`. | measured on the work PC | VERIFIED (R3) |

## Options for keeping the list right (open question wpc3-a)

| | What it is | What already exists | What it would not fix |
|---|---|---|---|
| **(a)** One-off refresh plus a pinned test | Refresh the tuple; capture a new fixture; the pinning test compares the two. | The pinning test exists (`tests/test_model_catalog_drift.py:430`). Only its fixture is stale. | The next CLI update. The test pins the catalog to a capture, not to the CLI. |
| **(b)** (a) plus a drift check against the live CLI | Run something that compares the catalog with the installed CLI. | `scripts/check_model_catalog.py --provider copilot` already exists. It is a script, not a skipped test, on purpose: D13 R2 says "a test whose verdict depends on what is installed is not a test". | Nobody runs it. It also reads the auto-updated binary, not the one the Hub spawns. |
| **(c)** Runtime discovery | Read the list from Copilot itself. | `copilot_probe.probe_copilot` already sends a model-free `session/new` in the background and caches a verdict (`copilot_probe.py:392-432`). That response now carries `models.availableModels`, and today it is discarded. | Nothing about which models are *documented*. But the account list is the one that decides what runs. |

The parent's framing of (b), "a test skipped when the CLI is absent", conflicts with archived D13 R2, and this design does not reopen that. The parent's (c) assumed ACP carries no list. It does now: 1.0.89-1's `session/new` returns one. The 1.0.88 captures in the archive predate it.

**R1 recommendation: (a), plus a corrected (b), plus the session-start half of (c).** D1, D2 and D3 below cover these. The probe-time half of (c) is deferred as question wpc3-e.

- The refresh fixes the reported 400.
- The corrected script makes the manual check ask the right binary.
- Reading `currentModelId` at session start turns a silent substitution into a reported one. That matters whatever the static list says, because a list of documented models can never equal any one account's entitlement.

## D1 — The refreshed list

`_COPILOT_MODEL_IDS` becomes `copilot help config` 1.0.94-3 verbatim, in its order. The catalog still starts with `auto`, as today. The list:

claude-sonnet-5.5, claude-sonnet-5, claude-fable-5.1, claude-fable-5, claude-opus-5.5, claude-opus-5,
claude-opus-4.8, claude-opus-4.8-fast, claude-sonnet-4.6, claude-haiku-5.5, claude-haiku-4.5,
gpt-6.1-sol, gpt-6-sol, gpt-6-luna, gpt-6-astra, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna, gpt-5.5,
gpt-5.4, gpt-5.4-mini, gpt-5.3-codex, gpt-5-mini, mai-code-1.1-flash, gemini-3.8-flash,
gemini-3.7-flash, grok-4.7, grok-4.6, grok-4.5, kimi-k3.

- **Why 1.0.94-3 and not 1.0.89-1, the version the Hub runs here.** 1.0.89-1's help omits `claude-sonnet-5.5`, yet that same binary's `session/new` lists `claude-sonnet-5.5` in `availableModels` (`evidence/r1-probe-no-model.log`). The help text of an older build lags the service. The newest documented list is the better superset. **R3:** this is stronger than one model. Every model the Hub's 1.0.89-1 binary offers live is in D1's list, and `claude-opus-4.7`, which 1.0.89-1's help still lists, is not offered live. The model list belongs to the service; a build's help is a dated copy of it. So "the build the Hub runs" is the wrong thing to track for *models*, and D2 must compare against the same newest list (R3 correction below).
- **Why a superset at all.** The catalog serves every operator's account. On this account `grok-*`, `kimi-*`, `mai-*` and `claude-fable-*` are not entitled, and they are substituted, as `grok-4.6` already is today. D3 makes that substitution visible rather than pretending the list can prevent it.
- **The parent's question about `claude-opus-4.8-fast` and `gpt-6-*`**: they are already in the catalog (`model_catalog.py:187-219`), and they stay. The list the parent quoted is the Copilot *app's* entitled list. It equals this account's `availableModels`, not the CLI's help.
- The comment at `model_catalog.py:186` names 1.0.94-3, and gains one sentence: the list is documentation, so entitlement is checked at session start (D3). **R2:** a second comment, in the `copilot` entry at `model_catalog.py:352-357`, also names "build 1.0.88" and changes with it.
- The fixture `tests/fixtures/copilot/help-config-1.0.94-3.txt` is the evidence file with its UTF-8 BOM removed. The 1.0.90 fixture is deleted rather than kept: one capture, one truth.

## D2 — The drift script compares against the list D1 tracks, and names both builds (R3: rewritten)

`scripts/check_model_catalog.py`'s `_copilot_help_config` (`:378-394`) calls `shutil.which("copilot")` and runs `help config` through the npm shim. The shim auto-updates, so today it reads the newest build (1.0.94-3 here). The Hub instead spawns the native binary with `--no-auto-update` (1.0.89-1 here). The two builds can disagree by several releases.

**R1 and R2 had the script read the Hub's binary instead. R3 reverses that, because it contradicts D1.** D1 tracks the newest `help config`, and the delta spec says the list is "the one printed by `copilot help config` of the newest Copilot CLI release the catalog was refreshed against". A drift check against a different build then reports drift by construction. R2 counted it: **nine** drifts on the day the refresh lands. At least two of those nine are demonstrably false: `claude-haiku-5.5` and `claude-sonnet-5.5` are "declared but gone" against 1.0.89-1's help, yet that very binary offers and runs them (facts table, R3). A manual check that is red on day one for reasons that are wrong trains its reader to ignore it.

- **The comparison** stays against the newest build's help, which the shim prints. That is today's `which("copilot") help config`; it is what D1 was copied from, and its result is 0 drifts the day the refresh lands.
- **Version.** The script prints the version of the build it compared against (`copilot --version` through the same shim).
- **The Hub's build.** The script also resolves the Hub's binary with `resolve_copilot_executable(None)` (`hub/hub/copilot_probe.py:156`) and prints its `--no-auto-update --version`. When that build is older, it says so as information. This is not a drift and does not set the exit code. The Hub's build matters for protocol features (the `models` field in `session/new` arrived after 1.0.88), not for which model ids exist.
  - The script is outside the Hub package, so it imports `copilot_probe` by path, as it imports the catalog. **R3 correction to R2:** "stdlib-only module-level imports" is not enough. The by-path import fails unless the module is registered in `sys.modules` before `exec_module`, because of `@dataclass _Verdict` (measured; facts table). The loader must copy `read_catalog`'s registration (`:148-152`), and a test must pin it.
  - `resolve_copilot_executable(None)` is the binary for unpinned runners and for every one-shot. A runner whose config pins `cli` spawns another binary (`copilot_acp` resolves `config.get("cli")`), which the script does not see. It is information only, so that is acceptable; the line says "unpinned runners".
- It stays manual: D13 R2 stands. Its docstring and `docs/` gain the instruction "rerun after `copilot update`". It is not a CI gate.
- Rejected: making the pinning test compare against the live CLI. That is D13 R2's rejected test under another name.
- Rejected (R3): comparing against the Hub's binary (R1/R2's D2). It is inconsistent with D1, and it reports models that run as gone. If the operator answers wpc3-c with (2), D1 changes to the Hub's build, and only then does the comparison move with it.

**History, kept for the round trail.** R1 said the Hub-binary script would report three drifts after the refresh. R2 corrected that to nine (`claude-haiku-5.5`, `claude-sonnet-5.5`, `gpt-6.1-sol`, `grok-4.6` and `grok-4.7` declared but gone; `claude-opus-4.7`, `gemini-3.5-flash`, `gemini-3.6-flash` and `kimi-k2.7-code` listed but undeclared). R3 re-derived those nine and agrees with the count. The nine are why the comparison moved back to the newest build.

## D3 — Substitution is read at session start

The adapter already holds the `session/new` response (`copilot_acp.py:2513-2515`) and the `session/load` response (`:2486-2490`). **R2 correction:** neither is the last word on the session's model before the first prompt. The adapter next selects the Hub's agent with `session/set_config_option` (`:2539-2543`) and replaces `options` with that answer's config options. The agent file it selects carries `model:` and `reasoningEffort:` frontmatter (`copilot_home.py:147-159`), so whether the selection moves the session's model or effort is a real question, and it is UNVERIFIED (no probe selected an agent). The check therefore runs **after agent selection**, on the latest `options`, and still before the first prompt:

1. **Model.** It reads the `model` config option's `currentValue` from the latest `options`, falling back to `models.currentModelId` from the `session/new` or `session/load` result (R1 had the order reversed; `set_config_option`'s answer carries config options, so `currentModelId` can be stale by then). If the requested model is concrete (not `auto`, not None) and differs from what Copilot reports:
   - It emits `copilot.model_substituted`, with the same code, facts (`requested`, `resolved`) and wording as `_model`. The list it names is `models.availableModels[].modelId`.
   - It sets `mapper.resolved_model`, so the mid-turn path does not emit the diagnostic a second time (`:1573` already returns once `resolved_model` is set).
   - `usage_sample` (`:2355`) then records the model that ran.
2. **Effort.** It reads the `reasoning_effort` option's `currentValue` from the latest `options`. If an effort was requested and differs, it emits `copilot.effort_substituted`, with facts `requested`, `resolved` and the offered values.
   - Severity: `info`, like the model diagnostic.
   - It does not fail the run.
3. **Auto.** With `auto` requested, `currentModelId` is the default model and not Auto's choice (VERIFIED). So the session-start check is skipped, and the mid-turn `auto_mode_resolved` path stays the only resolution.

**What each route returns when what it calls raises.** The reads are dictionary lookups on a response the adapter already validated for `sessionId`. If either field is missing (an older CLI, such as the 1.0.88 captures) or has the wrong type, the check does nothing and the turn proceeds as it does today. The check never raises. Raising here would fail a turn that Copilot was ready to run. If agent selection itself fails (`failure is not None`, `:2555`), `options` is still the session's own, and the check runs on it.

**R3: D3's ordering re-derived, and two notes.** The order (after agent selection, config option first, `currentModelId` as fallback) is right: `options = _options_of(selected) or options` (`:2552`) means the latest `options` is the agent answer's whenever it carries any config options, and `_model` returns early once `resolved_model` is set (`:1573`), so a later mid-turn event cannot report twice.
- The agent-selection answer's shape on 1.0.89-1 is uncaptured. The only capture (1.0.88) has no `model` option. If 1.0.89-1 answers the same way, `options` is replaced by a list with no `model`, and the check correctly falls back to `currentModelId`. A test must cover that shape (task 1.8), and task 3.2 must record the real answer so the 1.7/1.7a fixture can be corrected if it differs.
- `models.availableModels` begins with `auto` (`evidence/r2-probe-claude-opus-4.7.log`). When the diagnostic names what Copilot offered, it should leave `auto` out: `auto` is not a substitute Copilot could have chosen at session start. LOW.

**R2: this report sits beside an existing requirement it does not satisfy.** The current spec's "The Hub validates overrides before spawning" (`openspec/specs/model-catalog/spec.md:93-117`) states, as scenario "Silent provider fallback cannot occur", that the Hub has already refused any value a provider would silently replace. For Copilot that is not true today and stays untrue after this change: `max` is a permitted catalog effort that `gpt-5-mini` silently runs as `medium`, and a declared but unentitled model (`grok-4.7`) silently runs as `claude-sonnet-5`. D3 makes the fallback visible; it does not prevent it. This change does not MODIFY that requirement; question wpc3-g asks whether it should.

## D4 — A stored model that has left the catalog

There are three stores, and each needs its own rule. **R2:** there are more than three, and R1's third row was wrong.

| Store | Today, after a refresh | Proposed |
|---|---|---|
| `runners.model` | Saved unchanged (`runners.py:33-53`, `:216`); flagged by `model_unrecognised`; spawned as `--model <old>` **for conversation turns**. One-shot workers refuse it (next row). | Unchanged for turns. D3 now reports what ran. |
| **R2:** the model a one-shot worker is given: `projects.checkpoint_model` else `runners.model` (`runner_provider.py:221-233`, used by `checkpoint_trigger.py:160`, `checkpoint_handover.py:189`, `api/v1/checkpoints.py:182`); `manager_jobs.model` else `runners.model` (`distillation.py:182`, `vault_spec_check.py:246`, `vault_reports.py:116`) | **Refused.** `run_worker` checks `model_is_declared` with no stored-value tolerance (`worker.py:348-349`) and returns `WorkerResult("unknown_model")`. So after the refresh, a runner, project checkpoint model or manager job stored on `claude-opus-4.7` stops checkpoints, handovers, distillation, vault checks and vault reports. `checkpoint_model` is catalog-checked only for provider runners (`projects.py:586-603`); `ManagerJob.model` (`db/models.py:1106`) is not checked at all, so either can already hold any string. Conversation titling uses the same stored model but builds its own command (`conversation_titles.py:268`) and has no gate, so it spawns the old id and Copilot substitutes it (**R3:** unverified for `-p`; only ACP was probed). | **Open (wpc3-f; R3 recommends option 4).** R1 did not see this row. Either `model_is_declared` tolerates a stored value (the worker cannot tell stored from new: every worker model is stored), or the refresh is accepted as breaking those workers until the operator re-picks, and the release notes say so. Not decided here. No row on the work-PC drive database stores a removed model (R2, read-only), so the exposure is latent on this machine. |
| `conversations.runtime_overrides.model` | Peer and scheduled turns spawn it silently (`agent_trigger.py:1008-1022`). The dashboard composer resends it, and the trigger route answers **400 on every send** (`agent_trigger.py:1998-2004`). | The trigger route tolerates an override model equal to the conversation's stored one, as `_reject_undeclared_model` does with `current`. Newly choosing an undeclared model stays refused. `ConversationResponse` (`agent_chat.py:112`) gains a computed `model_unrecognised`. |
| A model newly chosen through a route: agent creation (`create_operator_agent`, `agents.py:727-732`), runner creation (`runners.py:86`), and removing a runner's provider (`:194`, which judges the left-behind model with no tolerance) | Refused, because these set a model newly. | Unchanged. **R2:** R1 listed `worker.py:349` here as "newly set"; it is not (row 2). |

**R2: the composer resend, re-traced.** `AgentOutputPanel.tsx:297-310` seeds the pending overrides from `conversation.runtime_overrides`, and `:1058` sends them with every message; `overridesForRunner` strips `model` only for provider runners. Confirmed. Two other paths copy a stored model into a *new* conversation, and so could have counted as "newly chosen": `inherit_runtime_overrides` (`conversations.py:66-111`) and the checkpoint cutover (`checkpoint_cutover.py:182-183`). Both write the copy as the new conversation's stored value without calling `validate_overrides`, so the next composer send matches the stored value and D4's rule tolerates it. An operator-opened conversation starts with no overrides (`agent_trigger.py:1917-1930`). No task, board or clone path stores a model: `runtime_overrides` at `db/models.py:1833` belongs to `Checkpoint`, and no agent-clone route exists.

The tolerance lives in `validate_overrides` as an optional `stored` mapping. When `overrides["model"] == stored.get("model")`, the model check is skipped and the value is kept in `accepted`. Other controls are validated as today. The tolerance is for the model only: the effort values are a closed enum that did not drift.

**What each route returns when what it calls raises.** `validate_overrides` returns a rejection; it does not raise. A conversation whose `runtime_overrides` is NULL, or has no `model`, makes `stored` empty, so nothing is tolerated and behaviour is today's.

Rejected alternatives:

- **Keep the four removed ids in the catalog**, perhaps marked as legacy. They would stay selectable for new runners, and selecting one buys a silent `claude-sonnet-5`.
- **Rewrite stored values to `auto` in a migration.** That changes what an operator chose without telling them. A flag plus a session-start report is honest about both.

### R3: every consumer of the catalog, and what each does with a stored model the refresh removes

Re-derived from the code, not from R2's table. "Removed" means `claude-opus-4.7`, `gemini-3.6-flash`, `gemini-3.5-flash` or `kimi-k2.7-code` is stored, and the catalog is D1's.

| Consumer | After the refresh, with a stored removed model | Covered by this change? |
|---|---|---|
| Agent create (`agents.py:727-732`) | Refuses an undeclared `body.model` with 400. That is a newly chosen model, so this is correct. There is **no agent-update model route**: an agent's model is its runner's. After binding, the agent's Copilot home is written with `model=runner.model` (`agents.py:1938-1952`), and `render_agent_file` (`copilot_home.py:147-157`) writes it into the `model:` frontmatter unless it is `auto`. | Yes (unchanged) |
| Runner update (`runners.py:216`) | Tolerates the stored value (`current=runner.model`) and flags `model_unrecognised`. | Yes (unchanged) |
| Conversation turns, the trigger (`agent_trigger.py:1998-2004`) | Composer sends 400 today; peer and scheduled turns spawn silently (`:1008-1022`). The home is rewritten each turn with that turn's model (`:3530-3557`), so the frontmatter always equals `--model`. | Yes (D4 tolerance, D3 report) |
| Conversation copy (`conversations.py:66-111`) and checkpoint cutover (`checkpoint_cutover.py:182-183`) | Copy the stored model into the successor without validation. The next composer send then matches the stored value, which D4 tolerates. | Yes |
| One-shot workers (`worker.py:344-349`) | Refuse with `unknown_model`. | **No.** wpc3-f, task 2.9 (R2) |
| Titler (`conversation_titles.py:268`) | Uses `job.model or runner.model` and builds its own `-p` command (`runner_adapters/copilot.py:59-78`) with `--model <old>`. It has no gate, so it spawns. **R3:** R2 said Copilot substitutes in `-p` mode. Only ACP `session/new` was probed, so that is UNVERIFIED. If `-p` errors instead, titling fails quietly and the floor title stays, which is visible but harmless. | Partly. Nothing reports what ran; task 3.2 can observe it. |
| **R3: UI model pill** (`ModelPicker.tsx:58-61`, fed by `Composer.tsx:347` as `pendingOverrides.model ?? effectiveModel`) | `resolveCatalogModel` returns null for an undeclared value, so `current` falls back to the default (Auto). `catalogModelLabel(Auto, "claude-opus-4.7")` (`modelCatalog.ts:113-115`) then labels the pill **"claude-opus-4.7 — latest (now Auto)"**. That presents the model as an alias that resolves to Auto, while Copilot runs `claude-sonnet-5`. The same happens for a runner stored on a removed model with no conversation override. | **No, until R3.** Proposal said "the composer's model pill can say so", but task 2.3 said "no rendering change". R3 adds task 2.3a and test 1.12. MEDIUM. |
| **R3: checkpoint-model select** (`ProjectSettingsPanel.tsx:341-359`) | Has no option for a stored undeclared value, so the controlled select shows "Use the runner's model" while `checkpoint_model` holds `claude-opus-4.7`. `RunnersPage` already renders such a value as "— unrecognised" (`:390`). | Folded into task 2.3a. LOW. |
| Drift script (`scripts/check_model_catalog.py`) | Reads the catalog by path. A stored value is not its concern. | Yes (D2, R3) |
| `agentweave doctor` (`src/agentweave/cli.py:130`, `diagnostics.py:866-873`) | Never consults the catalog; it echoes `model` as data. The Hub has no other doctor. `copilot_probe` discards `session/new`'s models (`:414-426`). | Unaffected |
| Context-window fallbacks (`checkpoint_policy.py:301`, `output_recording.py:173`, `model_context_window` / `context_window_for_model` `model_catalog.py:555-601`) | Every Copilot `context_window` is None before and after, so a removed id changes nothing. | Unaffected |

No row on the work-PC trial database stores a removed model (R3 re-read it with `mode=ro`): every runner model and `checkpoint_model` is NULL; `manager_jobs` is empty; the two conversation overrides are `gpt-5-mini` and `claude-sonnet-5.5`, both in D1. The exposure is latent here and real on any account that picked a removed model.

## D5 — Per-model effort (deferred; question wpc3-d)

Copilot's effort options vary by model. VERIFIED:

| Model | Offered efforts |
|---|---|
| `gpt-5-mini` | low, medium, high |
| `gpt-5.5` | none, low, medium, high, xhigh |
| the Claude models probed | low, medium, high, xhigh, max |

The catalog's Effort control is per provider: `ControlSpec`, with values `low…max`. Making it per model changes the catalog's schema and the composer's pill. D3's `copilot.effort_substituted` makes the mismatch visible now. The per-model list belongs with option (c), where Copilot supplies it per session.

## Tests that can fail

Each test below fails on today's code, unless it is marked as a control.

- `tests/test_model_catalog_drift.py`, against the 1.0.94-3 fixture: `parse_copilot_models` returns 30 ids including `claude-haiku-5.5` and `grok-4.7`, and the real catalog agrees with the capture. The agreement check fails today: 6 drifts.
- `hub/tests/test_model_catalog.py`:
  - `validate_overrides("copilot", {"model": "claude-haiku-5.5"})` is accepted.
  - `{"model": "claude-opus-4.7"}` is refused.
  - With `stored={"model": "claude-opus-4.7"}`, the same override is accepted and kept.
  - With `stored={"model": "gpt-5.5"}`, it is refused.
- `scripts/check_model_catalog.py` (**R3:** replaces R2's argv test): the script compares against `which("copilot") help config` as today. It also prints the version of the Hub's binary, from the monkeypatched `resolve_copilot_executable(None)` run with `--no-auto-update --version`. A differing Hub build is printed but leaves the exit code unchanged. The test monkeypatches the resolver and `subprocess.run`.
- A trigger route test: a conversation stored on `claude-opus-4.7`, re-sent with the same override, returns 200 and keeps it. Switching to `bogus-model` returns 400.
- An adapter test fed a `session/new` result with `currentModelId: "claude-sonnet-5"`, for requested `claude-opus-4.7`: exactly one `copilot.model_substituted` is emitted before the prompt, and the usage sample is attributed to `claude-sonnet-5`.
  - Requested `auto`: no diagnostic. This is a control.
  - A response without `models`: no diagnostic and no error. This is a control.
- The same adapter test for effort, with `reasoning_effort.currentValue: "medium"` against a requested `max`.
- **R2:** an adapter test in which `session/new` reports the requested model but the `session/set_config_option` (agent) answer's `model` option reports another: one diagnostic, naming the agent-selection value. This fails today (no check exists) and also fails R1's D3, which read `currentModelId` first.
- **R2:** a worker test: `run_worker` on a non-provider Copilot runner whose stored model is `claude-opus-4.7` (with the spawn stubbed). Today it spawns; after task 2.1 alone it returns `unknown_model`, which is the regression D4 row 2 describes. If wpc3-f keeps the refusal, the test asserts `unknown_model` and fails today; if it tolerates, the test is a regression control asserting a spawn.
- **R2:** the drift script's by-path import of `copilot_probe` succeeds with no Hub package on `sys.path`.
- The fixture order is the order Copilot printed it, and the session-start fixture is shaped exactly like `evidence/r2-probe-claude-opus-4.7.log`: result keys in the order `models`, `configOptions`, `modes`, `sessionId`. Per CLAUDE.md, a payload fixture must use the order the source emits.

**R3 corrections, each re-derived against HEAD `6208e9a5`:**
- **The trigger test cannot fail today as written (MEDIUM).** `claude-opus-4.7` is *declared* today, so resending it returns 200 now, and `bogus-model` returns 400 now. The test passes on today's code and proves nothing about the stored-value tolerance. Fix: store a Copilot id that **neither** the old nor the new catalog declares (for example `copilot-retired-model`, written straight to the row as an old Hub could have). Resending it returns 400 today and 200 after task 2.1. Keep the `claude-opus-4.7` resend as a regression control, which must still return 200 after the refresh.
- **Mislabelled controls (LOW).** Three cases R2 called controls fail today, which is fine, but they are not controls:
  - `stored={"model": "gpt-5.5"}` is refused: `validate_overrides` has no `stored` parameter today, so this is a TypeError. It becomes a control only once the signature exists.
  - The `session/load` mismatch case reports one diagnostic, but no check exists today.
  - The `model_unrecognised` case on runner `claude-opus-4.7`: the flag is false today because the model is still declared.
- **The agent-selection answer's shape is assumed (LOW).** The only captured answer (1.0.88, `evidence/README.md`) is `{"configOptions":[mode, agent, allow_all]}`, with no `model`. An added case: an agent answer with no `model` option falls back to `currentModelId`, and gives one diagnostic. `options = _options_of(selected) or options` replaces the options with that list today, so a check that reads only config options would silently find nothing.
- **R3:** a `ModelPicker` vitest: given `effectiveModel="claude-opus-4.7"` and a catalog that does not declare it, the pill reads `claude-opus-4.7 — unrecognised` and never the `— latest (now Auto)` label. It fails today (D4 R3 table).
- **R3, only if wpc3-f answers (4):** a manager-job PATCH that sets an undeclared model returns 400, as does a non-provider `checkpoint_model` set to one. Both return 200 today. Resaving the same stored value still returns 200.
- The pinning test's count assertion is at `tests/test_model_catalog_drift.py:415`, not `:413`. The test reads the fixture with `encoding="utf-8"`, so the new capture must have its BOM stripped, as R1's own fixture note says.

## Round log

- **R1 (2026-10-12)**: re-derived WPC-3, which holds as stated. Surprises:
  - Both guards it calls for already existed.
  - The CLI the Hub spawns is 1.0.89-1, not 1.0.94-3.
  - `session/new` now carries the account's model list and per-model effort.
  - Removed and unentitled models are substituted silently at session start.
  - The composer's resend of stored overrides would turn a refresh into a 400 per message.
- **R2 (2026-10-12, work PC)**: an independent comparison against HEAD `6208e9a5`, with two no-prompt probes (`evidence/r2-probe-*.log`). No prompt was sent, by instruction, so R1's prompted-turn question stays open (task 3.2).
  - **Confirmed:** both `--version` readings and that the Hub always passes `--no-auto-update` (ACP, probe, and one-shot); the 6 drifts against 1.0.94-3 and the 3 against 1.0.89-1; the 30-id count; the pinning test is green today (30 passed) and fails 6 drifts once task 1.1 swaps the fixture; the composer resend; the session-start fields `models.currentModelId`/`availableModels` and the `model`/`reasoning_effort` options; the silent `claude-sonnet-5` substitution; validation sites on runner create/update, agent create and trigger, and that `validate_overrides` returns rather than raises.
  - **HIGH:** one-shot workers refuse a stored removed model (`worker.py:348-349`); R1 called those "newly set". The refresh would stop checkpoints, handovers, distillation and vault work on any runner, project or job stored on a removed id. D4 row added; question wpc3-f.
  - **MEDIUM:** D3 read the `session/new` answer, but the adapter then selects an agent whose file carries `model`/`reasoningEffort`; the check moves after agent selection and reads the config option first.
  - **MEDIUM:** the existing requirement "The Hub validates overrides before spawning" claims silent fallback cannot occur; for Copilot it can, before and after this change. Question wpc3-g.
  - **LOW:** D2's post-refresh drift count is 9, not 3; the session-start key order is `models, configOptions, modes, sessionId`; `resolve_copilot_executable` is in `copilot_probe`; a second stale comment at `model_catalog.py:352-357`; R1's effort fact lacked a control (added); `r1_model_probe.py`'s docstring says 1.0.94-3 but it spawns 1.0.89-1.
  - The pinning test goes stale again on the next CLI release by construction. That is option (a)'s stated limit, not a defect of the test; D2's corrected script is the only thing that notices, and it is manual.
  - Files changed in R2: this design, `tasks.md`, `proposal.md` (header, D3/D4 cross-references swapped back, worker impact, agent-selection timing), `test-guide.md`, `evidence/README.md` and `evidence/r2_*`. In the delta spec, the ADDED requirement now says the comparison happens after agent selection, with a new scenario for it. The MODIFIED block was checked against `openspec/specs/model-catalog/spec.md` and is whole.
- **R3 (2026-10-12, work PC)**: an independent comparison against HEAD `6208e9a5`. No prompt was sent; only `--version` and `help config` were run, and the trial database was read with `mode=ro`.
  - **Confirmed:**
    - The 32-id catalog and its stale 1.0.90 and 1.0.88 comments.
    - The 6 drifts against 1.0.94-3 and the 9 between D1 and 1.0.89-1.
    - The 21 live models on this account, all in D1.
    - The session-start key order.
    - D3's ordering, and that `_model` returns early once `resolved_model` is set (`copilot_acp.py:1573`), so a mid-turn event cannot double-report.
    - The composer resend.
    - The worker refusal (`worker.py:348-349`).
    - `validate_overrides` returns rather than raises.
    - The wpc3-g citation.
  - **MEDIUM:**
    - D2 compared against the Hub binary's help. That is inconsistent with D1 and with the delta spec, which both track the newest release, and 2 of its 9 day-one drifts are false: `claude-haiku-5.5` and `claude-sonnet-5.5` run on 1.0.89-1. D2 is rewritten to compare against the newest help and to print the Hub build as information. wpc3-c changed.
  - **MEDIUM:**
    - The trigger test (task 1.4) passes on today's code, because `claude-opus-4.7` is still declared. It now uses an id neither catalog declares.
  - **MEDIUM:**
    - The composer pill labels an undeclared stored model "`<id>` — latest (now Auto)" (`ModelPicker.tsx:58-61`, `modelCatalog.ts:113-115`).
    - The proposal promised the pill would flag it, while task 2.3 said "no rendering change". Task 2.3a and test 1.12 are added, and the delta spec gains a scenario.
  - **MEDIUM:**
    - R2's "stdlib-only imports" is not enough for the by-path import of `copilot_probe`; it also needs `sys.modules` registration before `exec_module` (measured).
  - **LOW:**
    - Three mislabelled controls.
    - The agent-selection answer's shape is uncaptured on 1.0.89-1 (a new no-`model` case).
    - The titler's `-p` substitution is unverified.
    - The checkpoint-model select shows "Use the runner's model" for an undeclared value.
    - `auto` belongs out of the diagnostic's offered list.
    - A runner's pinned `cli` names a binary the drift script does not read.
    - The count assertion is at `:415`.
    - The delta spec's first sentence said "installed" where its body says "newest".
  - **On wpc3-f:**
    - R2 said the worker docstring (`worker.py:164-173`) argues for the gate. It argues for *agreement with the runner registry*, which tolerates a stored value, so after the refresh the gate disagrees with the registry.
    - Manager-job models are never validated on write (`api/v1/manager.py` PATCH checks only `runner_id`).
    - R3 adds option (4), "validate on write, tolerate at run", and recommends it.
  - **On wpc3-g:** R3 recommends (1).
  - Full consumer table in D4 (R3).
  - **Files changed in R3:** this design, `tasks.md`, `proposal.md`, the delta spec, `test-guide.md` and `evidence/README.md`. There are no new evidence files.

## Open questions for the operator

- **wpc3-a — Which option keeps the list right?**
  - Options:
    - (a) refresh plus the pinned test (exists).
    - (b) also fix and keep the manual drift script.
    - (c) read `availableModels` at probe time and validate against the account's list.
  - Recommended: **(a), plus the corrected (b), plus D3's session-start report**, now. Treat the probe-time half of (c) as wpc3-e.
  - Reason: this closes the 400 and the silence with no new contract. Validating against a per-account list changes what the catalog *means*, and that deserves its own change.
- **wpc3-b — Should a stored model that has left the catalog keep working, with a warning?**
  - Options:
    - (1) yes: tolerate the unchanged stored value, flag it, and report substitution (D4).
    - (2) refuse it: today's composer 400s.
    - (3) migrate it to `auto`.
  - Recommended: **(1)**.
  - Reason: it is what runners already do, it never rewrites an operator's choice, and D3 tells them what actually ran.
- **wpc3-c — Which CLI build does the list track?** *(changed in R2; changed in R3)*
  - Options:
    - (1) the newest `copilot help config` (1.0.94-3), as D1 proposes.
    - (2) the build the Hub spawns (`--no-auto-update`, 1.0.89-1 here).
    - (3) the union of the two.
  - Recommended: **(1)**, with the drift script comparing against the same newest list (D2, R3).
  - Reason: the model list belongs to the service, not the build. Every model 1.0.89-1 offers live on this account is in D1. That binary runs `claude-haiku-5.5` and `claude-sonnet-5.5`, which its own help omits, and it does not offer `claude-opus-4.7`, which its help lists.
  - On the parent's sub-question: `claude-opus-4.8-fast` and `gpt-6-*` need no action, because they are already present. The real additions are `claude-haiku-5.5` and `grok-4.7`.
  - R2 had the script compare against the Hub's binary, so with (1) it reported nine drifts on the day the refresh landed.
  - **R3:** that comparison contradicts (1) itself; it is not a cost of (1). So D2 now compares against the newest help (0 drifts that day) and prints the Hub's build as information.
  - Choosing (2) would refuse `claude-haiku-5.5`, the model WPC-3 is about, although the Hub's binary runs it.
- **wpc3-d — Per-model effort?**
  - Options:
    - (1) report the substitution only (D3/D5).
    - (2) a hand-maintained per-model effort table in the catalog.
    - (3) read the effort options from Copilot per session, with (c).
  - Recommended: **(1) now, (3) later**.
  - Reason: a hand table drifts exactly as this list did.
- **wpc3-e — Should the probe record the account's `availableModels` (request R11)?**
  - Options:
    - (1) yes, in a follow-up change: the catalog route shows which declared models this account can run, and the picker marks the others.
    - (2) yes, and also refuse unentitled models.
    - (3) no.
  - Recommended: **(1) as the next change**.
  - Reason: the data is already fetched and discarded (`copilot_probe.py:414`), but whether the catalog may vary by account is a product decision.
- **wpc3-f — What happens to a one-shot worker whose stored model left the catalog?** *(new in R2; changed in R3)*
  - Options:
    - (1) `model_is_declared` tolerates it for workers, as turns already do, and D3's report (or the one-shot envelope's model) says what ran.
    - (2) keep the refusal, so checkpoints, handovers, distillation and vault work stop with `unknown_model` until the operator re-picks; say so in the release notes and surface it on the runner.
    - (3) refuse, but fall back to the runner's CLI default (`model=None`) with a diagnostic.
    - (4) *(R3)* **validate on write, tolerate at run.**
      - The worker stops gating declared-ness for non-provider runners. Because every worker model is stored, "tolerate at run" is all it can mean.
      - The two write paths that accept a worker model without a catalog check gain one, with the runner registry's `current` tolerance:
        - the manager-job PATCH (`api/v1/manager.py:37-61`, which today checks only `runner_id`), judged against the job's runner, or the project's default runner when it has none;
        - a non-provider `checkpoint_model` (`projects.py:586-603`, which today checks only provider runners).
  - **R3 recommendation: (4).**
  - R2 declined to recommend, partly because "(1) removes a gate whose docstring argues for it". **R3 reads the docstring the other way.** `worker.py:164-173` justifies the gate by agreement with the runner registry: "a worker that … refused one it accepts … would be two gates disagreeing on one value". The registry accepts an unchanged stored value (`runners.py:216`, `current=runner.model`). So after the refresh, the worker gate refuses what the registry accepts, which is exactly the disagreement the docstring forbids.
  - (4) keeps the docstring's other purpose, catching a mistyped model before a slow, billable spawn, at the point where the mistype is made rather than on every run.
  - Today (1) alone would leave a manager-job model unvalidated end to end. (4) closes that.
  - **Caveat:** what a `-p` one-shot runs on a substituted model is unreported. D3 covers ACP sessions only, and `-p` substitution itself is unverified (task 3.2).
  - Context: the worker cannot distinguish stored from new, because every worker model is stored.
- **wpc3-g — Does the "Silent provider fallback cannot occur" scenario still hold for Copilot?** *(new in R2)*
  - Options:
    - (1) MODIFY "The Hub validates overrides before spawning" in this change, so that for a provider that substitutes silently (Copilot), the Hub reports the substitution at session start instead of guaranteeing it cannot happen.
    - (2) leave the requirement and accept the contradiction until per-model effort and per-account models (wpc3-d, wpc3-e) can make it true.
    - (3) make it true now: refuse an effort the requested model does not offer, which needs per-model effort (wpc3-d option 2 or 3).
  - No recommendation from R2. The contradiction predates this change (`grok-*` is declared and unentitled today), but this change is the first to write the fallback into the spec as expected behaviour.
  - **R3:** the question is well-posed, and the citation is exact: the requirement is at `openspec/specs/model-catalog/spec.md:93-117`, and its scenario "Silent provider fallback cannot occur" is at `:114-117`.
  - **R3 recommends (1).** Otherwise, once this change is synced, one spec file carries two requirements that contradict each other: "cannot occur" and "is reported when it occurs". `openspec validate --strict` cannot catch that.
  - (3) needs per-model effort and per-account models, both deferred (wpc3-d, wpc3-e).
  - The MODIFIED block is written only after the operator answers. Task 0.3 gates it.
