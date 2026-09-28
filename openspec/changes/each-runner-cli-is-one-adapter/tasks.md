## 0. Rounds

- [x] 0.1 R2: build on the tree the 2026-09-27 night ORDER leaves. Start from the code, not this design. Grep `hub/hub` for every runner-name comparison, and for `catalog_provider_for_runner`, `resolve_access_path`, `CLAUDE_FAMILY_RUNNERS`, `posture_at_rest`, `uses_app_server`, `SUPPORTED_CLIS` and `RUNNER_CLI`. Rebuild design D3's member table and D5's registry table from what you find, and rebase every line marked *(re-verify in R2)*. Then answer design open questions 1–3. Record the result in design.md's round log
  - **Done 2026-09-28** on `ef55e6f` (only 5 of the ORDER's 28 changes had landed; each unbuilt-dependency site is marked *(rebase at IMPL)*): 10 corrections, among them the new `api/v1/model_catalog.py:26` literal, `uses_app_server` deleted, `_claude_mcp_args` narrowed to `:250-262`, label members taking `subject`, `RpcTurnRequest` gaining `extra_flags`/`restrict_spec_writes` (the Codex app-server spec-turn gap), and D16 rebuilt against slices 2-5; open questions 1-3 answered (3 is F301)
- [ ] 0.2 R3: a second independent re-derivation. For each of D4's five rows, trace the post-night trigger path and confirm what is actually given (server, approver flag or RPC answering, and default posture) against D4's claimed values. Confirm the import graph in D1 has no cycle by reading each module's imports. `openspec validate each-runner-cli-is-one-adapter --strict` passes
- [ ] 0.3 Opus adversarial review of the change and of D1–D16 (the operator's standing step before an APPROVED row). The question: can anything about a Claude or Codex run differ after this change, and does any golden case miss that difference? Record it in `spec-queue/tracks/reviews/`

## 1. Tests first — each fails on today's code

Capture the goldens in 1.1–1.4 from the code **before any edit in group 2**. Do not `git stash` or `git checkout --` in the shared tree (DEAD-ENDS 2026-09-27). Write each capture script to a file (DEAD-ENDS 2026-09-27: long heredocs) and run it with `py -3.11`.

- [ ] 1.1 `hub/tests/fixtures/runner_adapters/capture_goldens.py`: import today's `hub.runner_commands.build_command`, `hub.runner_parsing` and `hub.worker`/`hub.conversation_titles` builders. Write `argv_golden.json`, the design's "Golden argv" cross product, about 100 cases, context path written as `<CTX>`. Also a case for each runner with `extra_flags=["--no-app-server"]`, recording today's `build_command` output (the trigger strips it before this). Commit the script and the JSON. Verify: `py -3.11 hub/tests/fixtures/runner_adapters/capture_goldens.py && py -3.11 -c "import json;print(len(json.load(open('hub/tests/fixtures/runner_adapters/argv_golden.json'))))"` prints ≥ 90
- [ ] 1.2 `hub/tests/test_runner_adapters_argv.py`: for every golden case, `get_adapter(runner).transport(flags)` builds it (stream transport; Codex `exec` via `--no-app-server`), and `build_launch(LaunchRequest(...))` equals the golden byte for byte. Also check `runner_adapters.build_command(...)` with the same arguments. FAILS today (`ModuleNotFoundError: hub.runner_adapters`). Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_argv.py -q`
- [ ] 1.3 Same capture script, and `hub/tests/test_runner_adapters_events.py`. Copy the JSONL lines inlined in `test_runner_parsing.py` into `fixtures/runner_adapters/claude_stream.jsonl` and `codex_exec.jsonl`, in their file order. Capture today's `parse_claude_line` / `parse_codex_line(model="gpt-5.5")` output per line into `stream_events_golden.json` (kind, content, payload, usage and accounting as dicts, session_id). Capture worker and title argv for each CLI × {model, None} × {schema path, None} into `one_shot_golden.json`. The test asserts `transport.map_events` and `adapter.one_shot` reproduce both goldens exactly. FAILS today (no module). Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_events.py -q`
- [ ] 1.4 `hub/tests/test_runner_adapters_rpc.py`. The capture half: drive today's `_execute_codex_appserver_run` with `hub.api.v1.agent_trigger.codex_run_turn` patched by a recorder, as `test_agent_trigger.py:111`'s `_fake_run_turn` does. Cover `permission_mode` ∈ {None, acceptEdits, workspace, manual, bypassPermissions} × `mcp_command` ∈ {None, set}. Record the kwargs, with callables as their parameter names, into `rpc_kwargs_golden.json`. The test half: `CodexAppServerTransport.run_turn(RpcTurnRequest(...), RpcCallbacks(...))`, with `hub.codex_appserver.run_turn` patched, passes the same kwargs. FAILS today (no module). Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_rpc.py -q`
- [ ] 1.5 `hub/tests/test_runner_adapters_conformance.py`. Each check fails today on the import:
  - (a) `tuple(ADAPTERS) == RUNNER_CLIS == tuple(CATALOG)`, and equal to the set parsed from `ck_runners_cli`'s `sqltext` (`db/models.py:340`)
  - (b) `GET /runners/launchability-by-provider` returns keys in `RUNNER_CLIS` order: `["claude", "codex"]`, the order the route emits
  - (c) the union of `write_tool_kinds` is `workspace_writes.WRITE_TOOLS`, no tool name is in two adapters, and `written_paths` extracts a path for a well-formed input of each kind
  - (d) `instruction_channel` agrees with argv: the flag is present iff the channel is not `None` and the context file exists; `CodexAppServerTransport.instruction_channel is None` (F325, pinned)
  - (e) `context_window_source` holds against each transport's recorded usage payloads (design D13)
  - (f) `launchability` does not raise, with `shutil.which` → `None` and with a pinned non-file `cli` override
  - (g) every adapter and transport instantiates (ABC completeness)
  - (h) the sentinel strip set equals `codex_appserver.TRANSPORT_SENTINELS`
  - (i) (R2) with `hub.codex_appserver.run_turn` patched by a recorder, `CodexAppServerTransport.run_turn` given `extra_flags=["--x"]` and `restrict_spec_writes=True` passes neither to it: the kwargs equal those for `[]`/`False` (design D11, the declared Codex app-server gap)
  - (j) (R2) `permission_card_label(method, subject)` and `refusal_label(method, subject)` on `CodexAppServerTransport` ignore `subject`: for each method in `_CODEX_APPROVAL_LABELS` and `codex_appserver._REFUSAL_LABELS`, two different subjects give today's label

  Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_conformance.py -q`
- [ ] 1.6 `hub/tests/test_access_axes.py`: `resolve_access_axes` returns design D4's five rows exactly. `ClaudeAdapter.posture_at_rest` gives `workspace`, `acceptEdits` and `bypassPermissions` for (approvals ≠ none), (approvals = none) and (yolo). FAILS today (no function). Verify: `cd hub && py -3.11 -m pytest tests/test_access_axes.py -q`
- [ ] 1.7 Before group 2, on the trial Hub started as in 5.1 **from pre-change code**, capture `GET …/runners/launchability-by-provider`, `GET …/agents/launchability` and, for a `codex` runner with no flags and one with `["--no-app-server"]` each bound to an agent, `collaboration_ready`/`collaboration_reason`, into `hub/tests/fixtures/runner_adapters/drive_before.json` (ids and timestamps removed). This is the drive's baseline, not a test. Verify: the file exists and names both providers

## 2. The adapter package

- [ ] 2.1 `hub/hub/runner_adapters/base.py`, the ABCs and value types of design D1/D3 with the contracts as docstrings. Add `probe_binary` (design D14) and `one_shot.py` (design D8). `probe_binary` calls `shutil.which` through the module attribute (design D6). Test `test_runner_adapters_imports.py`: importing `hub.runner_adapters` in a fresh interpreter does not import `hub.db.engine`, `hub.worker`, `hub.launchability` or `hub.api` (`sys.modules` check). Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_imports.py -q`
- [ ] 2.2 `claude.py`: `ClaudeAdapter`, `ClaudeStreamTransport` delegating to `runner_commands._build_claude_command` and `parse_claude_line`. `_build_claude_command` takes `approvals` in place of deriving the default from `mcp_command` (design D4, "Consumers"), and its MCP fragment is extracted to `_claude_mcp_args` (design D1). Move the one-shot builders and `parse_claude_envelope` here. Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_argv.py tests/test_runner_adapters_events.py -q -k claude`
- [ ] 2.3 `codex.py`: `CodexAdapter`, `CodexExecTransport`, `CodexAppServerTransport` (`posture_for` = `_codex_posture` moved; `permission_card_label(method, subject)`, `refusal_label(method, subject)`, `inject_mcp`, `run_turn`; and `workspace_verdict` if `an-ask-me-card-says-what-workspace-only-would-decide` has landed, design D3). `CodexAdapter.transport` takes `uses_app_server`'s body; delete `codex_appserver.uses_app_server` (R2, design D5). `CODEX_MCP_ENV_NAMES` is declared once in `codex_appserver.py`, read by both `_build_codex_command` and `run_turn`, and referenced by `CodexAdapter.mcp_env_names` (design D12). Extract `_codex_exec_mcp_args` (design D1). Move the one-shot builders and `parse_codex_envelope` here. Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_argv.py tests/test_runner_adapters_events.py tests/test_runner_adapters_rpc.py -q`
- [ ] 2.4 `__init__.py`: `ADAPTERS`, `get_adapter`, `build_command` (design D6) and `resolve_access_axes` (design D4). Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_conformance.py tests/test_access_axes.py -q`

## 3. Callers move onto the adapter

- [ ] 3.1 `runner_commands.py`: delete `build_command`, `SUPPORTED_RUNNERS`, `_CATALOG_PROVIDER_BY_RUNNER`, `catalog_provider_for_runner`, and the `claude_proxy`/`native` arm. Fold the night's `posture_at_rest`/`CLAUDE_FAMILY_RUNNERS` into the adapters: design D3's `decide_posture`, `mcp_tool_prefix` and `host_tool_note` rows and D5 name the sites each unbuilt change will leave (R2); re-read them on the tree as it stands at IMPL, since at R2 neither existed. Update the test imports (`grep -l "from hub.runner_commands import" hub/tests` → import `build_command` from `hub.runner_adapters`). Delete `test_runner_parsing.py`'s `claude_proxy`/`native` case and `test_model_catalog.py`'s `SUPPORTED_RUNNERS` assertions, replacing them with 1.5(a). Verify: `cd hub && py -3.11 -m pytest tests/test_runner_parsing.py tests/test_model_catalog.py tests/test_runner_command_overrides.py tests/test_runner_command_env.py tests/test_spec_authoring_restriction.py tests/test_permission_approver.py -q`
- [ ] 3.2 `launchability.py`:
  - delete `MCP_INJECTABLE_RUNNERS` and `resolve_access_path`, and its `kimi` test (`test_launchability.py:537`)
  - rename `RUNNER_CLI` to `LEGACY_RUNNER_CLI`, keeping every row including `copilot` (design D5)
  - `probe_agent` goes adapter-first (design D14)
  - `resolve_agent_env` ends with `guard_env` (design D10)

  Verify: `cd hub && py -3.11 -m pytest tests/test_launchability.py tests/test_inbound_queue.py -q`
- [ ] 3.3 `api/v1/agent_trigger.py`, the trigger:
  - the 501 gate becomes `get_adapter`
  - `resolve_access_axes` replaces `resolve_access_path`; `mcp_command` iff `tool_surface == "mcp"`; `described_access_path(axes.plane, …)`
  - the sentinel strip is the union over adapters
  - `cmd` is built only for a stream transport, still through the module-level name `build_command`, so the five capture patches keep working (design D6)
  - `render_control_config(adapter.catalog_provider, …)`

  Verify: `cd hub && py -3.11 -m pytest tests/test_agent_trigger.py tests/test_agent_trigger_overrides.py tests/test_agent_default_permission_mode.py tests/test_agent_tool_surface_phase7.py -q`
- [ ] 3.4 `agent_trigger.py`, the executors (design D9):
  - `_execute_run` reads `spawn_kind`, `map_events` and `usage_from`
  - `_execute_codex_appserver_run` becomes `_execute_rpc_run`; `runner="codex"` literals become `adapter.name`
  - the label helpers go through the transport, and `_codex_decision_timeout` becomes `_decision_timeout`
  - move the 17 `hub.api.v1.agent_trigger.codex_run_turn` patch targets to `hub.codex_appserver.run_turn`, and the three `_codex_posture`/`_codex_decision_timeout` imports

  Verify: `cd hub && py -3.11 -m pytest tests/test_agent_trigger.py tests/test_a_turn_says_how_it_ended.py tests/test_failed_run_returns_input.py tests/test_outside_write_record.py tests/test_codex_posture_ordering.py tests/test_agent_waiting_settings.py tests/test_codex_appserver_run_turn.py -q`
- [ ] 3.5 `worker.py` and `conversation_titles.py`: the one-shot calls go through the adapter (design D8). Delete `SUPPORTED_CLIS` and `_SUPPORTED_CLIS`, and re-export the moved names from `worker`. Change `test_title_generation.py:217` to `get_adapter("kimi") is None`. Verify: `cd hub && py -3.11 -m pytest tests/test_worker.py tests/test_worker_at_mention.py tests/test_title_generation.py -q`
- [ ] 3.6 `api/v1/agents.py`: the collaboration verdict comes from `adapter.collaboration`. `_display_model` takes `adapter.display_name` for adapter strings and keeps the legacy rows for the rest (design D5). The night's tool-prefix rendering reads `adapter.mcp_tool_prefix` and `host_tool_note`. `api/v1/runners.py:116-118` iterates `ADAPTERS`. (R2) `api/v1/model_catalog.py:24-29` calls a new `model_catalog.catalog_source(p.provider)` in place of `p.provider == "codex"` (design D2); the `GET /model-catalog` response is unchanged (`tests/test_codex_models_from_the_cli_cache.py`). Verify: `cd hub && py -3.11 -m pytest tests/test_launchability.py tests/test_tool_surface_matches_server.py tests/test_agent_facing_text.py tests/test_codex_models_from_the_cli_cache.py -q`

## 4. Whole-suite proof

- [ ] 4.1 Every group-1 test passes against the unchanged goldens. Verify: `cd hub && py -3.11 -m pytest tests/test_runner_adapters_argv.py tests/test_runner_adapters_events.py tests/test_runner_adapters_rpc.py tests/test_runner_adapters_conformance.py tests/test_access_axes.py tests/test_runner_adapters_imports.py -q` and `git diff --stat -- hub/tests/fixtures/runner_adapters/` shows no golden changed since 1.1–1.4
- [ ] 4.2 The Hub suite, under the CI condition that `claude` is not on PATH (memory: local suite green because `claude` is on PATH). Verify: `py -3.11 -m pytest hub/tests/ -q -p no:cacheprovider`, then the same with `claude`'s directory removed from `PATH` for the process
- [ ] 4.3 CI's lint over CI's paths (CLAUDE.md, "Code quality"). Verify: `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`
- [ ] 4.4 `hub/tests/test_no_runner_literals.py`: no `== "claude"`, `== "codex"`, `in ("claude"` or `!= "codex"` in `hub/hub/**/*.py` outside `runner_adapters/`, `migrations/`, `db/models.py`, and `model_catalog.py`'s `CATALOG` keys. Verify: `cd hub && py -3.11 -m pytest tests/test_no_runner_literals.py -q`

## 5. Drive

Slice 1 has no Copilot, so the Copilot Free plan is **not** spent here. The drive proves that Claude is unchanged. Real turns bind **Haiku** (memory: cheap models for test drives). Codex is undrivable, so no Codex run is started.

- [ ] 5.1 Start the trial Hub **from `hub/`, from source** (`.claude/reference/hubs.md`): `cd hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/trial/agentweave.db" py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1`. Read the startup line naming the database. **Never touch `:8000`**
- [ ] 5.2 On `proj-d85a82bf4216`, create a `claude` agent on `claude-haiku-4-5-20251001` with the default posture. Send one tiny turn that makes the agent call `send_message` to the operator and write one file inside its worktree. Record, verbatim:
  - the `run_started` lifecycle payload
  - whether `mcp_adapter_online_at` is set on the run
  - the posture pill's value
  - the timeline's tool events
  - the outside-write record (`[]`)
- [ ] 5.3 Same agent with its posture set to "Ask me". One turn asking for one write. Confirm the ask-me card appears, then allow it. Then set `hub_client: "cli"` through `/session/sync` for that agent. One turn: confirm the notice is the HTTP form and the default posture is `acceptEdits` (design D4 row 2)
- [ ] 5.4 `GET /api/v1/projects/proj-d85a82bf4216/runners/launchability-by-provider` and `GET …/agents/launchability`. Record both. Their key order and verdicts equal `drive_before.json` (task 1.7)
- [ ] 5.5 Codex without a run: create a `codex` runner with no flags and one with `["--no-app-server"]`, bind an agent to each, and record `collaboration_ready`/`collaboration_reason`. Both are unchanged against `drive_before.json` (task 1.7)

## 6. Archive

- [ ] 6.1 Sync the deltas (`openspec-sync-specs`): `runner-registry` gains *Each supported runner CLI is served by exactly one runner adapter*; `agent-capability-plane` gains *A run's tool surface, approval channel and plane access are decided separately*. `openspec validate --strict` passes on the synced specs
- [ ] 6.2 Record in `scripts/drive/FINDINGS.md`: F393's remaining note (the Hub registries are now the adapter table; `LEGACY_RUNNER_CLI`'s `copilot` row goes in slice 2). Record any finding R2 filed from open questions 3–4. R2 leaves two: (a) append to F301 that `get_agents_launchability` reports `collaboration_ready: True` for a `claude` agent with `hub_client: "cli"` (`agents.py:264-265`), the runs F301 measured unable to reach the Hub (design, open question 3); (b) file a new finding: a specification turn on Codex app-server keeps its write tools, because neither `restrict_spec_writes` nor the runner's flags reach `codex_appserver.run_turn` (design D11; derived from code, not driven)
- [ ] 6.3 Archive with `openspec-archive-change`, then commit and push (CLAUDE.md: commit each completed checkpoint; stage paths explicitly)
