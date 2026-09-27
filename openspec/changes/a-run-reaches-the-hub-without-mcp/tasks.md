## 0. Rounds

- [ ] 0.1 R2: re-derive independently, on the tree the night ORDER and slices 1–2 leave.
  - Rebase every `file:line` in `design.md`, especially the sites tonight's changes move:
    - the MCP branch of `access_path_notice`, and the `_tool_surface_lines` preamble (full-names change);
    - `_ask_operator` / `approve_tool_call` (ask-me card change);
    - `_report_decision` (run-records-calls change);
    - `posture_at_rest` (permissions-pill change).
  - Confirm slice 1's axis names (`tool_surface` / `approvals` / `plane`) and slice 2's names:
    - the normalised Copilot permission tool names (design D8, open question 6);
    - where slice 2 composes the prompt and sets `copilot.exe`'s env (D5, D9).
  - Answer open questions 1–6 in `design.md` or carry them forward. Record the result in the Round log.
- [ ] 0.2 R3: a second independent re-derivation.
  - Re-read D8's predicate against `_lex`/`_words` as they are, and try to construct a command that the predicate
    allows and that does more than one plane call. Record the attempt.
  - Re-check D1's "`connected` is final" and "untested" rows against how each runner can actually end.
  - `openspec validate a-run-reaches-the-hub-without-mcp --strict` passes.
- [ ] 0.3 Opus adversarial review of the change and of D2 (not a CLI subcommand), D8 (the args-file write under
  "Ask me", open question 7) and D11 (runs no longer told HTTP). Record it in
  `spec-queue/tracks/reviews/`, and apply or answer each finding before any APPROVED row.

## 1. Tests first — each fails on today's code

Every command runs from the repo root: `py -3.11 -m pytest <file> -q`.

