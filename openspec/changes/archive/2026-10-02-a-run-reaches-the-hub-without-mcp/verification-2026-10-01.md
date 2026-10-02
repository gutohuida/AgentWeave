# IMPL-time verification — 2026-10-01

Fresh comparison of `design.md` / `tasks.md` against master `eec4085` (slices 1 and 2 archived; full-names,
ask-me card, permissions pill and cannot-collaborate changes built; `a-run-records-that-its-calls-were-allowed`
NOT built). Read-only, except this file. Working tree at verification time held uncommitted task-2.1 work
(`0115_run_harness_mcp_status_and_plane_surface.py`, `db/models.py` `Run.harness_mcp_status`/`plane_surface`,
`HEAD_REVISION = "0115"` in `test_migrations.py`, bump in `test_project_persistence.py`); git warns that
`hub/hub/db/models.py` now has CRLF line endings in the working copy.

## 1. Moved, renamed, deleted or reshaped references

| cited (design/tasks/proposal) | today |
|---|---|
| `launchability.py:252-280` `harness_has_honoured_mcp` | `:227-256`, unchanged shape (`.limit(1)`, no order) |
| `launchability.py:311-312` `if access_path != "mcp": return access_path` | `:286-287`; still returns `"cli"` |
| `launchability.py:313-314` override | `:288-289` |
| `launchability.py:402-438` / `:409-413` / `:414-438` notice | `access_path_notice(access_path, tool_prefix="")` at `:377`; MCP branch `:388-393`, HTTP branch `:394-425`. Takes **no runner/adapter** argument (needed for D10's Codex sentence) |
| `agent_trigger.py:1106-1112` grounds call | `:1106-1111`, already in slice 1's predicted shape: `axes = resolve_access_axes(adapter, hub_client=…, flags=runner_flags)`; `described_access_path(axes.plane, override=hub_client, harness_honoured_mcp=…)` |
| `agent_trigger.py:1160-1169` context write | `:1163-1171` |
| `agent_trigger.py:1173` `notices = [access_path_notice(...)]` | `:1178-1179` (now with `notice_prefix = adapter.mcp_tool_prefix if described=="mcp"`) |
| `agent_trigger.py:1194` prompt join | `:1198` |
| `agent_trigger.py:1195-1203` pin | `:1200-1208`, guarded `if axes.tool_surface == "mcp"`, calls `tool_server.pinned_server_path()` (wraps `PIN.path()`) |
| `agent_trigger.py:1210` `codex_appserver.uses_app_server` | **deleted**; `run_transport = adapter.transport(runner_flags)` at `:1218` (Codex opt-out flag `APP_SERVER_OPT_OUT_FLAG`, `runner_adapters/codex.py:263-266`). Note `run_transport` is computed **after** `notices` |
| `agent_trigger.py:1217/:1403` prompt passed | `:1245` (`build_command`), `:1442` (`_execute_run`) |
| `agent_trigger.py:1246` `AW_RUN_TOKEN` | `:1279` |
| `agent_trigger.py:1292` `HUB_API_KEY` strip | `:1325` |
| `agent_trigger.py:1306` `Run(...)` | `:1343` |
| `agent_trigger.py:3244` run_turn exception tuple | `:3582` `(FileNotFoundError, AppServerError, asyncio.TimeoutError, OSError)` |
| `agent_trigger.py:~2451-2560` claude read loop | `_flush_line` `:2533`, `transport.map_events(line, model=…)` `:2542` (runner-neutral, shared with Codex exec) |
| `agent_trigger.py:1243-1304` env block | `:1272-1341`; Copilot sets `COPILOT_HOME` last at `:1338-1341` |
| slice 2 "prompt composition / `build_launch` / copilot.exe env" | No `build_launch` for Copilot. `_prepare_copilot_turn` `agent_trigger.py:3118`, `_CopilotTurn` `:3102`, `_execute_copilot_run` `:3205`, `_execute_rpc_run` `:3294`; argv is `copilot_acp.build_acp_argv` `:1474`; env is `req.env` passed unchanged to `create_subprocess_exec` (`copilot_acp.py:1230-1233`) |
| `RpcTurnRequest.told_access_path / tool_surface_context / per_turn_context` | exist, `runner_adapters/base.py:107-129` (frozen dataclass; defaults `None`). Codex's `_execute_rpc_run` adapter path (`agent_trigger.py:3348-3364`) does **not** set `told_access_path`; `CodexAppServerTransport.run_turn` (`codex.py:192-211`) does not forward it; `codex_appserver.run_turn` (`:913`) has no such parameter |
| `RpcCallbacks` (slice 1) | Two classes: transport-facing `runner_adapters.base.RpcCallbacks` (`base.py:132-146`, frozen, has `request_approval`, optional `on_session_missing`) imported in the trigger as `TransportRpcCallbacks`; and executor-local `agent_trigger.RpcCallbacks` (`:3086-3099`). **No `render_surface` field and no MCP-status callback exist** |
| `tests_mcp_before_first_prompt` ClassVar on both transport ABCs | **absent** (`StreamTransport` `base.py:149`, `RpcTransport` `:187`) — this change adds it |
| `RunnerAdapter.mcp_tool_prefix` / `host_tool_note` | exist (`base.py:243-244`); Claude `claude.py:112-116`, Copilot `copilot.py:228-233` (`COPILOT_MCP_TOOL_PREFIX = "agentweave-"`, `runner_commands.py:51`) |
| `AccessAxes` names | as designed: `tool_surface` mcp/none, `approvals`, `plane` mcp/cli (`base.py:84-90`) |
| `posture_at_rest` | `runner_commands.posture_at_rest` deleted; `RunnerAdapter.posture_at_rest(axes, *, yolo)`; Claude delegates to `runner_commands.claude_posture_at_rest(approvals, yolo)` `:107` |
| `LaunchRequest` / `build_command` | `base.py:93-105` and `runner_adapters/__init__.py:51`; carry `restrict_spec_writes` but **no `described_access_path`** (5.6 adds it to both plus `_build_claude_command`) |
| `runner_commands.py:229` `--disallowedTools` | `:189` (comment `:178-188`) in `_build_claude_command` `:158` |
| `runner_commands.py:262` `--allowedTools mcp__agentweave__*` | `:154`, inside `_claude_mcp_args`, which **is** `ClaudeStreamTransport.inject_mcp` (`claude.py:87-88`) |
| `runner_commands.py:287` `-p` | `:235` |
| `mcp_server.py:8-16` imports, `:18-21` fastmcp | unchanged; still no `import sys` |
| `mcp_server.py:360-525` / `:404-525` `ask_user` | `:383-548` |
| `mcp_server.py:871-919` `archive_job` | `:899-948` |
| `mcp_server.py:1005` question timeout | `:1032` |
| `mcp_server.py:1009` `_PATH_KEYS` | `:1036` |
| `mcp_server.py:1061` `_ARGUMENT_ENDS` | `:1088` (`"|;&<>()"`, unchanged) |
| `mcp_server.py:1072` `_TOOL_DIALECTS` | `:1099` (unchanged) |
| `mcp_server.py:1403-1505` `_lex`/`_words`; `:1476` `isspace` | `_lex(command, bash, reading)` `:1448` (third arg `reading` ∈ `"c"/"utf8"`), `isspace` `:1521`, `_words` `:1535` returns `(word, _, bool)` triples |
| `mcp_server.py:1557-1558` `_decide` own-tools line | `:1618-1619`; `_decide(..., *, workspace=None, hub_url=None)` `:1593` |
| `mcp_server.py:1567` root realpath | `:1632` |
| `mcp_server.py:1595-1614` `_report_decision`; `:1715` call | `:1678-1698`; call `:1826`; body unchanged (run-records change unbuilt) |
| `mcp_server.py:1630-1655` `_ask_operator` | `:1713-1751` — ask-me change **built**: `_workspace_verdict` `:1754` + 422 retry |
| `mcp_server.py:1705-1712` / `:1709-1710` `approve_tool_call` operator branch | `:1808-1830` / `:1820-1821` |
| `mcp_server.py:2073-2088` announce, `:2091-2094` `main`, `:2106` guard | `:2187-2202`, `:2205-2208`, `:2220` |
| `@mcp.tool()` count | 27, unchanged |
| `agents.py:983` `http_note` | `:985` |
| `agents.py:989-999` `UNDESCRIBED_TOOLS` | `:991-1002` |
| `agents.py:1016` import from `mcp_server` | `:1022` |
| `agents.py:1484-1505` `_http_lines` | `:1507-1529` |
| `agents.py:1541` `over_mcp`, `:1547-1560` HTTP preamble | `:1575`, `:1597-1607`. `_tool_surface_lines(*, has_peers, access_path="mcp", runner=None)` `:1531` — prefix derived from `get_adapter(runner)`, no `tool_prefix`/`question_timeout` parameter; `host_tool_note` appended in every form (`:1611-1612`) |
| `agents.py:2126` the one `_tool_surface_lines` call | `:2245` (inside `_part("tool_surface")`); split keys `stable`/`per_turn`/`tool_surface` returned `:2289-2293` |
| `agents.py:898` / `agent_chat.py:341` `RunFacts(` | `agents.py:899` (`GET /agents/{name}/timeline`), `agent_chat.py:341` (`_run_facts_for`, served by `GET /agent/{agent}/chat` and `/chat/{conversation_id}`) |
| `schemas/agents.py:140-169` `RunFacts` | `:156-189` |
| `agent_actions.py:459-483` announce route | unchanged |
| `codex_appserver.py:547-567` / `:557-561` `map_mcp_server_failure` | `:556-575` / text `:569-571`; signature `(params, *, own_server_name)` |
| `codex_appserver.py:1162-1183` startupStatus branch | `:1165-1186` (only `status == "failed"` handled) |
| `codex_appserver.py:280-283` `decide_approval` workspace branch | `:286-291` (ask-me change built, `workspace_verdict` `:233`) — group 6 cut, informational |
| `workspace_writes.py:38-43` `CLAUDE_WRITE_TOOLS` | `:40-45` |
| `tool_server.py:39-56` `path()` | `:39-57`; `PIN`, `ToolServerPin`, `prune_stale`, `pinned_server_path` all as cited |
| `repo_hygiene.py:59-85` | `EXCLUDE_PATTERNS` from `:59` |
| `runner_events.status_event` `:221`; `_truncate_utf8` | `:221`; `_truncate_utf8` `:88` |
| `test_agent_trigger.py:713` env test | `:708` |
| `test_launchability.py:588` `access_path_notice("cli")` | **four** sites: `:576`, `:584`, `:595`, `:618` (plus `test_agent_facing_text.py:162`) |
| `test_codex_appserver_run_turn.py:555` | `:556` |
| `harness_honoured_mcp=` callers to migrate (not in tasks) | `test_launchability.py:522-552` (7 asserts), `test_mcp_adapter_online.py:19,99-129` |
| slice 2 fake ACP agent | in `hub/tests/test_copilot_acp_run_turn.py` |
| `.claude/rules/mcp-server.md` | step 1 at `:18` says "Add an `@mcp.tool()` decorated function" — must change with 3.1, not only gain a bullet (3.4) |

Copilot (slice 2) contracts as built:
- `copilot_acp._standing_rules(pairs, *, kind, facts, posture, spec_turn)` `:505-516` — the empty step-3 slot reserved for `_hub_own_call`; returns `None` today.
- Normalised names (`normalise_request` `:456-502`): `("PowerShell"|"Bash"|"Shell", {"command"})` via `_shell_key` `:440-449`; `edit` → one `("Write", {"path": p})` per path, paths from `locations[].path`, `rawInput.fileName`, `rawInput.path` (ACP locations are typically absolute).
- Spec-turn rules already shipped: `SPEC_TURN_EXCLUDED_TOOLS` without `create` `:125`; every spec-turn `edit` not allowed by step 3 is REJECT in every posture `:604-607`; full-access spec turn judged as `workspace` (`judged`, `:553`) and `allow_all` not set on (`:2023`, `:2075-2076`); Plan mode gated `spec_turn and SPEC_TURN_USES_PLAN_MODE and told_access_path == "mcp"` `:1997` with `SPEC_TURN_USES_PLAN_MODE = False` `:120`.
- `CopilotEventMapper(told_access_path=…)` `:823-840` (plain mutable attribute); `_server_status` `:1066-1110`: `copilot_mcp_server_failed` only when `told_access_path == "mcp"`; otherwise a `copilot.mcp_server_unavailable` diagnostic saying the run "reaches the Hub by its HTTP form instead"; `connected` is in `_TRANSIENT_SERVER_STATUSES` `:773` and is skipped.
- Wait slot marker: `copilot_acp.py:2073` "(Slice 3's announce wait and `render_surface` go here, before the prompt.)" — **after** `session/set_mode` (`:1997-2020`) and the allow-all step.
- `run_turn` already has an `on_decision` parameter (`:1603`, used `:1838-1840`); `CopilotAcpTransport.run_turn` passes none (`copilot.py:198-199`).
- `decide_permission` `:625-657` wraps everything and turns any exception into REJECT.
- `HUB_MCP_TOOLS` `:174-204` is a third restated copy of the tool names (asserted against `mcp.list_tools()` in `test_copilot_acp_decide.py:901-910`).

## 2. Per-task verdicts

- **1.1** Buildable. Also rewrite the 7 `harness_honoured_mcp=` asserts in `test_launchability.py:522-552` and `test_mcp_adapter_online.py:99-129` (they test the function being removed).
- **1.2** Buildable (`parse_claude_line` `runner_parsing.py:229` still has no `system` branch; `ParsedLine` `:51-55` gains the field).
- **1.3** Buildable. `test_copilot_acp_decide.py:901-910` keeps working via `list_tools()`.
- **1.4, 1.5** Buildable.
- **1.6** Buildable; add rows for Copilot's absolute `locations` paths if case 3 is meant to allow them (see §3 item 7).
- **1.7** Buildable.
- **1.8** Rebase `:713`→`:708`; patching `PIN.path` works because the trigger calls `pinned_server_path()`.
- **1.9** Rebase: four `access_path_notice("cli")` sites in `test_launchability.py`, not one.
- **1.10** Buildable.
- **1.11** Test file is `hub/tests/test_chat_run_facts.py` (and the timeline test).
- **1.13** Buildable; also expect slice 1's golden-argv tests for Claude to change (allowedTools now emitted without MCP).
- **1.14** Partly already true on today's code: rows "raw not-connected on a run told shim emits no `copilot_mcp_server_failed`" and "told `mcp` then raw `failed` emits it once" pass today (slice 2 gates on `told_access_path == "mcp"`), so they are not fail-first except for the "recorded `failed`" half. Add a row: a run told `shim` gets no `copilot.mcp_server_unavailable` "HTTP form" diagnostic (§3 item 3).
- **1.15** Copilot half mostly already true: argv excludes `apply_patch,edit,str_replace,str_replace_editor` but not `create`; a `src/x.py` edit is REJECT in every posture with no card; full-access non-`edit` judged as workspace; no `allow_all` on a spec turn — all pass today. Only the args-file `edit` allow (via 6.2) and "set_mode plan after the wait" are new; the latter needs `SPEC_TURN_USES_PLAN_MODE` patched true, since it ships `False`. Claude half buildable after 5.6.
- **2.1** In flight in the working tree as `0115`. Buildable.
- **2.2** Buildable. The route rewrite must also write the status when the stamp is already set but the status is NULL/`absent` (today's `if run.mcp_adapter_online_at is None` guard writes nothing on a second announce).
- **2.3** Buildable.
- **2.4** Rebase: call at `agent_trigger.py:1107-1111`, already reading `axes.plane`. Change `return access_path` (`:287`) to `"shim"`.
- **2.5** Rebase to `_flush_line` `:2533-2560`. It is shared with Codex `exec`; key the write on `parsed.harness_mcp_status is not None and mcp_command`, never on the runner name.
- **2.6** Under-specified, not just rebased. "`run_turn` passes the request's told surface" is four hops on today's tree: `_execute_run` → `_execute_rpc_run(adapter, transport, …)` (no `told_access_path` parameter, `:3294`) → its `RpcTurnRequest(...)` (`:3348`, field not set) → `CodexAppServerTransport.run_turn` (`codex.py:192`, not forwarded) → `codex_appserver.run_turn` (no parameter) → `map_mcp_server_failure`. The status callback likewise needs a new transport `RpcCallbacks` field and a `codex_appserver.run_turn` kwarg; neither exists. `TestRunTurnMcpStartupFailure` at `:556`.
- **2.7** Rebase `agents.py:898`→`:899`.
- **3.1** Buildable; also edit `.claude/rules/mcp-server.md:18` (step 1 names `@mcp.tool()`).
- **3.2–3.4** Buildable.
- **4.1** Buildable.
- **4.2** Rebase: `PATH` beside `:1279`; calls dir beside `:1163-1171`; pin at `:1200-1208` (move out of `if axes.tool_surface == "mcp"`).
- **4.3** Buildable.
- **5.1** Answered by the code: `copilot.exe` receives the whole run env (`req.env` → `create_subprocess_exec(env=env)`, `copilot_acp.py:1230-1233`), so a `PATH` prepend placed with `AW_RUN_TOKEN` reaches it. There is no `build_launch` for Copilot. Nothing to add in 5.4.
- **5.2** Buildable. Signature needs new inputs: `access_path_notice` has no runner/adapter parameter (needed for D10), and `_tool_surface_lines`/`_render_hub_agent_context` have no `question_timeout` (use `effective_question_wait(agent_row)`, `agent_trigger.py:592`). The "host-`SendMessage` sentence in the shim form" bullet is already satisfied: `host_tool_note` is appended in every form (`agents.py:1611-1612`).
- **5.3** Rebase `:2126`→`:2245`, `:1306`→`:1343`.
- **5.4** Partly done by slice 2; what remains is concrete and larger than stated:
  - `tests_mcp_before_first_prompt` and `render_surface` must be added to `runner_adapters/base.py` (`RpcTransport` and the frozen transport `RpcCallbacks`), forwarded by `CopilotAcpTransport.run_turn` as a new `copilot_acp.run_turn` kwarg, and built in `_execute_copilot_run._start_turn`.
  - Omitting the pre-spawn notice needs the transport before `notices` is built: `run_transport` is computed at `:1218`, after `notices` (`:1179`); move it up (raw flags are available at `:1105`).
  - The wait slot (`:2073`) sits after `session/set_mode`, which reads the pre-spawn `told_access_path` (`:1997`); "Plan mode after the wait" means moving the wait above `set_mode` or the mode step below the wait.
  - `RpcTurnRequest` is frozen: "the transport replaces `told_access_path`" means a local variable and `mapper.told_access_path = surface`, not a request mutation.
  - The `/mcp list` reply cannot be read through the existing handler: `on_notification` drops every `session/update` until `state["armed"]` (`:1757-1760`), and arming before it would put the slash reply in the run's timeline. It needs its own collector.
  - An interrupt during the wait has no return path: `run_turn` only raises before the prompt; ending `interrupted` with status NULL needs a `TurnOutcome` built before arming.
  - The spec-turn bullet reduces to: the args-file allow (comes from 6.2's `_standing_rules`) and the plan-mode move. `create`, the edit refusal, no `allow_all` and the full-access-as-workspace answer are all shipped.
  - The mapper must record raw `connected` before its `_TRANSIENT_SERVER_STATUSES` skip (`:1080`), and `failed` before the once-per-turn flag.
- **5.5** Buildable, but `_execute_run` receives neither `described_path` nor `hub_client`. Read `plane_surface` from the row (written at `Run(...)`) and pass the declaration through.
- **5.6** Buildable: add `described_access_path` to `LaunchRequest` (`base.py:93`), `build_command` (`__init__.py:51`), `ClaudeStreamTransport.build_launch` (`claude.py:68-85`) and `_build_claude_command` (`runner_commands.py:158`).
- **6.1** Buildable. `_lex` takes a third `reading` argument; with an ASCII allow-list either reading gives the same words.
- **6.2** Rebased target: put the call in `copilot_acp._standing_rules` (`:505`), which runs before the edit refusal, the hub-own check and the posture branches. Wrap it in its own `try`, because `decide_permission`'s outer handler turns any exception into REJECT, not fall-through. `on_decision` is not wired (run-records change unbuilt); a standing allow reaches the recorders through `answer_permission` like any other.
- **7.1** Rebase: `--allowedTools mcp__agentweave__*` is emitted by `_claude_mcp_args` (`runner_commands.py:154`), which is also `inject_mcp`. Adding `aw-tool` there would make "inject MCP" carry an unrelated rule, and it would be missing when no MCP is injected. Emit the aw-tool rules in `_build_claude_command` for non-yolo, and check that Claude accepts a repeated `--allowedTools` (or merge into one).
- **9.x** No code drift. 9.2's `agentweave-create_task` matches `COPILOT_MCP_TOOL_PREFIX`.

## 3. Premises that no longer hold, or never held

1. **D9 / 5.4 "the transport replaces `told_access_path`"**: `RpcTurnRequest` is a frozen dataclass and Plan mode is decided from the pre-wait value at `copilot_acp.py:1997`, before the reserved wait slot at `:2073`. Ordering must change, and the mapper attribute must be set.
2. **D9 `render_surface: Callable[[Literal[...]], list[str]]` (sync) that "writes `plane_surface` and the context file"**: it is called from inside the async transport in the Hub's event loop; a sync callable cannot await a DB write, and the full context is rendered by the async, DB-bound `_render_hub_agent_context` with trigger-local inputs (spec document, review, binding). Workable shape: pre-render both surfaces (notice, tool section and the full context) in the trigger, and make the callback async (`Callable[[str], Awaitable[list[str]]]`) so it can write `plane_surface` and the file. The design's sync type is wrong for today's code.
3. **D9/D12 "slice 2's statement for a run told `shim` is only the error event, which is suppressed"**: slice 2 also emits `copilot.mcp_server_unavailable` for any non-`mcp` told value, worded "this run reaches the Hub by its HTTP form instead" (`copilot_acp.py:1098-1107`). After this change that sentence is false and would sit beside D12's event. Reword it to `aw-tool`, or suppress it where D12's event was stored.
4. **D12 / task 2.6 "`run_turn` passes the request's told surface"**: Codex's `RpcTurnRequest` never carries it (`agent_trigger.py:3348-3364`), and the transport does not forward it (`codex.py:192-211`). There is no existing plumbing to reuse.
5. **D1 "every writer is best-effort inside a `try`"**: true for writers. But the Copilot standing check sits inside `decide_permission`, whose outer `except` is REJECT (`:650-657`). "Treat a raise as `None`" needs its own `try` in `_standing_rules` (Required-of-slice-2 item 1 assumed otherwise).
6. **D5 / tasks 1.8, 4.2**: still true that the pin is MCP-only (`:1200-1208`). Moving it before the branch changes `cli`-run behaviour as designed.
7. **D8 case 3 for Copilot**: case 3 does not require relative paths (only case 2 does). Copilot `edit` locations arrive absolute, so an implementation that reuses case 2's plain-relative word check for case 3 would give Copilot no args-file standing. State it in the implementation, and in a 1.6 row.
8. **D11 note "slice 1 then replaces `CLAUDE_FAMILY_RUNNERS`"**: done. The host note is per adapter and already rendered in every form, so no shim-specific work remains for it.
9. **`.claude/rules/mcp-server.md`**: task 3.4 says add one bullet. Step 1 at `:18` instructs `@mcp.tool()`, which 3.1 replaces with `@_tool()`, so step 1 must change too.

No premise about slice 1's axes, the announce-before-`mcp.run` ordering, `_decide`'s own-tools line, `_ARGUMENT_ENDS`'s parentheses, the copilot.exe environment, or the spec-turn decisions was found broken.

## 4. What each touched route returns when its callee raises

| route | today | after this change, as designed / as it will actually behave |
|---|---|---|
| `POST /api/v1/agent-actions/mcp-adapter-online` (`agent_actions.py:459`) | No `try`. A raise from `session.get`/`commit` → Starlette 500; no global handler covers it (`main.py:538,550` handle other types only); the adapter suppresses it (`mcp_server.py:2201-2202`) | Status and stamp in one commit, so a raise from `record_harness_mcp_status`/commit → 500, nothing written, no notify → a Copilot waiter times out → `absent`/`shim`. **Gap:** if `mcp_announce.notify` raises *after* the commit, the route still answers 500 though the write landed. Make `notify` total; the waiter's per-poll re-check recovers anyway |
| `POST /api/v1/agent/trigger` and `POST /messages` (via `schedule_agent` → `trigger_agent_directly`) | `turn_scheduler` catches only `TriggerAgentError` (`turn_scheduler.py:394`); anything else bubbles → 500 after the message was committed (the F338 class) | New `TriggerAgentError` 409s: pin/launcher `OSError` (now also for `cli` runs) and calls-dir `OSError`. **`latest_mcp_test` raising** (a DB error) would bubble as 500, the same as `harness_has_honoured_mcp` today but unstated. Make it total (exception → `None` → `shim`), and catch `ValueError` beside `OSError` in the calls-dir and launcher steps |
| `GET /agents/{name}/timeline` (`agents.py:800/899`), `GET /agent/{agent}/chat[/{conversation_id}]` (`agent_chat.py:726/643`, facts at `:341`) | Plain attribute reads | Two more reads; can only raise if the migration is missing (500), same as every other column |
| `GET /agents/agent-context` (`agents.py:2854`) | Renders with default `access_path="mcp"` | Unchanged; cannot reach the new `ValueError` while the default stays `"mcp"` |
| `approve_tool_call` (MCP tool, not an HTTP route) | A raise becomes a FastMCP tool error | Predicate total by design; keep `_report_decision` behaviour |
| Copilot `session/request_permission` (ACP, in-process) | Any raise in deciding → REJECT (`copilot_acp.py:650-657`; `:1834-1836`) | See §3 item 5: needs its own `try` to fall through |

## 5. Migration number

Committed head is `0114` (`0114_permission_request_workspace_verdict.py`). **`0115` is the next free number, and the
uncommitted working tree already uses it for this change** (`0115_run_harness_mcp_status_and_plane_surface.py`,
`down_revision = "0114"`, `HEAD_REVISION = "0115"` in `test_migrations.py:40`). No other open change claims `0115`.

## 6. `test_no_runner_literals.py`

The scan (`hub/tests/test_no_runner_literals.py`) fails on `== / != / in (` against `"claude"` or `"codex"`
anywhere in `hub/hub/` outside `runner_adapters/`, `migrations/` and `db/models.py`. Conflicts in this change's text:

- **D10 / task 5.2**: "the sandbox-network sentence … keyed on the runner". It must be an adapter member (for
  example `RunnerAdapter.shell_may_lack_network: ClassVar[bool]`, true on `CodexAdapter`), and
  `access_path_notice` must take that value or the adapter. Never `runner == "codex"` in `launchability.py`. The spec
  scenario is already runner-neutral (`specs/agent-capability-plane/spec.md:151`).
- **D12 / task 5.5**: "not emitted where the runner's own failure event states it: Codex `failed` … Copilot told
  `mcp`". Key it on a member (a transport ClassVar such as "reports its own MCP failure", plus
  `tests_mcp_before_first_prompt` for Copilot), not on the names.
- **D1's per-runner source table / task 2.5**: implement per transport. Claude's source arrives through
  `ParsedLine` from `map_events`, so `_flush_line` (shared with Codex `exec`) stays name-free.
- `"copilot"` comparisons are **not** caught by the scan (`_NAME` covers only claude/codex), but F473's intent says
  the same. The trigger already has `if runner == "copilot":` (`agent_trigger.py:1225`); do not add more. Gate the
  wait, the omitted notice and `render_surface` on `transport.tests_mcp_before_first_prompt`.
