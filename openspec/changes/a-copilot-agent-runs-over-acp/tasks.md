## 0. Rounds

- [x] 0.1 R2: an independent re-derivation against the code as it stands after tonight's queue and slice 1. Re-read, fresh:
  - `codex_appserver.py`;
  - `agent_trigger.py` (the trigger body, `_execute_run`'s dispatch, the RPC executor, the stop paths);
  - `runner_commands.py`, `launchability.py`, `model_catalog.py`;
  - `mcp_server._decide` and its callers;
  - `workspace_writes.py`, `worker.py`, `conversation_titles.py`;
  - `agents.py` (`_render_hub_agent_context`, create, PATCH).

  Re-derive D1–D19 from those files, not from this design. Re-check every row of design § "Sites touched by open changes" against what landed, including slice 1's adapter member names, and correct the design where they differ. Answer Open questions 2, 4 and 9 from `app.js` or the command reference. Record the round in `design.md`'s Round log. `openspec validate a-copilot-agent-runs-over-acp --strict` passes
  - **Done 2026-09-28** against master `ef55e6f` (3 of the queue's sites landed; the rest and slice 1 unbuilt, marked "rebase at IMPL"): 16 corrections, incl. three gates that would 501 or never inject MCP, an empty `--available-tools=` that grants every tool, and JSON-titled conversations; Open questions 2, 4, 9, 10 answered. See the Round log
- [x] 0.2 R3: a second independent re-derivation, not a re-read of R2. Ask of each route in design § "What each route returns when what it calls raises" what it actually returns when the Copilot function it calls raises, by reading the route. Re-derive the D8 table from `app.js`'s `XDo`/`nNo` and `mcp_server._decide`. Record the round in the Round log
  - **Done 2026-09-28** against master `fc33ff9` (code identical to `ef55e6f`). There are five changes:
    - R2's MCP identification by `tool_call` title is replaced, because the title is the model-written `description` argument (`VDo`). The source is now `tool.execution_start`, and an unidentified call is refused;
    - the trigger route answers 200 queued, not 409, so three refusals gain `agent_wide`;
    - `run_turn` returns rather than raises after the prompt;
    - MCP calls are labelled by server, not by `YDo`'s guessed kind;
    - `diagnostic_event` gets the spec's `stream`/`severity`.

    The contract with slices 3–5 is written down. Open questions 3, 6 and 7 are answered and 8 in part; 1 and 5 are carried. See the Round log
- [x] 0.3 Opus adversarial review of the change and of the decisions it assumes (the operator's standing step before APPROVED). It MUST address:
  - D5: the context split, and whether the tool surface belongs in `per_turn`;
  - D8: whether the `acceptEdits` emulation, fetch-allowed parity and the refusal to emulate full access under policy are right;
  - D9: plan mode on specification turns;
  - D15: whether a pending launchability verdict should be permissive.

  Record the result in the Round log and in `spec-queue/tracks/reviews/`
  - **Done 2026-09-28:** Opus review ghcp-s2-2026-09-28: REVISE → 11 fixes applied (findings 1–11, all verified against `app.js`/the capture; none disputed), 6 notes answered (12–17, all applied), plus 4 cross-slice items (subagent `session.error`, both contract conflicts closed as decided, `COPILOT_ALLOW_ALL` owned here). See the Round log, "Review fixes, 2026-09-28"

## 1. Captures, then tests first — each test fails on today's code

Copilot Free plan: **two** model-calling prompts in this group, and no more. Every other probe is a slash command or a handshake. Run captures with `openspec/changes/a-copilot-agent-runs-over-acp/evidence/r1_probe.py` as the starting point. Always use a scratch `COPILOT_HOME` under `%TEMP%`, and point the MCP server's `HUB_URL` at a dead port, never `:8000`.

- [x] 1.1 **Capture 1 (1 prompt, ACP).** Set up a scratch workspace holding a custom agent file whose body carries the marker `AW-MARKER-5521`, and the Hub's real `mcp_server.py` from `--additional-mcp-config`. Subscribe to design D10's raw events (`COPILOT_RAW_EVENTS`, which since R3 includes `tool.execution_start`). Answer every `session/request_permission` with `allow_once`, **recording its params**. Send one prompt: *"Quote the marker in your agent instructions. Then create file probe.txt containing hi. Then run each of these shell commands separately: `Set-Content probe2.txt hi`, then `Get-ChildItem`, then `curl.exe -s http://127.0.0.1:<DEAD>/`. Then fetch `http://127.0.0.1:<DEAD>/` with your web fetch tool. Then call agentweave-list_tasks."* `<DEAD>` is the dead Hub port. (Review 2026-09-28, findings 1 and 2: R3's `echo done` is the class Copilot auto-approves, so it would have captured **no** `execute` request and 1.6 would have had no execute fixture. `Set-Content` writes, so Copilot must ask.)
  - **Done 2026-09-29** (`evidence/t1_1_capture.py`, dead port 9, build 1.0.88): fixture saved,
    386 wire messages, redacted, no token. Headline corrections: the marker did **not** come back
    (policy refusal, not proof of an empty body); no `kind:"edit"` request occurred at all (both
    writes went through `Set-Content` shell calls); `Get-ChildItem` **did** raise a permission
    request three times (`readOnly:false`), disproving the "auto-approved read-only class" premise
    this task and task 10.1 both stated; `curl.exe` raised only `kind:"shell"`, never finding 2's
    anticipated `kind:"url"`; `session.mcp_servers_loaded`'s `agentweave` entry carries neither
    `source` nor `transport`, unlike `github-mcp-server`'s `"source":"builtin"`. Full detail,
    including the ordering and stop-reason sub-items, in the Round log

  Save the transcript, in wire order, to `hub/tests/fixtures/copilot_acp/turn_write_shell_mcp.jsonl`. Paths must be replaced by `<WS>`/`<HOME>`, and it must hold no token. Record in the Round log:
  - whether the marker came back (Open question 1);
  - the three `request_permission` shapes (edit, execute, mcp) against design D8;
  - the `session.error|warning|info` field names, if any appeared (Open question 10);
  - (R3) for each permission request, the order of its raw `tool.execution_start`, its raw `permission.requested` and the ACP `session/request_permission`. Also whether `tool.execution_start` carried `mcpServerName` for the `agentweave` call. Design D8 relies on it preceding the request (CODE, `setupEventForwarding`);
  - (R3) the stop reason the prompt returned if a `session.error` appeared, and any second `session_info_update` title (Open question 8);
  - (review) that `Get-ChildItem` raised **no** permission request (the read-only class), and which requests `curl.exe` raised: an `execute`, a `url` carrying the `powershell` call's `toolCallId`, both, or none. And the `url` request of the `web_fetch` call, with its `toolCallId`;
  - (review) for each `execute` request, whether `tool.execution_start` named its tool (how often a genuine `powershell` request arrives with no name known; slice 3's conflict 1);
  - (review) the `source` and `transport` `session.mcp_servers_loaded` reported for `agentweave` (fixes D8's accepted source), and whether `session.mode_changed` or `exit_plan_mode.requested` appeared.
- [x] 1.2 **Capture 2 (1 prompt, `-p`).** Run `copilot.exe -p "Reply with the word ok" --output-format json --no-auto-update --disable-builtin-mcps --no-custom-instructions --no-ask-user --excluded-tools=builtin:*,mcp:*,custom:* --allow-all-tools` under a scratch home. **Never `--available-tools=`**: R2 read `app.js`'s `Y0`, and an empty value means *no filter* (design D14). Save stdout to `hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl`. Record which event carries the answer and whether any tool was offered. If the source-qualified patterns did not remove every tool, record that; design D14's fallback (the explicit built-in list) applies. Also save `evidence/help-config.txt` (the output of `copilot help config`, no model call) for task 2.4
  - **Done 2026-09-29** (`evidence/t1_2_capture.py`, build 1.0.88): 16 wire messages, RC 0, saved.
    The answer is carried by `assistant.message_delta` then finalized in `assistant.message`
    (`content:"ok"`, `toolRequests:[]`). No tool was offered: `session.info` lists 16 disabled
    tools and `session.usage_checkpoint`'s `promptCacheBreakState` reports `tool_count:0`,
    `tools:[]` — the source-qualified `--excluded-tools` patterns removed every tool by
    themselves, so D14's explicit-built-in-list fallback was not exercised (nothing to record
    beyond confirming the non-fallback path). See the Round log, "Task 1.2 — Capture 2,
    2026-09-29"
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
  - (consistency pass 2026-09-28, design D9 item 1a) with `spec_turn=True`, an `edit` inside the workspace → REJECT under `workspace`, `acceptEdits`, `manual` and full access (no card under `manual`); with `spec_turn=False` the same request keeps its posture's answer;
  - (operator decision 2026-09-28, design open question 13, option (c)) with `spec_turn=True` under full access, every **non-`edit`** row is answered as the `workspace` column answers it, never ALLOW on full access's account: a PowerShell command writing `..\..\x` → REJECT, one writing `.\x` → ALLOW, a foreign MCP server judged as under `workspace`, an MCP request whose server is not identified → REJECT, `memory` → REJECT; the same requests with `spec_turn=False` under full access → ALLOW;
  - a PowerShell command writing `..\..\x` refused under `workspace`;
  - `agentweave` MCP allowed under `manual`;
  - a foreign MCP server judged;
  - `memory` refused;
  - the answer never being `allow_always`;
  - (R2) an `edit` request with no `locations` and no `fileName` refused;
  - (R2) an unset `permission_mode` judged exactly as `workspace`;
  - (R3, replacing R2's title case) the server taken from a raw `tool.execution_start` (`mcpServerName: "agentweave"`, `mcpToolName: "send_message"`) read before the request → ALLOW under `manual`;
  - (R3) the same request with **no** raw event read, but a preceding `tool_call` titled `agentweave-send_message` (a foreign tool's `description` argument) → REJECT under every posture but full access. Under R2's rule this is an allow; it must fail on R2's code;
  - (R3) `mcpServerName: "agentweave-x"`, or `"agentweave"` with a tool the Hub does not serve → judged as foreign;
  - (R3) a `read` request with no `rawInput.path` and no `locations` → REJECT;
  - (R3) an `execute` request whose `tool.execution_start.toolName` is `local_shell`, carrying a command that only the Bash reading refuses → REJECT (both dialects);
  - (R3) a foreign MCP call whose arguments name no path and no command → ALLOW under `workspace` (Claude parity, stated in the test's docstring);
  - (review, finding 2) a `url` request carrying a `powershell` call's `toolCallId` with `https://example.com` → REJECT under `workspace`; the same URL on a `web_fetch` call → ALLOW; the same with `requestSandboxBypass: true` → REJECT; a `url` request whose id is `"url-permission"` or unknown → judged as shell text, and a URL naming the run's `hub_url` → ALLOW;
  - (review, finding 5) server `agentweave` with a tool the Hub does not serve and `{"command": "Remove-Item ..\\..\\x"}` → REJECT under `workspace`; server `agentweave__x` → judged as foreign (same command → REJECT). Both are ALLOW on R3's `mcp__<server>__<tool>` name, so the test fails on R3's code;
  - (review, finding 6) `agentweave`/`send_message` with `servers` reporting `agentweave` from source `workspace`, or `plugin`, or not reported at all → not the Hub's own (REJECT under `acceptEdits`); from the Hub's source with transport `stdio` → ALLOW;
  - (review, finding 1/slice 3) an `execute` request with no `rawInput.command` (e.g. `write_powershell`'s `{shellId, input}`) → REJECT; an `execute` whose tool name is `write_powershell` carrying a command → key `"Shell"`;
  - (review, note 12) after `tool.execution_complete` for `call_0`, a new request on `call_0` with no new `tool.execution_start` → unidentified → REJECT;
  - (review, note 16) under `manual`, an unidentified MCP request → ASK_OPERATOR with label "an MCP tool Copilot did not identify", never the title;
  - (review, note 17) a `read` whose one path contains `", "` is judged whole as well as in pieces;
  - (review, conflict 2) under `workspace`, with slice 5's rule stubbed at step 3 to return ASK_OPERATOR for everything, an unidentified MCP request is still REJECT (step 1 answers it)
- [ ] 1.7 `hub/tests/test_permission_approver.py`: `_decide(..., workspace=W, hub_url=U)` judges against `W` and `U` when `os.environ` names other values. It fails today because the keywords do not exist
- [ ] 1.8 `hub/tests/test_copilot_acp_mapper.py` (new): replay `evidence/acp4-turn-mcp-shell-1.0.88.log` and the 1.1 fixture, **in their recorded order**, through `CopilotEventMapper`. Assert:
  - one `text` event per contiguous message block;
  - `tool_use` then `tool_result` with the same call id for the shell and the MCP call;
  - a streamed partial shell output emits nothing until the terminal update;
  - the edit's `tool_use` carries the file path and diff;
  - a replayed `user_message_chunk` before arming emits nothing;
  - a synthetic message `"Warning: X"` with a matching raw `session.warning` becomes `diagnostic`, and without one stays `text`;
  - an `agentweave` server status `failed` emits one error;
  - `session.model_change` to a different model emits one diagnostic;
  - (R3) an MCP `tool_call` whose raw `tool.execution_start` names `mcpServerName: "agentweave"`, `mcpToolName: "create_task"` (so `YDo` gives it kind `edit`) emits `tool_use` with `tool == "agentweave-create_task"` and category `mcp`, never `edit`/`file_change`;
  - (R3) every `diagnostic` payload carries `version`, `stream == "copilot"`, `severity` and `summary`;
  - (R3) an `agentweave` server status `failed` on a run whose `told_access_path` is `cli` emits a `copilot.mcp_server_unavailable` diagnostic, not the error;
  - (review, cross-slice) a `session.error` whose envelope carries `agentId` (and separately one whose `data` carries `parentToolCallId`) emits a `copilot.subagent_error` diagnostic, its `Error:` echo is dropped, and the mapper does not mark the turn failed; a root `session.error` still does.

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
  - (j) a spec turn (consistency pass 2026-09-28, slice 3's D16): the spawn argv holds `--excluded-tools=apply_patch,edit,str_replace,str_replace_editor` (no `create`); under full access `allow_all` is **not** set on (read back `off`), and an `execute` request for a PowerShell command writing outside the workspace is REJECTed (judged as `workspace`; operator decision 2026-09-28, design open question 13); a `create` `edit` request for `x.py` is REJECTed and recorded through `_on_refusal`; with the switch patched on, `set_mode` carries the full plan URI before the prompt;
  - (k) (R2, narrowed in R3) a JSON-RPC `error` response to a request **before** the prompt (e.g. `session/new`) raises `CopilotACPError` carrying `.code` and `.data`, and it is an `AppServerError`;
  - (l) (R2, amended in R3) `initialize` sends `clientCapabilities._meta["github.com/copilot"].events` equal to `COPILOT_RAW_EVENTS`, de-duplicated, including `tool.execution_start`. There is no `on_raw_event` callback and no `prompt_usage`/`session_was_new` field (removed, design D10);
  - (m) (R2) the process tree is terminated on a failed turn too, not only on a stop;
  - (n) (R3) a `session/prompt` answered with a JSON-RPC error, and separately a process that exits after the prompt is written, each **return** `TurnOutcome(status="failed")` with the error and `stderr_tail`, and raise nothing;
  - (o) (R3) an armed raw `session.error` followed by `stopReason: end_turn` returns `status == "failed"` with the event's `message`. With `stopReason: cancelled` it is `interrupted`;
  - (p) (R3) `session/new` answered `-32000` raises, and `CopilotProbe`'s verdict reads not authorized before the raise propagates;
  - (q) (R3) the prompt's first text block is `per_turn_context` then `tool_surface_context`, and `control_overrides {"effort": "high"}` puts `--reasoning-effort high` on the spawn argv;
  - (r) (review, note 15 and the D5 answer) the first block opens with `COPILOT_TURN_CONTEXT_HEAD`; with `per_turn_context` and `tool_surface_context` both empty and the message `/allow-all on`, the prompt still has two blocks and the first does not start with `/`;
  - (s) (review, finding 4) a `session/load` response with `currentModeId` `#plan` on a non-spec turn → `set_mode #agent` is sent before the prompt; `#autopilot` likewise; `allow_all` `on` after load under `workspace` → `off` is set and read back; an `off` that reads back `on` → `run_turn` raises and **no** `session/prompt` is sent; an armed `session.mode_changed` into `#autopilot` under `workspace` → `session/cancel`, a `copilot_posture_escalated` error, status `failed`;
  - (t) (review, finding 6) an `agent` option whose description is not the marker → `set_config_option agent ""` is sent before the prompt; a deselect that does not read back `""` raises and sends no prompt;
  - (u) (review, finding 10) `build_acp_argv` with runner flags `--yolo --allow-tool=shell --add-dir C:\x --config-dir C:\y --deny-tool=x` under `workspace` keeps only `--deny-tool=x` and emits one `copilot.runner_flag_removed` per removed flag; under full access it keeps all but `--config-dir`;
  - (v) (review, finding 7) with `os.path.realpath` patched to sleep 2 s, a coroutine running beside the turn makes progress while a `path` request is decided (the judge runs in `asyncio.to_thread`);
  - (w) (review, finding 9) an armed `exit_plan_mode.requested` → `session/cancel`, a `copilot.plan_mode_exit_unanswerable` diagnostic, status `failed`; `SPEC_TURN_USES_PLAN_MODE` is `False`, so a spec turn sends `set_mode #agent`, not `#plan`, and still carries `--excluded-tools`
- [ ] 1.10 `hub/tests/test_copilot_home.py` (new): `copilot_home_path` is `…/copilot-home/projects/<pid>/<agent>` and refuses a project id of `..`, `a/b`, `a\b` or one resolving outside the root (R2); the worker home is `…/copilot-home/worker`. `ensure_copilot_home` writes `agents/<agent>.agent.md` with frontmatter `name`, `description` (the marker), `tools`, `model` (omitted for `auto`) and `reasoningEffort`, and a body that opens with the precedence statement and holds the stable context. It also writes `agentweave-mcp.json` with no `env` and `timeout == (agents.MAX_WAITING_SECONDS + 60) * 1000`. A second call with the same content does not rewrite the file (mtime unchanged). No file contains an `aw_run_` string. (Review, finding 8) With `hooks/allow.json`, `settings.json`, `mcp-config.json`, `installed-plugins/p/`, `agents/other.agent.md` and a `config.json` holding `trustedFolders` and `firstLaunchAt` placed in the home, `ensure_copilot_home` removes the first five, drops `trustedFolders` and keeps `firstLaunchAt`, leaves `session-state/` alone, and reports what it removed; a hook recorded in `.agentweave-owned.json` survives, and the same path with changed content is removed
- [ ] 1.11 `hub/tests/test_copilot_context_split.py` (new):
  - `_render_hub_agent_context`'s `stable`, `per_turn` and `tool_surface` (R3) together hold every `##`/`###` section of `context` exactly once;
  - the charter and project instructions are in `stable`;
  - the workspace is in `per_turn`, and the tool surface only in `tool_surface`;
  - `context` for a Claude run equals a snapshot taken before the change (write the snapshot as the first step of this task, from today's code)
- [ ] 1.12 `hub/tests/test_model_catalog.py`: `get_provider("copilot")` exists, its default model is `auto` labelled "Auto", every model's `context_window is None`, its Permissions values and labels equal Codex's with default `workspace` (R2), and `validate_overrides("copilot", {"model": "bogus-model"})` is refused
- [ ] 1.13 `hub/tests/test_workspace_writes.py`: `written_paths("edit", {"locations": [{"path": "C:/elsewhere/x.py"}], …})` returns that path, and `delete`/`move` likewise. `"shell"` returns `()`. `OutsideWriteRecorder` records a Copilot edit outside the workspace
- [ ] 1.14 `hub/tests/test_worker.py` and `test_conversation_titles.py`:
  - `build_worker_command(cli="copilot", …)` returns design D14's argv (the resolved `.exe`, not the npm shim, with `--no-custom-instructions`);
  - `build_title_command` returns it without `--no-custom-instructions`;
  - `parse_copilot_envelope` on the 1.2 fixture returns `"ok"`;
  - `copilot` is in both supported sets;
  - (R2) neither argv contains `--available-tools`, and both contain `--excluded-tools=builtin:*,mcp:*,custom:*`;
  - (R2) a Copilot conversation titled from the 1.2 fixture gets the answer, not a JSON fragment (`generate_conversation_title` with `_run_titler` patched to return the fixture);
  - (R2, mechanism fixed in R3) with `resolve_copilot_executable` raising `CopilotExecutableNotFound` (a `FileNotFoundError`), `run_worker` returns `spawn_failed` (not `unsupported_cli`) naming the looked-for path, raises nothing and removes its temporary directory, and titling returns `None`;
  - (R2) the spawn helpers pass the Copilot environment (`COPILOT_HOME` = the worker home, no `GH_TOKEN`) and still pass `env=None` for Claude and Codex
- [ ] 1.15 `hub/tests/test_launchability.py`:
  - with `GH_TOKEN` unset and a cached probe verdict "signed in, 1.0.88", `probe_agent` for `copilot` is runnable (today it says "No GitHub auth token found");
  - "not signed in" → not authorized, with the `copilot login` sentence;
  - "1.0.75" → not authorized, with the version sentence;
  - pending → runnable with `verdict_pending: True`;
  - (review, finding 11) a cached "not signed in" verdict younger than the TTL: a read returns it **and** schedules a refresh; a second read within 5 s schedules none; a positive verdict younger than the TTL schedules none. The probe's argv carries `--disable-builtin-mcps`
- [ ] 1.16 `hub/tests/test_runner_command_env.py`: `resolve_agent_env("copilot", {})` with `GH_TOKEN`/`GITHUB_TOKEN`/`COPILOT_GITHUB_TOKEN` in `os.environ` returns an environment without them. With `env_vars: {"COPILOT_GITHUB_TOKEN": "COPILOT_GITHUB_TOKEN"}` that variable is kept. Claude's environment is unchanged. (Review, finding 3) `COPILOT_ALLOW_ALL=true` ambient, and separately in `env_vars`, is absent from the result under every posture, and the `env_vars` case is reported as removed (the turn's `copilot.permission_override_removed` diagnostic); the same for every name in `COPILOT_TRUST_ENV_NAMES`; `COPILOT_HOME` in `env_vars` does not survive over the Hub's. (Consistency pass 2026-09-28, slice 5's 2.10) Ambient `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_BEARER_TOKEN`, `COPILOT_PROVIDER_WIRE_MODEL`, `COPILOT_MODEL` and `COPILOT_OFFLINE`, and the same names in `env_vars`, are absent under every posture (the `env_vars` case reported as removed). The one-shot environment (`one_shot_env`) and the probe's environment pass through the same function
- [ ] 1.17 `hub/tests/test_mcp_server_stdio_surface.py`: spawn `mcp_server.py` as the Hub does, with `HUB_URL` on a dead port. Send `{"jsonrpc":"2.0","id":0,"method":"server/discover","params":{}}` **before** `initialize`. Assert a JSON-RPC error response with id 0 (not a crash, not silence). Then `initialize` with `protocolVersion "2025-11-25"` succeeds and `tools/list` lists `send_message`.

  This test documents behaviour R1 measured (design § VERIFIED). It passes today and is a guard, which it says in its docstring
- [ ] 1.18 `hub/tests/test_tool_surface_matches_server.py`: a Copilot run in the MCP form names every tool `agentweave-<tool>`, and the access notice does too. **Depends on** `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` having landed. If it has not, leave this unchecked and say so
- [ ] 1.19 UI tests:
  - `hub/ui/src/__tests__/` asserts `providerForRunner('copilot') === 'copilot'`;
  - `ProviderMark` renders an SVG, not initials, for `copilot`;
  - the Runners page's CLI select offers `copilot`;
  - (R2) an `AgentTimeline` tool row with `tool: "edit"` is rendered as a writing block.

  Extend `modelCatalogFixture.ts` with the Copilot provider. Verify: `cd hub/ui && npx vitest run`
- [ ] 1.20 **Probe (no model call; review 2026-09-28, finding 6).** Under a scratch `COPILOT_HOME`, in a scratch git repository holding `.mcp.json` and `.github/agents/<agent>.agent.md` whose `mcp-servers` both name a stand-in server `agentweave`, spawn `copilot.exe --acp` with the Hub's `--additional-mcp-config` (dead `HUB_URL`) and `COPILOT_ALLOW_ALL` unset. Run `initialize` (subscribing `session.mcp_servers_loaded`), `session/new`, select then deselect the agent, and `session/close`. Record in the Round log which `agentweave` loaded and with what `source`/`transport`, whether the repository agent's `mcp-servers` loaded at all in an untrusted folder, and whether deselecting it changed the loaded servers. The result fixes D8's accepted `source`

## 2. Registry, migration, seeding, catalog

- [ ] 2.1 `db/models.py`: `RUNNER_CLIS = ("claude", "codex", "copilot")`, and the `ck_runners_cli` constraint is written from `RUNNER_CLIS`, so the two cannot drift
- [ ] 2.2 A new migration, the next free revision after tonight's queue, recreates `runners` with the widened constraint (`batch_alter_table(recreate="always")`) and guards a missing table. Downgrade refuses when a `copilot` row exists. Bump `HEAD_REVISION` in `hub/tests/test_migrations.py` and the head in `hub/tests/test_project_persistence.py` (`.claude/rules/db-migrations.md`)
  - Verify: `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py hub/tests/test_runners_api.py -q`
- [ ] 2.3 Confirm both seeders produce `Copilot (default)`. Task 1.4 passes
- [ ] 2.4 `model_catalog.py`: add `CATALOG["copilot"]` per design D13, taking the model tuple from `evidence/help-config.txt`, with the Permissions default `workspace`. Add `"copilot": "copilot"` to `runner_commands._CATALOG_PROVIDER_BY_RUNNER` (or slice 1's `catalog_provider`) and `copilot` to `SUPPORTED_RUNNERS` (`test_model_catalog.py:16-18` requires it). R2: drift is checked by a `--provider copilot` section in `scripts/check_model_catalog.py` that runs `copilot help config`, **not** by a pytest that skips without the binary (that script's docstring says why). Tasks 1.12 and 1.3 pass
  - Verify: `py -3.11 -m pytest hub/tests/test_model_catalog.py hub/tests/test_model_catalog_api.py -q`

## 3. Executable, probe, launchability

- [ ] 3.1 `hub/hub/copilot_probe.py`: `resolve_copilot_executable` (design D2). Task 1.5 passes
- [ ] 3.2 `CopilotProbe`: a cached, TTL'd, async refresh using `initialize` → `session/new` → `session/close` under the worker home, with no model call (design D15). R2: the refresh is scheduled by `CopilotProbe.verdict()` itself whenever the verdict is stale and a loop is running, so all six `probe_agent` callers keep it fresh; amend `get_agents_launchability`'s "never spawns anything" docstring. Test its refresh against a fake process
- [ ] 3.3 `launchability.py`: delete the env-token branch (`:116-126`) with its tests (`test_launchability.py:124-140`) and (R3, slice 1 D5) the `RUNNER_CLI["copilot"]` row, make `probe_agent` read the Copilot verdict (its `cli` the resolved path; an unclassified refresh failure leaves the verdict unchanged and adds `probe_error`, design D15), add `copilot` to `MCP_INJECTABLE_RUNNERS` (`:230`; R2: without it no Copilot run is given the MCP server), and extend `resolve_agent_env` with the GitHub-token strip and (review 2026-09-28) the unconditional `COPILOT_TRUST_ENV_NAMES` strip and (consistency pass 2026-09-28) the no-provider `COPILOT_PROVIDER_*`/`COPILOT_MODEL`/`COPILOT_OFFLINE` strip, with `COPILOT_HOME` set after `env_vars` (design D3). Tasks 1.15 and 1.16 pass
  - Verify: `py -3.11 -m pytest hub/tests/test_launchability.py hub/tests/test_runner_command_env.py hub/tests/test_copilot_probe.py -q`

## 4. The Hub-owned Copilot home and the context split

- [ ] 4.1 `_render_hub_agent_context` returns `stable` and `per_turn` beside the unchanged `context` (design D5). Task 1.11 passes
- [ ] 4.2 `hub/hub/copilot_home.py`: `copilot_home_path` and `ensure_copilot_home` (design D4), including (review) the configuration-surface sweep and the `.agentweave-owned.json` recorder. Task 1.10 passes
- [ ] 4.3 Call `ensure_copilot_home` after `create_operator_agent` commits and after `PATCH /agents/{name}` commits, for a Copilot-bound agent: on create after the `agent_created` broadcast (`agents.py:758`), on PATCH before the `schedule_agent` re-drain (`:2720`). **Any** exception is logged and does not fail the route (R3: not only `OSError`). Not after `POST /agents/request`, design D4 (R3). Add route tests: creating a Copilot agent produces the agent file; a patched write raising `OSError`, and one raising `RuntimeError`, each still return 201 and broadcast `agent_created`
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_home.py hub/tests/test_copilot_context_split.py -q`

## 5. Approvals

- [ ] 5.1 `mcp_server.py`: add keyword-only `workspace`/`hub_url` to `_decide`, and thread `hub_url` through `_read_command`, `_judge_word`, `_judge_url` and `_is_own_hub` (R2: all five; `HUB_URL` is read at `:1191` and `:1241`), defaulting to the environment. Add no import (`.claude/rules/mcp-server.md`). Task 1.7 passes, and `test_permission_approver.py` and `test_mcp_server.py` are otherwise unchanged
- [ ] 5.2 `copilot_acp.decide_permission` (design D8), with the per-kind operator-card labels beside `_CODEX_APPROVAL_LABELS`; (review) the client and `workspace_verdict` call it through `asyncio.to_thread`. Task 1.6 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_acp_decide.py hub/tests/test_permission_approver.py hub/tests/test_mcp_server.py -q`

## 6. The ACP transport

- [ ] 6.1 `runner_events.diagnostic_event(*, stream, severity, summary, code=None, facts=None)` (R3: slice 5's shape, which `agent-stream-events` requires) in the closed set, with a test that its payload has `version`, `stream`, `severity` and `summary`. `copilot_acp.CopilotEventMapper` (design D10). Task 1.8 passes
- [ ] 6.2 `copilot_acp.ACPProcess`: stdio JSON-RPC as `AppServerProcess`, UTF-8, stderr drained, and a pending-request map. It additionally supports a request whose response is awaited while notifications are drained, and handles agent→client requests. `close()` ends the process tree with `terminate_process_tree`. Test it against a stand-in script, as `test_codex_appserver_process.py` does
- [ ] 6.3 `copilot_acp.build_acp_argv` and `run_turn` (design D3, D6, D7, D9, D11, D12, D17). Task 1.9 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_acp_mapper.py hub/tests/test_copilot_acp_run_turn.py -q`

## 7. Wiring into the trigger

- [ ] 7.1 If slice 1 did not already make `_execute_codex_appserver_run` a runner-parameterised RPC executor, do that first: replace the four `runner="codex"` literals (`agent_trigger.py:3089`, `:3261`, `:3350`, `:3445`) with the adapter's name, and `codex_run_turn` with the adapter's `run_turn`. Run the whole Codex app-server suite unchanged
  - Verify: `py -3.11 -m pytest hub/tests/test_codex_appserver_run_turn.py hub/tests/test_codex_appserver.py -q`
- [ ] 7.2 In `trigger_agent_directly`, a `copilot` runner:
  - resolves the executable (a `TriggerAgentError(409, agent_wide=True)` with the probe's sentence when absent);
  - ensures its home with this turn's model and effort (`TriggerAgentError(409, agent_wide=True)` on failure; R3);
  - sets `COPILOT_HOME` in the environment;
  - sends the per-turn block and the prompt;
  - reaches the RPC executor with the Copilot adapter.

  `on_session_missing` rebinds under design D7's exception. Add `_bind_session_id(replace_missing=True)`. Add a trigger-level test with the adapter's `run_turn` patched, asserting `Run.session_id` and `Conversation.provider_session_id` after a rebind.

  R2: first admit `copilot` past the three gates of design D1: `SUPPORTED_RUNNERS` (`agent_trigger.py:773`, 501 today), the `build_command` call (`:1214`, 501 at `:1230`; skipped for an RPC transport) and `MCP_INJECTABLE_RUNNERS` (task 3.3). The trigger-level test enters through `trigger_agent_directly`, not the executor, and asserts the patched `run_turn` received a non-`None` `mcp_command` and the per-turn block. It fails today with 501. (R3) A route test through `POST /agent/trigger` with the home write patched to fail asserts **200** `status: "queued"` with the sentence in `waiting_reason`, and that the queue entry's delivery attempts are unchanged
- [ ] 7.3 Route an operator card for `ASK_OPERATOR` through `_await_operator_permission` with Copilot's labels (and its `workspace` verdict once `an-ask-me-card-says-what-workspace-only-would-decide` lands). Route refusals through `_on_refusal`, and allows through the `on_decision` callback whose executor side is `permission_tally.note`/`write_counts` from `a-run-records-that-its-calls-were-allowed` (R2: unbuilt at R2; if still unbuilt at IMPL, record refusals only and say so)
  - Verify: `py -3.11 -m pytest hub/tests -q -k "copilot or appserver or trigger"`

## 8. Outside writes, one-shot calls, tool names, display

- [ ] 8.1 `workspace_writes.py`: `COPILOT_WRITE_TOOLS = {"edit", "delete", "move"}` reading `locations[].path`, added to `WRITE_TOOLS`. Task 1.13 passes
- [ ] 8.2 `worker.py`: add the `copilot` branch, `parse_copilot_envelope` and the worker-home environment; `_run_worker_process` and `_run_titler` gain an `env` parameter (R2: neither passes one today). `conversation_titles.py` gets its `copilot` branch and parses the envelope before `title_from_output` (design D14). The builders catch a resolution failure rather than raise. Task 1.14 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_worker.py hub/tests/test_conversation_titles.py hub/tests/test_title_generation.py -q`
- [ ] 8.3 The tool surface uses the `agentweave-` prefix and Copilot preamble for Copilot runs (design D16), through the mechanism of `a-claude-run-is-told-its-agentweave-tools-by-their-full-names`. Task 1.18 passes
- [ ] 8.4 `api/v1/agents.py` `_display_model` gains `"copilot": agent_meta.get("model", "GitHub Copilot")`
- [ ] 8.5 CI parity: `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`, `py -3.11 -m pytest hub/tests/ -q`. With `claude` stripped from `PATH`, re-run the Copilot tests to confirm they do not depend on a local CLI (memory: the local suite is green because `claude` is on `PATH`)

## 9. UI

- [ ] 9.1 `RunnerCli`, `CLI_OPTIONS`, `providerForRunner`, `PROVIDER_MARKS.copilot` from `siGithubcopilot` in `currentColor`, and (R2) `AgentTimeline.tsx`'s `WRITING_TOOLS`/`TOOL_ICON` gain `edit`, `delete`, `move` (design D19). Task 1.19 passes
- [ ] 9.2 `cd hub/ui && npm run lint && npx vitest run && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`. Commit `hub/ui/src` and `hub/hub/static/ui` together (`.claude/rules/hub-ui.md`)

## 10. Findings and docs

- [ ] 10.1 Record in `spec-queue/` FINDINGS the appendix corrections from the Round log (R1: `--no-auto-update` version, `~/.agents/skills`, the MCP 30 s timeout; R2: an empty `--available-tools=` means no filter, project-level custom agents outrank `$COPILOT_HOME/agents`), so later slices do not inherit them. From the review (2026-09-28), also file:
  - Copilot auto-approves shell commands it classes read-only, so a Copilot run's Workspace only judges fewer commands than Claude's (parity measured, not assumed; cite 1.1's `Get-ChildItem` record);
  - `_decide` resolves UNC and device paths with `realpath` before refusing them, which blocks ~21 s per unreachable host and opens an SMB connection from whichever process judges; it should refuse `\\`, `//`, `\\?\` and `\\.\` before any I/O, for every runner

## 11. Drive on the trial Hub `:8010`

Start it **from `hub/`, from source**, never through `agentweave --port 8010`, and never touch `:8000`:
`cd hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/trial/agentweave.db" py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1`.
Confirm the database it serves before trusting it (`.claude/reference/hubs.md`).

Copilot **Free plan**, Auto only: this group spends **at most four** model prompts. Keep every prompt tiny, and record each prompt's cost in the drive notes.

- [ ] 11.1 No model call. Check the following:
  - the Runners page offers `copilot`;
  - create a Copilot runner, then a Copilot agent `cop-1` on it with a short charter;
  - `~/.agentweave/hub/copilot-home/projects/proj-d85a82bf4216/cop-1/agents/cop-1.agent.md` exists (confirm the trial Hub's project id first) and holds the charter and the precedence statement, and the repository has no new file;
  - launchability for `copilot` reads runnable and names no token.
- [ ] 11.2 **Prompt 1.** Under Workspace only, send `cop-1`: *"Create hello.txt containing hi in your workspace, then send me a one-line message with agentweave-send_message."* Record the timeline verbatim:
  - one text block per message;
  - the edit's tool row with its path;
  - the message arriving in the operator inbox;
  - a context reading with a limit;
  - the Auto-substitution diagnostic, if any;
  - no replayed history.

  Then confirm `Conversation.provider_session_id` is set.
- [ ] 11.3 **Prompt 2.** A specification turn, with `SPEC_TURN_USES_PLAN_MODE` switched **on for this drive only** (it ships off, design D9): open an empty spec document and ask `cop-1` one question about it. Check: it interviews rather than writing a plan file; it has no editing tool but `create`, and any file it tries to create is refused (design D9 item 1a); whether `exit_plan_mode` was called and whether `exit_plan_mode.requested` reached the client (and so cancelled the turn); and that the next, non-spec turn of the conversation (11.4) starts in `#agent`. Leave the constant `False` unless neither the interview nor the ending suffered; turning it on is a commit citing this drive. If the turn was cancelled, file a finding and re-run with prompt 3 with the constant off.
- [ ] 11.4 **Prompt 3.** Under Ask me, in the same conversation (a resume), ask for `echo hi` in the shell. An operator card opens. Deny it: the timeline shows the refusal, the run completes, and the first turn's output is not rendered again.
- [ ] 11.5 **Prompt 4 (only if unused).** Stop a running turn with the stop button during a long request. The run ends `stopped`, and no `copilot.exe` or `powershell.exe` child of it survives: check with `Get-Process`.
- [ ] 11.6 Write the drive notes into `design.md`'s Round log (prompts spent, what matched, what did not). File every mismatch as a finding. Measure Open question 5 from the context readings of 11.2 and 11.4.

## 12. Archive

- [ ] 12.1 All tasks above checked, or explicitly deferred with a finding. `openspec validate a-copilot-agent-runs-over-acp --strict` passes. Sync the deltas into `openspec/specs/` (`openspec-sync-specs`) and archive (`openspec-archive-change`). Write the handoff per the handoff-cadence rule