- [ ] 1.1 `hub/tests/test_mcp_adapter_online.py`: grounds are the latest test (design D1).
  - Plant runs of agent `g` with explicit `started_at` values written into the rows (DEAD-ENDS 2026-09-27: patching
    `_now` does not freeze `created_at`):
    - an older `connected` and a newer `absent` → `latest_mcp_test == "absent"` and the described path is `shim`;
    - reversed → `mcp`;
    - a newer run with NULL status is skipped.
  - `described_access_path(..., latest="weird")` → `shim`.
  - Fails today: `harness_has_honoured_mcp` returns True for the first case (F340's measured one-off).
- [ ] 1.2 `hub/tests/test_runner_parsing.py`: `parse_claude_line` on a `{"type":"system","subtype":"init",
  "mcp_servers":[...]}` line sets `ParsedLine.harness_mcp_status`:
  - `connected` / `failed` for those statuses;
  - `absent` when there is no `agentweave` entry;
  - `failed` for an unknown status string;
  - `None` for a non-init line.
  Fixture shapes come from F340's table and from the raw PTY capture in
  `openspec/changes/archive/2026-09-13-an-absent-approver-is-not-named/evidence/a-hub-plain-raw-pty.txt`.
- [ ] 1.3 `hub/tests/test_mcp_call_mode.py` (new): spawn the **pinned** file (`tool_server.PIN.path()`) as
  `sys.executable <pin> --call --list`, from a `tmp_path` cwd.
  - The listed names equal the tools `test_mcp_server_stdio_surface.py` reads over stdio, minus
    `approve_tool_call`.
  - A second run, with `PYTHONPATH` pointing at a `tmp_path` directory whose `fastmcp/__init__.py` raises
    `ImportError`, still exits 0 (call mode does not import fastmcp; design D4).
- [ ] 1.4 Same file: call mode against a stdlib `http.server` stub Hub bound to `127.0.0.1:0` in a thread, with
  `HUB_URL` and `AW_RUN_TOKEN` in the child's env.
  - `create_task` with an args file → the stub saw `POST /api/v1/agent-actions/tasks`, `Authorization: Bearer
    <token>`, and the body the MCP tool sends. Stdout is exactly one JSON object `{"ok": true, ...}`, exit 0.
  - A 409 with `detail.message` → `kind: rejected`, `status: 409`, the readable detail, exit 1.
  - No `AW_RUN_TOKEN` → `kind: unbound`, exit 2, and the stub saw **no** request.
  - An unknown key → `kind: usage` naming the accepted parameters, exit 64.
  - `--token x` → usage, exit 64.
  - A UTF-16-with-BOM args file and a UTF-8-with-BOM file both work.
- [ ] 1.5 Same file, `ask_user` through call mode against the stub (design D7), with `AW_QUESTION_TIMEOUT=10`. It
  takes about 10 s; there is no `slow` marker in this repo, so do not add one:
  - the stub answers on the second poll → the answers come back in order;
  - the stub never answers → exit 0 with `answered: false`, and the stub saw `POST /questions/wait-ended`.
- [ ] 1.6 `hub/tests/test_permission_approver.py`: `_hub_own_call` table (design D8). For each row assert the
  predicate result, and assert that `_decide` and `approve_tool_call` agree with the posture. Under `operator`,
  monkeypatch `_ask_operator` and assert whether it was called.
  - **Allowed** (reason "the Hub's own tools"):
    - `aw-tool create_task .agentweave/calls/1.json` (Bash and PowerShell);
    - `aw-tool.cmd create_task .agentweave\calls\1.json` (PowerShell only);
    - `AW-TOOL list_tasks` (PowerShell only);
    - `aw-tool list_tasks`;
    - `aw-tool --list`;
    - a `Write` of `.agentweave/calls/x.json`.
  - **Fall through** (predicate `None`; under `operator` the card is asked):
    - `aw-tool create_task .agentweave/calls/1.json; rm x`, `… | cat`, `… > out`;
    - `aw-tool create_task $(echo x)`, `aw-tool create_task $env:X`, `aw-tool create_task %X%`;
    - `./aw-tool …`, `C:\x\aw-tool.cmd …`;
    - `aw-tool approve_tool_call …`, `aw-tool nosuch`;
    - `aw-tool create_task ../calls/1.json`, `… .agentweave/calls/../../x.json`, `… .agentweave/calls/1.txt`,
      `… C:\w\.agentweave\calls\1.json`;
    - a second file argument;
    - `& aw-tool …`;
    - `aw-tool.cmd …` in the Bash dialect;
    - `Aw-tool …` in Bash;
    - a `Write` of `.agentweave/calls/x.py`;
    - a `Write` whose path is a symlink under `calls/` pointing out (skip on Windows without symlink privilege).
  - Fails today: every "allowed" row under `operator` calls `_ask_operator`.
- [ ] 1.7 `hub/tests/test_tool_server_pin.py`: `PIN.launcher_dir()` (design D5):
  - it holds `aw-tool.cmd` (CRLF, naming `sys.executable` and the pinned path, `--call %*`) and `aw-tool` (sh,
    `exec … --call "$@"`);
  - both are rewritten when altered or deleted;
  - it sits under `<digest>/bin/<sha256(sys.executable)[:8]>`;
  - `prune_stale` removes it with its digest directory.
- [ ] 1.8 The trigger's env test (find the one asserting `AW_RUN_TOKEN` in the spawned env: `grep -rn
  "AW_RUN_TOKEN" hub/tests`):
  - the launcher dir is the first `PATH` entry;
  - with a base env whose key is `Path`, the same key is reused and no second `PATH` key appears;
  - `<work_dir>/.agentweave/calls/` exists after the trigger.
  - `hub/tests/test_repo_hygiene.py`: `.agentweave/calls/` is in `EXCLUDE_PATTERNS`, and in the seeded block.
- [ ] 1.9 `hub/tests/test_tool_surface_matches_server.py` + `test_launchability.py`:
  - `access_path_notice("shim")` names `aw-tool` and `.agentweave/calls/`, and contains no `AW_RUN_TOKEN`, no
    `Bearer` and no `$HUB_URL`;
  - `_tool_surface_lines(access_path="shim")` renders every operation `_operations()` renders, each as
    `` `aw-tool <tool>` `` with its `args`, plus the short-name mapping sentence and the question wait in seconds
    (pass `question_timeout=37` and assert `37`);
  - the existing agreement check runs over the shim rendering too;
  - `_tool_surface_lines(access_path="cli")` no longer exists as a run rendering. Assert that
    `described_access_path` never returns `"cli"`/`"http"` for a run.
- [ ] 1.10 `hub/tests/test_mcp_announce.py` (new), with an in-process app:
  - `wait(run_id, 1.0)` returns True at once when `mcp_adapter_online_at` is already set;
  - it returns True within ~0.1 s when the announce route is called during the wait;
  - it returns False after the timeout otherwise;
  - the announce route sets `harness_mcp_status = connected` and never downgrades it.
- [ ] 1.11 `RunFacts` carries `plane_surface` and `harness_mcp_status` from the row. Extend the test that asserts
  `outside_workspace_writes` on the agent timeline / chat run facts (`grep -rn outside_workspace_writes
  hub/tests`), using the ordering the route returns.
- [ ] 1.12 (group 6) `hub/tests/test_codex_appserver*.py`: `decide_approval` on a command approval whose command is
  `aw-tool create_task .agentweave/calls/1.json`:
  - under `posture=OPERATOR_POSTURE` → accept, not `ASK_OPERATOR`;
  - a near miss → `ASK_OPERATOR` as today.
  First read `approval_subject` for how the command arrives (a string or an argv list).
- [ ] 1.13 (group 7) `hub/tests/test_runner_commands*.py` / `test_permission_approver.py`: a non-yolo Claude
  command, with and without `mcp_command`, carries `Bash(aw-tool:*)` and `PowerShell(aw-tool:*)` in
  `--allowedTools`. A yolo command carries neither.
- [ ] 1.14 (after slice 2) Copilot transport, using slice 2's fake ACP agent (or a stub that answers `initialize`,
  `session/new` and `session/prompt`):
  - no announce within a patched 0.3 s wait → the fake receives the prompt `/mcp list` first, then a prompt whose
    text holds the shim notice and the `aw-tool` tool section; the run records `absent` + `shim`; exactly one
    `plane_surface` status event is stored, quoting the fake's `/mcp list` text;
  - the announce arrives during the wait → no `/mcp list`, the MCP notice, and `connected` + `mcp`.

## 2. The per-run record (design D1)

- [ ] 2.1 Migration (next free number at build time; read `.claude/rules/db-migrations.md`):
  - add nullable `runs.harness_mcp_status` (String(16)) and `runs.plane_surface` (String(8)), guarded for a missing
    table;
  - backfill `harness_mcp_status='connected'` where `mcp_adapter_online_at IS NOT NULL`;
  - bump the head assertions in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`;
  - add the fields to `db/models.py` `Run` with a comment in the house style.
  - Verify: `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q`.
- [ ] 2.2 `record_harness_mcp_status(session, run_id, status)` in `launchability.py` (or a new small module). It
  enforces "`connected` is final" and the unknown→`failed` mapping. The announce route (`agent_actions.py:459-483`)
  calls it and then `mcp_announce.notify(run_id)`.
- [ ] 2.3 `hub/hub/mcp_announce.py`: the per-run event registry and `wait(run_id, timeout)`, which checks the row
  first (design D9). Registry entries are removed when the wait returns or the run ends.
- [ ] 2.4 Replace `harness_has_honoured_mcp` with `latest_mcp_test`, and change `described_access_path` to take
  `latest` and to return `mcp` | `shim`. Update the call at `agent_trigger.py:1107-1112`. Tests 1.1 and 1.9 pass.
- [ ] 2.5 Claude: `ParsedLine.harness_mcp_status` and the `system`/`init` branch in `parse_claude_line`. The claude
  run loop (`agent_trigger.py` ~`:2451-2560`, `parse_line` consumer) records it through 2.2 when the run was given
  MCP. Test 1.2 passes.
- [ ] 2.6 Codex: at run end, a run given MCP that ended `completed` with no announce records `absent`. **Gate:** do
  this only if R2 settled open question 3 in favour; otherwise leave Codex runs untested and delete this row from
  design D1.
- [ ] 2.7 `RunFacts` gains the two fields at both construction sites (`agents.py:904`, `agent_chat.py:351`). Test
  1.11 passes.

## 3. The call mode (design D3, D4, D6, D7)

- [ ] 3.1 In `mcp_server.py`, before the fastmcp import:
  - `_CALL_MODE` and the `_CallRegistry` stand-in (import `sys` at the top);
  - keep the `ImportError` message for server mode;
  - re-read `.claude/rules/mcp-server.md` first, and keep `approve_tool_call` without a return annotation.
- [ ] 3.2 `call_main(argv) -> int`:
  - `--list` / `--help`;
  - bind with `inspect.signature`;
  - read the file (UTF-8 / UTF-8-BOM / UTF-16-BOM);
  - map `HubAPIError` / `HubUnreachableError` / `UnboundIdentityError` / usage errors to the D3 envelope and exit
    codes;
  - `json.dumps(result, default=str)`;
  - refuse `approve_tool_call`.
  The entry guard at the end of the file dispatches to `call_main(sys.argv[2:])` in call mode (keep it the last
  block; its comment explains why).
- [ ] 3.3 Tests 1.3–1.5 pass. Then `py -3.11 -m pytest hub/tests/test_mcp_server_stdio_surface.py
  hub/tests/test_mcp_server.py hub/tests/test_fastmcp_api_contract.py hub/tests/test_mcp_tool_schemas.py -q`
  (server mode unchanged).
- [ ] 3.4 Update `.claude/rules/mcp-server.md`, one bullet: call mode exists, is decided before the fastmcp import,
  and a new tool is callable through it automatically.

## 4. The launcher, the run's PATH and the calls directory (design D5, D14)

- [ ] 4.1 `ToolServerPin.launcher_dir()` in `tool_server.py`, and prune with the digest directory. Test 1.7 passes.
- [ ] 4.2 `agent_trigger.py`:
  - the `PATH` prepend, with a case-insensitive key, beside `AW_RUN_TOKEN` (`:1246`);
  - `.agentweave/calls/` created beside the context file (`:1160-1169`), with an `OSError` refused as the context
    write is;
  - a launcher failure refused with the tool-server reason (`:1197-1203`).
  Test 1.8 passes.
- [ ] 4.3 `repo_hygiene.EXCLUDE_PATTERNS` gains `.agentweave/calls/` with a one-line reason. Test 1.8 (hygiene half)
  passes.

## 5. What the run is told (design D9–D12)

- [ ] 5.1 **Check slice 2 first:** does `copilot.exe` itself (not only the `--additional-mcp-config` `env`) get
  `AW_RUN_TOKEN`, `HUB_URL`, `AW_WORKSPACE_DIR` and the run's `PATH`? Read slice 2's `build_launch`. If not, 5.4
  adds it.
- [ ] 5.2 `access_path_notice("shim")` (replacing the HTTP branch) and `_shim_lines` / the shim preamble in
  `_tool_surface_lines`. It takes `question_timeout` (the agent's `question_timeout_seconds` or the restated
  default 240). `_http_lines` stays, reachable only by an explicit `access_path="http"` (design D11, open question
  1). Test 1.9 passes.
- [ ] 5.3 `_render_hub_agent_context(include_tool_surface=True)`. The claude/codex paths are unchanged. Record
  `plane_surface` when the prompt is composed (the Claude/Codex path in `trigger_agent_directly`).
- [ ] 5.4 Copilot, in slice 2's adapter and transport:
  - `tests_mcp_before_first_prompt = True`;
  - the transport waits with `mcp_announce.wait` after `session/new` / `session/load`, sends `/mcp list` on
    timeout, then calls `render_surface(surface)` and sends `session/prompt`;
  - the context rendered for the custom agent file uses `include_tool_surface=False`;
  - `map_events` passes `session.mcp_servers_loaded` / `mcp_server_status_changed` entries for `agentweave` to 2.2
    (`connected` only upgrades) and stores any other status as a diagnostic;
  - `copilot.exe`'s env per 5.1.
  Test 1.14 passes.
- [ ] 5.5 The `plane_surface` status event, once per run, when a run given MCP is recorded `absent` or `failed`
  (quoting the `/mcp list` line on Copilot, bounded by `_truncate_utf8`). Test 1.14 (event half) passes.

## 6. The approver recognises the call command (design D8)

- [ ] 6.1 `_hub_own_call` in `mcp_server.py`, using `_lex`, the callable set from 3.1, and `AW_WORKSPACE_DIR`.
  `_decide` and `approve_tool_call`'s operator branch call it in place of their `mcp__agentweave__` lines. Test 1.6
  passes.
- [ ] 6.2 Slice 2's ACP permission handler calls `_hub_own_call` before `_decide` or the card, in every posture,
  on its normalised `(tool_name, tool_input)`.
- [ ] 6.3 (severable) Codex's `decide_approval`: the command-approval branch accepts on `_hub_own_call` before the
  posture branches (imported from `hub.mcp_server`; the Hub side may import it, as `agents.py:1016` already does).
  Test 1.12 passes. If cut, drop 1.12 and D8's Codex bullet.

## 7. Claude parity (severable; design D13)

- [ ] 7.1 `_build_claude_command`: when not yolo, `--allowedTools` carries `Bash(aw-tool:*)` and
  `PowerShell(aw-tool:*)` in every case. When `mcp_command` is set they are added to the existing
  `mcp__agentweave__*` value: read how `--allowedTools` takes several values, one argument or repeated. Test 1.13
  passes.
- [ ] 7.2 If group 7 is cut, delete *"A Claude run pre-allows the Hub's call command"* from
  `specs/agent-run-sandboxing/spec.md` and re-run `openspec validate a-run-reaches-the-hub-without-mcp --strict`.

## 8. Gates (what CI runs)

- [ ] 8.1 `ruff check src/ hub/ tests/`
- [ ] 8.2 `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`
- [ ] 8.3 `mypy src/` (unchanged by this change, but it is CI's)
- [ ] 8.4 `py -3.11 -m pytest hub/tests/ -q` and `py -3.11 -m pytest tests/ -q`, all green. Record the counts.

## 9. Drive on the trial Hub `:8010`

Start it per CLAUDE.md and `.claude/reference/hubs.md`: from `hub/`, `py -3.11 -m uvicorn hub.main:app --port 8010`
with `DATABASE_URL` naming the trial profile. Never `:8000`. Use a throwaway fixture project under
`testbed/scratch/`. Copilot is on the **Free plan: Auto model only, a small monthly allowance, so keep every
prompt one tiny sentence and the turns to the ones listed**. Claude turns are on Haiku. Record each run id, and
read `runs.harness_mcp_status`, `runs.plane_surface`, the run's events and the tasks it created with `mode=ro`
SQLite reads of the trial profile's database.

- [ ] 9.1 Start the Hub and confirm, from its startup log, the database it serves and the pinned tool-server path.
  List `<digest>/bin/<exe>/` and confirm both launchers. From a PowerShell and a Git Bash with that dir on `PATH`,
  `aw-tool --list` prints the tool list with no token set, and `aw-tool list_tasks` prints `kind: unbound`.
  (No model call.)
- [ ] 9.2 **Copilot, MCP permitted** (1 prompt): *"Create an AgentWeave task titled S3-MCP, then stop."* Expect
  `connected` + `mcp`, the task created by an `agentweave-create_task` tool call, and no `plane_surface` status
  event. Record the time from `session/new` returning to the announce (open question 2).
- [ ] 9.3 **Copilot, MCP blocked locally** (1 prompt). Add `--disable-mcp-server agentweave` to the Copilot
  runner's flags (VERIFIED today: the server is never started, and `/mcp list` says `agentweave (disabled)`).
  Same prompt with `S3-SHIM`. Expect:
  - `absent` + `shim`;
  - one status event quoting `agentweave (disabled)`;
  - the model wrote `.agentweave/calls/*.json` and ran `aw-tool create_task …` in `powershell`;
  - the permission decisions for both were allowed by the Hub's own rule, with no operator card;
  - the task's `created_by_run_id` is the run;
  - `grep -c aw_run_` over the run's stored events is **0**.
  If Copilot never asks (it auto-allowed the command), record that instead: it answers D15's INFERRED row.
- [ ] 9.4 **Copilot, blocked, "Ask me" posture** (1 prompt): the same with `S3-ASK`. Expect **no** permission
  card for the args-file write or the `aw-tool` call. Any card that does open is answered by the driver, and it is
  a defect to record.
- [ ] 9.5 **Not latched** (1 prompt): remove the runner flag, then *"Create a task titled S3-BACK."* Expect
  `connected` + `mcp` again. This is F340 in both directions on one agent.
- [ ] 9.6 **Resume.** 9.5 must be the second turn of 9.3's conversation, so it resumes through `session/load`.
  Record whether the announce arrived after `session/load` (design D9 "Resume", INFERRED). If it did not, file a
  finding and keep the change: the shim still works.
- [ ] 9.7 **Claude, F340** (Haiku, 2 turns). A Claude agent whose runner flags carry `--settings
  '{"deniedMcpServers":[{"serverName":"agentweave"}]}'`. F340 measured its `init` omitting the server; F299 says
  the run then dies at its first approval-needing call, so the prompt needs none: *"Reply with the word ok."*
  Expect `absent`. The second turn, *"Reply ok."*, reads the shim notice in its prompt (read the stored prompt).
- [ ] 9.8 **Claude, F301** (group 7; Haiku, 1 turn). A Claude agent with `config.hub_client = "cli"`: *"Create an
  AgentWeave task titled S3-F301, then stop."* Expect the task created through `aw-tool` with no denial.
  - If it holds, F301 is closed for Claude.
  - If the harness refuses the command, record the refusal verbatim, F301 stays open for Claude, and group 7 is
    reported rather than reverted.
- [ ] 9.9 Append the outcome to `scripts/drive/FINDINGS.md`: the F340 status line (fixed), F301 (fixed for Copilot;
  Claude per 9.8), and F299 (answered for Copilot; open for Claude). File any new defect as a new finding.

## 10. Archive

- [ ] 10.1 The human-only checks in `test-guide.md` are done by the operator on the work PC, or explicitly waived by
  them.
- [ ] 10.2 `openspec validate a-run-reaches-the-hub-without-mcp --strict`, then the `openspec-archive-change` skill.
  Sync the four deltas. Commit and push per CLAUDE.md, staging paths explicitly.
