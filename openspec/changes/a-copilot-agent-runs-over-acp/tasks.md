## 0. Rounds

- [ ] 0.1 R2: an independent re-derivation against the code as it stands after tonight's queue and slice 1. Re-read, fresh:
  - `codex_appserver.py`;
  - `agent_trigger.py` (the trigger body, `_execute_run`'s dispatch, the RPC executor, the stop paths);
  - `runner_commands.py`, `launchability.py`, `model_catalog.py`;
  - `mcp_server._decide` and its callers;
  - `workspace_writes.py`, `worker.py`, `conversation_titles.py`;
  - `agents.py` (`_render_hub_agent_context`, create, PATCH).

  Re-derive D1–D19 from those files, not from this design. Re-check every row of design § "Sites touched by open changes" against what landed, including slice 1's adapter member names, and correct the design where they differ. Answer Open questions 2, 4 and 9 from `app.js` or the command reference. Record the round in `design.md`'s Round log. `openspec validate a-copilot-agent-runs-over-acp --strict` passes
- [ ] 0.2 R3: a second independent re-derivation, not a re-read of R2. Ask of each route in design § "What each route returns when what it calls raises" what it actually returns when the Copilot function it calls raises, by reading the route. Re-derive the D8 table from `app.js`'s `XDo`/`nNo` and `mcp_server._decide`. Record the round in the Round log
- [ ] 0.3 Opus adversarial review of the change and of the decisions it assumes (the operator's standing step before APPROVED). It MUST address:
  - D5: the context split, and whether the tool surface belongs in `per_turn`;
  - D8: whether the `acceptEdits` emulation, fetch-allowed parity and the refusal to emulate full access under policy are right;
  - D9: plan mode on specification turns;
  - D15: whether a pending launchability verdict should be permissive.

  Record the result in the Round log and in `spec-queue/tracks/reviews/`

## 1. Captures, then tests first — each test fails on today's code

Copilot Free plan: **two** model-calling prompts in this group, and no more. Every other probe is a slash command or a handshake. Run captures with `openspec/changes/a-copilot-agent-runs-over-acp/evidence/r1_probe.py` as the starting point. Always use a scratch `COPILOT_HOME` under `%TEMP%`, and point the MCP server's `HUB_URL` at a dead port, never `:8000`.

- [ ] 1.1 **Capture 1 (1 prompt, ACP).** Set up a scratch workspace holding a custom agent file whose body carries the marker `AW-MARKER-5521`, and the Hub's real `mcp_server.py` from `--additional-mcp-config`. Subscribe to design D10's raw events plus `tool.execution_start`. Answer every `session/request_permission` with `allow_once`, **recording its params**. Send one prompt: *"Quote the marker in your agent instructions. Then create file probe.txt containing hi, then run the shell command `echo done`, then call agentweave-list_tasks."*

  Save the transcript, in wire order, to `hub/tests/fixtures/copilot_acp/turn_write_shell_mcp.jsonl`. Paths must be replaced by `<WS>`/`<HOME>`, and it must hold no token. Record in the Round log:
  - whether the marker came back (Open question 1);
  - the three `request_permission` shapes (edit, execute, mcp) against design D8;
  - the `session.error|warning|info` field names, if any appeared (Open question 10).
- [ ] 1.2 **Capture 2 (1 prompt, `-p`).** Run `copilot.exe -p "Reply with the word ok" --output-format json --no-auto-update --disable-builtin-mcps --no-custom-instructions --no-ask-user --available-tools= --allow-all-tools` under a scratch home. Save stdout to `hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl`. Record which event carries the answer and whether any tool was offered. If `--available-tools=` did not remove tools, record that; design D14's fallback applies. Also save `evidence/help-config.txt` (the output of `copilot help config`, no model call) for task 2.4
- [ ] 1.3 `hub/tests/test_runners_api.py`: `POST /runners` with `cli: "copilot"` returns 201, and the row reads back. Today it fails with 422, the validator's refusal. Add a model-level test that inserts a `Runner(cli="copilot")` and commits; it fails today on `ck_runners_cli`
  - Verify: `py -3.11 -m pytest hub/tests/test_runners_api.py -q -k copilot`
- [ ] 1.4 `hub/tests/test_runner_charter_models.py` (or the seeding test beside `db/engine.py`'s seeder): a zero-runner project is seeded with `claude`, `codex` and `copilot`. A project holding one runner gets nothing. Cover both seeders, `engine.py:_seed_default_runners` and `project_lifecycle._seed_new_project`
- [ ] 1.5 `hub/tests/test_copilot_probe.py` (new): `resolve_copilot_executable` on a fake tree in `tmp_path`. Cover:
  - an npm `copilot.cmd` JS shim plus `node_modules/@github/copilot/node_modules/@github/copilot-win32-x64/copilot.exe` resolves to the `.exe`;
  - a shim with no platform package raises, with the looked-for path in the message;
  - a native executable on `PATH` is used as-is;
  - a pinned override that is a `.cmd` is refused.

  Patch `shutil.which` and the platform. The test fails today because the module does not exist
- [ ] 1.6 `hub/tests/test_copilot_acp_decide.py` (new): `decide_permission` over every row of design D8's table, for all four postures. Use the `request_permission` params captured in 1.1 for edit, execute and mcp, and CODE-shaped params for read, fetch, memory and an unknown kind. It must include:
  - a PowerShell command writing `..\..\x` refused under `workspace`;
  - `agentweave` MCP allowed under `manual`;
  - a foreign MCP server judged;
  - `memory` refused;
  - the answer never being `allow_always`
- [ ] 1.7 `hub/tests/test_permission_approver.py`: `_decide(..., workspace=W, hub_url=U)` judges against `W` and `U` when `os.environ` names other values. It fails today because the keywords do not exist
- [ ] 1.8 `hub/tests/test_copilot_acp_mapper.py` (new): replay `evidence/acp4-turn-mcp-shell-1.0.88.log` and the 1.1 fixture, **in their recorded order**, through `CopilotEventMapper`. Assert:
  - one `text` event per contiguous message block;
  - `tool_use` then `tool_result` with the same call id for the shell and the MCP call;
  - a streamed partial shell output emits nothing until the terminal update;
  - the edit's `tool_use` carries the file path and diff;
  - a replayed `user_message_chunk` before arming emits nothing;
  - a synthetic message `"Warning: X"` with a matching raw `session.warning` becomes `diagnostic`, and without one stays `text`;
  - an `agentweave` server status `failed` emits one error;
  - `session.model_change` to a different model emits one diagnostic.

  Reversing the order of a `tool_call` and its `tool_call_update` must make the correlation assertion fail (the CLAUDE.md ordering rule)
- [ ] 1.9 `hub/tests/test_copilot_acp_run_turn.py` (new): a scripted fake session in the style of `test_codex_appserver_run_turn.py`, whose `session/prompt` response is delivered **after** that turn's notifications, as Copilot does. Assert:
  - (a) new: `initialize` subscribes the D10 events, then `session/new` with `mcpServers: []`, then `set_config_option agent`, then the prompt with the per-turn block first;
  - (b) load: `session/load` is used, and replayed chunks before the prompt produce no event;
  - (c) load `-32002`: `session/new` follows and `on_session_missing` fires;
  - (d) version `1.0.75`: fails before any `session/*` request;
  - (e) full access with no `allow_all` option: a diagnostic, and requests are judged as `workspace`;
  - (f) an `agent` option whose description is not the marker: the stable context goes as a `resource` block, with a diagnostic;
  - (g) stop: `session/cancel` is sent, and `stopReason: cancelled` → `interrupted`;
  - (h) every `session/request_permission` is answered exactly once;
  - (i) `usage_update` → `on_usage` with a measured sample and the resolved model;
  - (j) a spec turn: `set_mode` with the full plan URI before the prompt
- [ ] 1.10 `hub/tests/test_copilot_home.py` (new): `ensure_copilot_home` writes `agents/<agent>.agent.md` with frontmatter `name`, `description` (the marker), `tools`, `model` (omitted for `auto`) and `reasoningEffort`, and a body that opens with the precedence statement and holds the stable context. It also writes `agentweave-mcp.json` with no `env` and `timeout == (agents.MAX_WAITING_SECONDS + 60) * 1000`. A second call with the same content does not rewrite the file (mtime unchanged). No file contains an `aw_run_` string
- [ ] 1.11 `hub/tests/test_copilot_context_split.py` (new):
  - `_render_hub_agent_context`'s `stable` and `per_turn` together hold every `##`/`###` section of `context` exactly once;
  - the charter and project instructions are in `stable`;
  - the tool surface and workspace are in `per_turn`;
  - `context` for a Claude run equals a snapshot taken before the change (write the snapshot as the first step of this task, from today's code)
- [ ] 1.12 `hub/tests/test_model_catalog.py`: `get_provider("copilot")` exists, its default model is `auto` labelled "Auto", every model's `context_window is None`, its Permissions values and labels equal Codex's, and `validate_overrides("copilot", {"model": "bogus-model"})` is refused
- [ ] 1.13 `hub/tests/test_workspace_writes.py`: `written_paths("edit", {"locations": [{"path": "C:/elsewhere/x.py"}], …})` returns that path, and `delete`/`move` likewise. `"shell"` returns `()`. `OutsideWriteRecorder` records a Copilot edit outside the workspace
- [ ] 1.14 `hub/tests/test_worker.py` and `test_conversation_titles.py`:
  - `build_worker_command(cli="copilot", …)` returns design D14's argv (the resolved `.exe`, not the npm shim, with `--no-custom-instructions`);
  - `build_title_command` returns it without `--no-custom-instructions`;
  - `parse_copilot_envelope` on the 1.2 fixture returns `"ok"`;
  - `copilot` is in both supported sets
- [ ] 1.15 `hub/tests/test_launchability.py`:
  - with `GH_TOKEN` unset and a cached probe verdict "signed in, 1.0.88", `probe_agent` for `copilot` is runnable (today it says "No GitHub auth token found");
  - "not signed in" → not authorized, with the `copilot login` sentence;
  - "1.0.75" → not authorized, with the version sentence;
  - pending → runnable with `verdict_pending: True`
- [ ] 1.16 `hub/tests/test_runner_command_env.py`: `resolve_agent_env("copilot", {})` with `GH_TOKEN`/`GITHUB_TOKEN`/`COPILOT_GITHUB_TOKEN` in `os.environ` returns an environment without them. With `env_vars: {"COPILOT_GITHUB_TOKEN": "COPILOT_GITHUB_TOKEN"}` that variable is kept. Claude's environment is unchanged
- [ ] 1.17 `hub/tests/test_mcp_server_stdio_surface.py`: spawn `mcp_server.py` as the Hub does, with `HUB_URL` on a dead port. Send `{"jsonrpc":"2.0","id":0,"method":"server/discover","params":{}}` **before** `initialize`. Assert a JSON-RPC error response with id 0 (not a crash, not silence). Then `initialize` with `protocolVersion "2025-11-25"` succeeds and `tools/list` lists `send_message`.

  This test documents behaviour R1 measured (design § VERIFIED). It passes today and is a guard, which it says in its docstring
- [ ] 1.18 `hub/tests/test_tool_surface_matches_server.py`: a Copilot run in the MCP form names every tool `agentweave-<tool>`, and the access notice does too. **Depends on** `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` having landed. If it has not, leave this unchecked and say so
- [ ] 1.19 UI tests:
  - `hub/ui/src/__tests__/` asserts `providerForRunner('copilot') === 'copilot'`;
  - `ProviderMark` renders an SVG, not initials, for `copilot`;
  - the Runners page's CLI select offers `copilot`.

  Extend `modelCatalogFixture.ts` with the Copilot provider. Verify: `cd hub/ui && npx vitest run`

## 2. Registry, migration, seeding, catalog

- [ ] 2.1 `db/models.py`: `RUNNER_CLIS = ("claude", "codex", "copilot")`, and the `ck_runners_cli` constraint is written from `RUNNER_CLIS`, so the two cannot drift
- [ ] 2.2 A new migration, the next free revision after tonight's queue, recreates `runners` with the widened constraint (`batch_alter_table(recreate="always")`) and guards a missing table. Downgrade refuses when a `copilot` row exists. Bump `HEAD_REVISION` in `hub/tests/test_migrations.py` and the head in `hub/tests/test_project_persistence.py` (`.claude/rules/db-migrations.md`)
  - Verify: `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py hub/tests/test_runners_api.py -q`
- [ ] 2.3 Confirm both seeders produce `Copilot (default)`. Task 1.4 passes
- [ ] 2.4 `model_catalog.py`: add `CATALOG["copilot"]` per design D13, taking the model tuple from `evidence/help-config.txt`. Add `"copilot": "copilot"` to `_CATALOG_PROVIDER_BY_RUNNER` (or slice 1's `catalog_provider`). Add a test that is skipped when `copilot.exe` is absent and otherwise compares the tuple with a live `copilot help config`. Tasks 1.12 and 1.3 pass
  - Verify: `py -3.11 -m pytest hub/tests/test_model_catalog.py hub/tests/test_model_catalog_api.py -q`

## 3. Executable, probe, launchability

- [ ] 3.1 `hub/hub/copilot_probe.py`: `resolve_copilot_executable` (design D2). Task 1.5 passes
- [ ] 3.2 `CopilotProbe`: a cached, TTL'd, async refresh using `initialize` → `session/new` → `session/close` under the `_worker` home, with no model call (design D15). Refresh is scheduled from `GET /runners/launchability-by-provider` and the agent launchability route. Test its refresh against a fake process
- [ ] 3.3 `launchability.py`: delete the env-token branch (`:116-126`), make `probe_agent` read the Copilot verdict, and extend `resolve_agent_env` with the GitHub-token strip (design D3). Tasks 1.15 and 1.16 pass
  - Verify: `py -3.11 -m pytest hub/tests/test_launchability.py hub/tests/test_runner_command_env.py hub/tests/test_copilot_probe.py -q`

## 4. The Hub-owned Copilot home and the context split

- [ ] 4.1 `_render_hub_agent_context` returns `stable` and `per_turn` beside the unchanged `context` (design D5). Task 1.11 passes
- [ ] 4.2 `hub/hub/copilot_home.py`: `copilot_home_path` and `ensure_copilot_home` (design D4). Task 1.10 passes
- [ ] 4.3 Call `ensure_copilot_home` after `create_operator_agent` commits and after `PATCH /agents/{name}` commits, for a Copilot-bound agent; an `OSError` is logged and does not fail the route. Also after `POST /agents/request` if that path creates Copilot agents. Add a route test: creating a Copilot agent produces the agent file, and a failing write (patched) still returns 201
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_home.py hub/tests/test_copilot_context_split.py -q`

## 5. Approvals

- [ ] 5.1 `mcp_server.py`: add keyword-only `workspace`/`hub_url` to `_decide`, `_is_own_hub` and `_judge_word`, defaulting to the environment. Add no import (`.claude/rules/mcp-server.md`). Task 1.7 passes, and `test_permission_approver.py` and `test_mcp_server.py` are otherwise unchanged
- [ ] 5.2 `copilot_acp.decide_permission` (design D8), with the per-kind operator-card labels beside `_CODEX_APPROVAL_LABELS`. Task 1.6 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_acp_decide.py hub/tests/test_permission_approver.py hub/tests/test_mcp_server.py -q`

## 6. The ACP transport

- [ ] 6.1 `runner_events.diagnostic_event(code, message)` in the closed set. `copilot_acp.CopilotEventMapper` (design D10). Task 1.8 passes
- [ ] 6.2 `copilot_acp.ACPProcess`: stdio JSON-RPC as `AppServerProcess`, UTF-8, stderr drained, and a pending-request map. It additionally supports a request whose response is awaited while notifications are drained, and handles agent→client requests. `close()` ends the process tree with `terminate_process_tree`. Test it against a stand-in script, as `test_codex_appserver_process.py` does
- [ ] 6.3 `copilot_acp.build_acp_argv` and `run_turn` (design D3, D6, D7, D9, D11, D12, D17). Task 1.9 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_acp_mapper.py hub/tests/test_copilot_acp_run_turn.py -q`

## 7. Wiring into the trigger

- [ ] 7.1 If slice 1 did not already make `_execute_codex_appserver_run` a runner-parameterised RPC executor, do that first: replace the four `runner="codex"` literals (`agent_trigger.py:3089`, `:3261`, `:3350`, `:3445`) with the adapter's name, and `codex_run_turn` with the adapter's `run_turn`. Run the whole Codex app-server suite unchanged
  - Verify: `py -3.11 -m pytest hub/tests/test_codex_appserver_run_turn.py hub/tests/test_codex_appserver.py -q`
- [ ] 7.2 In `trigger_agent_directly`, a `copilot` runner:
  - resolves the executable (a `TriggerAgentError(409)` with the probe's sentence when absent);
  - ensures its home with this turn's model and effort;
  - sets `COPILOT_HOME` in the environment;
  - sends the per-turn block and the prompt;
  - reaches the RPC executor with the Copilot adapter.

  `on_session_missing` rebinds under design D7's exception. Add `_bind_session_id(replace_missing=True)`. Add a trigger-level test with the adapter's `run_turn` patched, asserting `Run.session_id` and `Conversation.provider_session_id` after a rebind
- [ ] 7.3 Route an operator card for `ASK_OPERATOR` through `_await_operator_permission` with Copilot's labels. Route refusals through `_on_refusal`, and allows through tonight's recorder from `a-run-records-that-its-calls-were-allowed` (re-verify its name in R2)
  - Verify: `py -3.11 -m pytest hub/tests -q -k "copilot or appserver or trigger"`

## 8. Outside writes, one-shot calls, tool names, display

- [ ] 8.1 `workspace_writes.py`: `COPILOT_WRITE_TOOLS = {"edit", "delete", "move"}` reading `locations[].path`, added to `WRITE_TOOLS`. Task 1.13 passes
- [ ] 8.2 `worker.py`: add the `copilot` branch, `parse_copilot_envelope` and the `_worker` home environment. `conversation_titles.py` gets its `copilot` branch (design D14). Task 1.14 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_worker.py hub/tests/test_conversation_titles.py hub/tests/test_title_generation.py -q`
- [ ] 8.3 The tool surface uses the `agentweave-` prefix and Copilot preamble for Copilot runs (design D16), through the mechanism of `a-claude-run-is-told-its-agentweave-tools-by-their-full-names`. Task 1.18 passes
- [ ] 8.4 `api/v1/agents.py` `_display_model` gains `"copilot": agent_meta.get("model", "GitHub Copilot")`
- [ ] 8.5 CI parity: `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`, `py -3.11 -m pytest hub/tests/ -q`. With `claude` stripped from `PATH`, re-run the Copilot tests to confirm they do not depend on a local CLI (memory: the local suite is green because `claude` is on `PATH`)

## 9. UI

- [ ] 9.1 `RunnerCli`, `CLI_OPTIONS`, `providerForRunner`, and `PROVIDER_MARKS.copilot` from `siGithubcopilot` in `currentColor` (design D19). Task 1.19 passes
- [ ] 9.2 `cd hub/ui && npm run lint && npx vitest run && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`. Commit `hub/ui/src` and `hub/hub/static/ui` together (`.claude/rules/hub-ui.md`)

## 10. Findings and docs

- [ ] 10.1 Record in `spec-queue/` FINDINGS the three appendix corrections from the Round log (`--no-auto-update` version, `~/.agents/skills`, the MCP 30 s timeout), so later slices do not inherit them

## 11. Drive on the trial Hub `:8010`

Start it **from `hub/`, from source**, never through `agentweave --port 8010`, and never touch `:8000`:
`cd hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/trial/agentweave.db" py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1`.
Confirm the database it serves before trusting it (`.claude/reference/hubs.md`).

Copilot **Free plan**, Auto only: this group spends **at most four** model prompts. Keep every prompt tiny, and record each prompt's cost in the drive notes.

- [ ] 11.1 No model call. Check the following:
  - the Runners page offers `copilot`;
  - create a Copilot runner, then a Copilot agent `cop-1` on it with a short charter;
  - `~/.agentweave/hub/copilot-home/proj-d85a82bf4216/cop-1/agents/cop-1.agent.md` exists and holds the charter and the precedence statement, and the repository has no new file;
  - launchability for `copilot` reads runnable and names no token.
- [ ] 11.2 **Prompt 1.** Under Workspace only, send `cop-1`: *"Create hello.txt containing hi in your workspace, then send me a one-line message with agentweave-send_message."* Record the timeline verbatim:
  - one text block per message;
  - the edit's tool row with its path;
  - the message arriving in the operator inbox;
  - a context reading with a limit;
  - the Auto-substitution diagnostic, if any;
  - no replayed history.

  Then confirm `Conversation.provider_session_id` is set.
- [ ] 11.3 **Prompt 2.** A specification turn: open an empty spec document and ask `cop-1` one question about it. Check two things: it interviews rather than writing a plan file, and it has no write tool. If plan mode prevents the interview, set `SPEC_TURN_USES_PLAN_MODE = False`, file a finding, and re-run with prompt 3.
- [ ] 11.4 **Prompt 3.** Under Ask me, in the same conversation (a resume), ask for `echo hi` in the shell. An operator card opens. Deny it: the timeline shows the refusal, the run completes, and the first turn's output is not rendered again.
- [ ] 11.5 **Prompt 4 (only if unused).** Stop a running turn with the stop button during a long request. The run ends `stopped`, and no `copilot.exe` or `powershell.exe` child of it survives: check with `Get-Process`.
- [ ] 11.6 Write the drive notes into `design.md`'s Round log (prompts spent, what matched, what did not). File every mismatch as a finding. Measure Open question 5 from the context readings of 11.2 and 11.4.

## 12. Archive

- [ ] 12.1 All tasks above checked, or explicitly deferred with a finding. `openspec validate a-copilot-agent-runs-over-acp --strict` passes. Sync the deltas into `openspec/specs/` (`openspec-sync-specs`) and archive (`openspec-archive-change`). Write the handoff per the handoff-cadence rule
