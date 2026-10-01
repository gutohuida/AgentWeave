## 0. Rounds

- [x] 0.1 R2: re-derive independently, on the tree the night ORDER and slices 1–2 leave.
  - Rebase every `file:line` in `design.md`, especially the sites tonight's changes move:
    - the MCP branch of `access_path_notice`, and the `_tool_surface_lines` preamble (full-names change);
    - `_ask_operator` / `approve_tool_call` (ask-me card change);
    - `_report_decision` (run-records-calls change);
    - `posture_at_rest` (permissions-pill change).
  - Confirm slice 1's axis names (`tool_surface` / `approvals` / `plane`) and slice 2's names:
    - the normalised Copilot permission tool names (design D8, open question 6);
    - where slice 2 composes the prompt and sets `copilot.exe`'s env (D5, D9).
  - Answer open questions 1–6 in `design.md` or carry them forward. Record the result in the Round log.
  - **Done 2026-09-28** on master `ef55e6f`. Only 5 of the night ORDER's changes had landed, and neither slice
    had, so the sites those changes move are marked "rebase at IMPL". Result:
    - 14 corrections, among them: the D5 pin is only made for MCP runs; the D8 deny-list missed `()`; Codex
      approvals are wrapped, so group 6 cannot fire (recommended cut); call mode must never announce; D9 is
      retargeted onto slice 2's `per_turn`;
    - OQ 1/3/4/6 answered, 2/5/7 carried;
    - 7 cross-slice gaps listed.
- [x] 0.2 R3: a second independent re-derivation.
  - Re-read D8's predicate against `_lex`/`_words` as they are, and try to construct a command that the predicate
    allows and that does more than one plane call. Record the attempt.
  - Re-check D1's "`connected` is final" and "untested" rows against how each runner can actually end.
  - `openspec validate a-run-reaches-the-hub-without-mcp --strict` passes.
  - **Done 2026-09-28** on master `fc33ff9`. Result:
    - 20 attacks, none giving more than one plane call. Three holes around the allow-list were closed: case 2 for
      non-shell tools, the path-less edit, and `PYTHON*` poisoning (now `-I`). The PowerShell `-x.y` split was also
      closed;
    - "`connected` is final" was replaced by a source precedence (the announce precedes `mcp.run`);
    - F340 is not closed for Codex `exec`;
    - D12's wording was false for runs told `mcp`;
    - group 6 cut; R2's Codex `*TOKEN*` premise was refuted.
- [x] 0.3 Opus adversarial review of the change and of D2 (not a CLI subcommand), D8 (the args-file write under
  "Ask me", open question 7) and D11 (runs no longer told HTTP). Record it in
  `spec-queue/tracks/reviews/`, and apply or answer each finding before any APPROVED row.
  - **Done 2026-09-28.** Opus review ghcp-s3-2026-09-28: APPROVE WITH FIXES → 12 applied, 1 answered (13
    findings; both contract conflicts resolved too). Mapping in `design.md`'s Round log, *Review fixes,
    2026-09-28*. Open question 7 now carries four options for the operator (design, *Opus review … on open
    question 7*); it is the operator's decision before any APPROVED row.
  - **Operator decisions, 2026-09-28.** Open question 7: (a) now, (c) detect-and-degrade as a follow-up change,
    raised only if the work-PC drive (task 10.1, test guide human-only step 8) records persistent shell sessions in
    use; (b) and (d) rejected. Open question 11: (c), a full-access spec turn's non-`edit` requests judged as
    `workspace`.

- [x] 0.4 IMPL verification round, 2026-10-01, against master `eec4085` (slices 1 and 2 archived; the 09-27
  ORDER changes this design names archived except `a-run-records-that-its-calls-were-allowed`). An independent Opus
  comparison of `design.md`/`tasks.md` against the tree, written to `verification-2026-10-01.md` beside this file
  (moved references, per-task verdicts, broken premises, what each touched route returns when its callee raises).
  Applied as the tasks are built; each task line names what it took from it.
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
  - `None` for an unknown status string such as `pending` (R3: not a report; design D1);
  - `None` for a non-init line.
  Fixture shapes come from F340's table and from the raw PTY capture in
  `openspec/changes/archive/2026-09-13-an-absent-approver-is-not-named/evidence/a-hub-plain-raw-pty.txt`.
- [x] 1.3 `hub/tests/test_mcp_call_mode.py` (new): spawn the **pinned** file (`tool_server.PIN.path()`) as
  `sys.executable <pin> --call --list`, from a `tmp_path` cwd.
  - The listed names equal the tools `test_mcp_server_stdio_surface.py` reads over stdio, minus
    `approve_tool_call`.
  - A second run, with `PYTHONPATH` pointing at a `tmp_path` directory whose `fastmcp/__init__.py` raises
    `ImportError`, still exits 0 (call mode does not import fastmcp; design D4). Spawn this one **without** `-I`:
    isolated mode ignores `PYTHONPATH`, so it would pass whether or not call mode imports fastmcp (R3).
  - A third run through the launcher (`-I -S`) with `PYTHONPATH` naming a directory whose `json.py` raises still
    exits 0 (design D5, R3).
  - (review note 12) `mcp_server._CALLABLE_TOOLS`'s names, imported in-process, equal the listed names, and equal
    the fastmcp-registered set minus `approve_tool_call` (design D3, *How the set is known in both modes*).
  - **Done 2026-10-01**: `hub/tests/test_mcp_call_mode.py`, spawning a `ToolServerPin` copy under `tmp_path` (not the
    Hub user's pin root). `--list` names equal the stdio-served set minus `approve_tool_call`; `_CALLABLE_TOOLS`
    in-process equals it too; a poisoned `fastmcp` on `PYTHONPATH`, spawned without `-I`, still exits 0; a
    poisoned `json.py` under `-I -S` exits 0. The launcher spawn of that last case is added with 1.7, once the
    launcher exists. Red first (`--list` unknown). Mutation: forcing the fastmcp import in call mode fails it.
- [x] 1.4 Same file: call mode against a stdlib `http.server` stub Hub bound to `127.0.0.1:0` in a thread, with
  `HUB_URL` and `AW_RUN_TOKEN` in the child's env.
  - `create_task` with an args file → the stub saw `POST /api/v1/agent-actions/tasks`, `Authorization: Bearer
    <token>`, and the body the MCP tool sends. Stdout is exactly one JSON object `{"ok": true, ...}`, exit 0.
  - A 409 with `detail.message` → `kind: rejected`, `status: 409`, the readable detail, exit 1.
  - No `AW_RUN_TOKEN` → `kind: unbound`, exit 2, and the stub saw **no** request.
  - An unknown key → `kind: usage` naming the accepted parameters, exit 64.
  - `--token x` → usage, exit 64.
  - Across every case above, the stub saw **no** `POST /api/v1/agent-actions/mcp-adapter-online`. Call mode
    never announces (design D4).
  - A stub answering `200` with a non-JSON body → `kind: internal`, exit 70, and no traceback on stdout or
    stderr.
  - A UTF-16-with-BOM args file and a UTF-8-with-BOM file both work.
  - (review fix 3) An args file holding an em dash as cp1252 byte `0x97` with no BOM (what a bare 5.1
    `Set-Content` writes): on Windows it decodes through the ANSI code page and the stub sees the em dash; with
    `locale.getencoding` patched to a codec that cannot decode it (and on POSIX), `kind: usage` whose detail names
    `-Encoding utf8`, and the stub saw no request (design D3).
  - (review fix 8) The shim's calls-root check, each with the stub seeing **no** request and `kind: usage`:
    - an args file outside `<AW_WORKSPACE_DIR>/.agentweave/calls/` (a `tmp_path` file, and a `..` path);
    - an args file inside, with `AW_WORKSPACE_DIR` unset;
    - the child's cwd a subdirectory of the workspace, with a relative `.agentweave/calls/1.json` that therefore
      resolves under the subdirectory (the drifted-`cd` case);
    - `.agentweave/calls` a directory junction (Windows, `New-Item -ItemType Junction`, no privilege needed) or a
      symlink (POSIX) to another workspace directory holding the file.
    The same file inside a real calls directory works (design D3, *Where the file may be*).
  - **Done 2026-10-01** (same file): the stub Hub is a `ThreadingHTTPServer` in a thread. The `create_task` body is
    compared against what the MCP function sends in-process (its `_hub_request` captured), not restated. Every
    usage case asserts the stub saw no request; the cp1252 `0x97` case runs where the code page is cp1252, and
    the undecodable case runs `call_main` in-process with `locale.getencoding` patched to `ascii`. The calls-root
    rows (outside, `..`, no `AW_WORKSPACE_DIR`, drifted cwd, a junction made with `mklink /J`) all fail closed.
    Mutation: `call_main` announcing fails the never-announces row.
- [x] 1.5 Same file, `ask_user` through call mode against the stub (design D7), with `AW_QUESTION_TIMEOUT=10`. It
  takes about 10 s; there is no `slow` marker in this repo, so do not add one:
  - the stub answers on the second poll → the answers come back in order;
  - the stub never answers → exit 0 with `answered: false`, and the stub saw `POST /questions/wait-ended`.
  - **Done 2026-10-01** (same file): `AW_QUESTION_TIMEOUT=10`; answered on the second poll in order; unanswered
    ends `answered: false` with `POST /questions/wait-ended` seen.
- [x] 1.6 `hub/tests/test_permission_approver.py`: `_hub_own_call` table (design D8). For each row assert the
  predicate result, and assert that `_decide` and `approve_tool_call` agree with the posture. Under `operator`,
  monkeypatch `_ask_operator` and assert whether it was called.
  - **Allowed** (reason "the Hub's own tools"):
    - `aw-tool create_task .agentweave/calls/1.json` (Bash and PowerShell);
    - `aw-tool.cmd create_task .agentweave\calls\1.json` (PowerShell only);
    - `AW-TOOL list_tasks` (PowerShell only);
    - `aw-tool list_tasks`;
    - `aw-tool --list`;
    - a `Write` of `.agentweave/calls/x.json`, by `file_path` and by `path` (slice 2's shape), and an `Edit` of it;
    - the same allows with `AW_WORKSPACE_DIR` unset and `workspace=<tmp>` passed (the callers that run in the Hub
      process).
  - `_HUB_OWN_WRITE_TOOLS == workspace_writes.CLAUDE_WRITE_TOOLS` (the restated constant).
  - **Fall through** (predicate `None`; under `operator` the card is asked):
    - `aw-tool create_task .agentweave/calls/1.json; rm x`, `… | cat`, `… > out`;
    - in PowerShell (design D8's character allow-list):
      - `aw-tool list_tasks (.agentweave/calls/1.json)`, which today lexes to exactly the three accepted words;
      - `aw-tool create_task {x}`;
      - `aw-tool create_task .agentweave/calls/1.json,x`;
      - `aw-tool 'create_task' .agentweave/calls/1.json`;
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
  - Review rows (review fix 1, the calls-root rule), all **fall through**, and **not skipped on Windows**
    (a directory junction needs no privilege):
    - `.agentweave/calls` a directory junction to `.claude`, then a `Write` of `.agentweave/calls/settings.json` by
      `file_path` and by `path`, and `aw-tool create_task .agentweave/calls/settings.json`: under `operator` the card
      is asked;
    - `.agentweave` itself a junction to another directory holding `calls/`: the same;
    - the plain allowed rows with the workspace **itself** reached through a junction (its realpath is the root),
      which stay **allowed**.
  - R3 rows, all **fall through**:
    - `mcp__other__run` with `{"command": "aw-tool list_tasks"}`, and a tool named `Shell` with the same input
      (case 2 is `Bash`/`PowerShell` only);
    - `aw-tool –list` (U+2013) and `aw-tool list_tasks .agentweave/calls/ａ.json` (fullwidth `ａ`)
      (ASCII set);
    - `aw-tool create_task -x.agentweave/calls/1.json` in PowerShell, with `-x.agentweave` a junction/symlink to
      `.agentweave` where the platform allows (leading `-`);
    - a `Write` with no path key, and `("Write", {"path": ""})`;
    - `os.path.realpath` patched to raise `OSError` → `None`, and neither `_decide` nor `approve_tool_call` raises.
  - R3 row, **allowed**: `aw-tool create_task .AgentWeave/Calls/1.json` on Windows (case-insensitive paths,
    compared with `normcase`).
  - Fails today: every "allowed" row under `operator` calls `_ask_operator`.
  - **Done 2026-10-01**, in its own file, `hub/tests/test_hub_own_call.py` (the table is long, so it is kept out of
    `test_permission_approver.py`): every row of the task, red first. Allowed rows assert the predicate, `_decide`
    and `approve_tool_call` under the operator posture with no card asked; fall-through rows assert one card
    asked. Copilot's absolute `edit` paths are allowed rows by `path` (verification finding 7: case 3 does not
    reuse case 2's relative-path rule). Junction rows run on Windows via `mklink /J` (no privilege); the
    file-symlink row skips without the symlink privilege. Mutations: dropping the character allow-list fails 6;
    widening case 2 to tools outside `_TOOL_DIALECTS` fails 3. Dropping the root-is-itself check fails nothing,
    and cannot: every path is resolved and compared against the *unresolved* root, so a link at `.agentweave` or
    `calls` already moves the resolved path outside it. The check is the design's belt and braces, redundant by
    construction.
- [x] 1.7 `hub/tests/test_tool_server_pin.py`: `PIN.launcher_dir()` (design D5):
  - it holds `aw-tool.cmd` (CRLF, naming `sys.executable`, `-I -S` and the pinned path, `--call %*`) and `aw-tool`
    (sh, `exec … -I -S … --call "$@"`);
  - both are rewritten when altered or deleted;
  - it sits under `<digest>/bin/<sha256(sys.executable)[:8]>`;
  - `prune_stale` removes it with its digest directory.
  - **Done 2026-10-01**: four tests in `test_tool_server_pin.py`, red first. The exact bytes of both launchers
    (`.cmd` CRLF; `sh` LF, forward slashes, executable on POSIX); rewritten after an alteration and a deletion;
    pruned with a stale digest; and 1.3's third case through the launcher itself (`aw-tool.cmd --list` under
    `cmd`, with a poisoned `json.py` on `PYTHONPATH`, exits 0).
- [x] 1.8 The trigger's env test: the one in `hub/tests/test_agent_trigger.py` that reads
  `spawned_env["AW_RUN_TOKEN"]` (`:713` at R2).
  - the launcher dir is the first `PATH` entry;
  - with a base env whose key is `Path`, the same key is reused and no second `PATH` key appears;
  - `<work_dir>/.agentweave/calls/` exists after the trigger;
  - (review fix 1, design D14) with `.agentweave/calls` a junction (Windows) or symlink (POSIX) to a directory
    holding a file, after the trigger `calls` is a real directory and the former target still holds its file; with
    `.agentweave` itself a link, the trigger proceeds, leaves it in place and logs a warning;
  - with `hub_client: "cli"` (no MCP), the launcher dir is still first on `PATH`;
  - a patched `PIN.path` that raises `OSError` refuses the trigger with 409 *"Could not materialize the tool
    server…"*, also under `hub_client: "cli"`. Today the pin is made only for MCP runs (design D5).
  - `hub/tests/test_repo_hygiene.py`: `.agentweave/calls/` is in `EXCLUDE_PATTERNS`, and in the seeded block.
  - **Done 2026-10-01**: in `test_agent_trigger.py` (new tests beside the `:708` env test, whose HTTP-form
    assertions change with group 5). Launchers first on `PATH`, one `PATH` key, and `.agentweave/calls/` a
    directory, for `hub_client` unset and `"cli"`. A patched `PIN.path` raising `OSError` refuses both: the route
    answers queue-first (`status: queued`, `run_id: null`, the reason in `waiting_reason`), not a bare 409, which
    is how it answers every `TriggerAgentError`; the `cli` row was red before the change (it started a run).
    `prepend_run_path` (a `Path` key reused, order kept) and `prepare_calls_dir` (a junction replaced and its
    target's file kept; a linked `.agentweave` left alone with a warning; a file replaced) are tested directly.
    `test_repo_hygiene.py`: `.agentweave/calls/` in `EXCLUDE_PATTERNS` and in the seeded block.
- [ ] 1.9 `hub/tests/test_tool_surface_matches_server.py` + `test_launchability.py`:
  - `access_path_notice("shim")` names `aw-tool` and `.agentweave/calls/`, and contains no `AW_RUN_TOKEN`, no
    `Bearer` and no `$HUB_URL`;
  - `_tool_surface_lines(access_path="shim")` renders every operation `_operations()` renders, each as
    `` `aw-tool <tool>` `` with its `args`, plus the short-name mapping sentence and the question wait in seconds
    (pass `question_timeout=37` and assert `37`);
  - the existing agreement check runs over the shim rendering too;
  - `_tool_surface_lines(access_path="cli")` raises `ValueError`, and `access_path="http"` renders today's HTTP
    form (design D11);
  - `described_access_path` never returns `"cli"` or `"http"` for a run. This includes
    `described_access_path("cli", override="cli") == "shim"`.
- [x] 1.10 `hub/tests/test_mcp_announce.py` (new), with an in-process app:
  - `wait(run_id, 1.0)` returns True at once when `mcp_adapter_online_at` is already set;
  - it returns True within ~0.1 s when the announce route is called during the wait;
  - it returns False after the timeout otherwise;
  - the announce route sets `harness_mcp_status = connected` over NULL and `absent`, and never over `failed`;
  - (R3, design D1 precedence) `record_harness_mcp_status(..., "failed")` after an announce leaves `failed`. An
    announce after a harness `failed` leaves `failed`. An announce after a wait's `absent` gives `connected`. A
    harness `connected` after a harness `failed` gives `connected`;
  - (review fix 5) the race: patch the row check so that the announce route commits and notifies **while** the
    check runs, after it has read the row as unset. `wait` returns True at once, not after the timeout. Against
    check-then-register it times out, so the test fails on R3's order;
  - (review fix 5) the stamp written directly to the row with no notify during the wait → `wait` returns True within
    one poll interval.
  - **Done 2026-10-01**: `hub/tests/test_mcp_announce.py`, 24 tests, written red (import error) before
    2.2/2.3. Precedence parametrised over six source orders plus the announce route over NULL/`absent`/`failed`;
    `ValueError` for a value no source reports (`pending`, an announce of `absent`, a wait of `connected`, an
    unknown source). The route's 500 is asserted through a client with `raise_app_exceptions=False` (the test
    client otherwise re-raises), with neither the stamp nor the status written. Mutation checks: an announce that
    writes over anything fails 2; **R3's check-then-register-then-wait order fails the race row** (a first
    mutation that re-checked right after registering did not, correctly: that order is as safe as the fix).
- [x] 1.11 `RunFacts` carries `plane_surface` and `harness_mcp_status` from the row. Extend the test that asserts
  `outside_workspace_writes` on the agent timeline / chat run facts (`grep -rn outside_workspace_writes
  hub/tests`), using the ordering the route returns.
  - **Done 2026-10-01**: `test_chat_run_facts.py::test_run_facts_carry_how_each_run_reached_the_hub`, both
    routes that serve `RunFacts` (chat conversation and `/agents/{name}/timeline`), rows `connected/mcp`,
    `absent/shim` and NULL/NULL; red on `KeyError` first.
- ~~1.12~~ **Cut by R3 with group 6** (design D8, open question 4). Codex's `decide_approval` is not a caller of the
  predicate. No Codex approval test is added.
- [ ] 1.13 (group 7) `hub/tests/test_agent_default_permission_mode.py` (there is no `test_runner_commands*.py`): a non-yolo Claude
  command, with and without `mcp_command`, carries `Bash(aw-tool:*)` and `PowerShell(aw-tool:*)` in
  `--allowedTools`. A yolo command carries neither.
- [ ] 1.14 (after slice 2) Copilot transport, using slice 2's fake ACP agent (or a stub that answers `initialize`,
  `session/new` and `session/prompt`):
  - no announce within a patched 0.3 s wait → the fake receives the prompt `/mcp list` first, then a prompt whose
    text holds the shim notice and the `aw-tool` tool section; the run records `absent` + `shim`; exactly one
    `plane_surface` status event is stored, quoting the fake's `/mcp list` text;
  - the announce arrives during the wait → no `/mcp list`, the MCP notice, and `connected` + `mcp`;
  - in both cases, the prompt holds exactly one tool section, the one for the decided surface, and
    `.agentweave/context/<agent>.md` after the run holds that same section (design D9);
  - a raw `session.mcp_servers_loaded` with `agentweave` not connected, on a run told `shim`, emits **no**
    `copilot_mcp_server_failed` error event (design D9, R3's narrowing of slice 2's D10);
  - (R3) the announce arrives, the run is told `mcp`, then a raw `failed` for `agentweave` arrives. The run is
    recorded `failed`, slice 2's `copilot_mcp_server_failed` **is** emitted once, and no `plane_surface` status event
    is stored;
  - (R3) the `/mcp list` prompt's content is exactly one text block, `/mcp list`, and the model prompt holds exactly
    one access-path notice (none came from the pre-spawn `notices`);
  - (R3) a Copilot agent with `hub_client: "cli"` does not wait: no `/mcp list`, `shim`, status NULL;
  - (R3) an interrupt during the wait ends the run within one poll interval, with status NULL;
  - (review fix 7) a Copilot agent with `hub_client: "mcp"` whose wait times out is told `shim` (the shim notice and
    section, `plane_surface = shim`), and the next trigger still injects the server.
- [ ] 1.15 (review finding 4, design D16) Specification turns told `shim`:
  - Claude (slice 1's builder): `restrict_spec_writes=True` with `described_access_path="shim"` gives
    `--disallowedTools Edit,MultiEdit,NotebookEdit`; with `"mcp"` (and by default) today's
    `Edit,MultiEdit,Write,NotebookEdit`; both under yolo too. The trigger passes the described value (patch
    `build_command` and read its kwargs, as the existing seams do);
  - Copilot (slice 2's fake ACP agent): a spec turn's argv excludes `apply_patch,edit,str_replace,str_replace_editor`
    and not `create`; an `edit` request for `.agentweave/calls/1.json` is allowed by standing and one for `src/x.py`
    is `reject_once`, under `workspace`, under `manual` (no card asked) and under full access (where `allow_all` is
    not set on for the spec turn); under full access a spec turn's non-`edit` request, a PowerShell command writing
    outside the workspace, is refused as under `workspace`, never ALLOWed on full access's account (design open
    question 11, DECIDED (c) 2026-09-28); `session/set_mode` plan is sent after the wait and only for a run told `mcp`.

## 2. The per-run record (design D1)

- [x] 2.1 Migration (next free number at build time; read `.claude/rules/db-migrations.md`):
  - add nullable `runs.harness_mcp_status` (String(16)) and `runs.plane_surface` (String(8)), guarded for a missing
    table;
  - backfill `harness_mcp_status='connected'` where `mcp_adapter_online_at IS NOT NULL`;
  - bump the head assertions in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`;
  - add the fields to `db/models.py` `Run` with a comment in the house style.
  - Verify: `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q`.
  - **Done 2026-10-01**: migration **0115** (`0115_run_harness_mcp_status_and_plane_surface.py`), guarded for a
    missing `runs`, backfill only over NULL; `plane_surface` not backfilled (what an older run was told was never
    recorded). Two tests in `test_migrations.py` (backfill of a stamped vs an unstamped run; the guard), red
    first; head bumped in both files. Verify: `test_migrations.py` + `test_project_persistence.py` 124 passed.
- [x] 2.2 `record_harness_mcp_status(session, run_id, status, *, source)` in `launchability.py` (or a new small
  module), with `source` one of `harness` / `announce` / `wait`. It enforces design D1's precedence (R3, replacing
  "`connected` is final" and unknown→`failed`). Callers outside the announce route call it inside a `try` that logs,
  because a failing record must never fail a run. The announce route (`agent_actions.py:459-483`)
  writes the stamp and the status in one commit, then calls `mcp_announce.notify(run_id)`. If either raises, the
  route returns 500 and writes nothing (design D1).
  - **Done 2026-10-01**: `launchability.record_harness_mcp_status(db, run_id, status, *, source)`, which does not
    commit (the announce route commits stamp and status together; executor callers commit in a `try`). The
    announce route (`agent_actions.report_mcp_adapter_online`) records `connected` by precedence in the stamp's
    commit, then `mcp_announce.notify`. Verification finding 13 applied: `notify` is total, so a write that landed
    is never answered 500.
- [x] 2.3 `hub/hub/mcp_announce.py`: the per-run event registry and `wait(run_id, timeout)`, which checks the row
  first (design D9). Registry entries are removed when the wait returns or the run ends.
  - **Done 2026-10-01**: `hub/hub/mcp_announce.py` (`MCP_ANNOUNCE_WAIT_SECONDS = 15.0`, `POLL_SECONDS = 0.25`):
    registers, then checks; re-checks the row every poll; honours `should_interrupt`; total (a failing check is
    "not yet"); the registration is removed when the wait returns. Test 1.10 passes.
- [ ] 2.4 Replace `harness_has_honoured_mcp` with `latest_mcp_test`, and change `described_access_path` to take
  `latest` and to return `mcp` | `shim`. Update the call at `agent_trigger.py:1107-1112`. Tests 1.1 and 1.9 pass.
- [ ] 2.5 Claude: `ParsedLine.harness_mcp_status` and the `system`/`init` branch in `parse_claude_line`. The claude
  run loop (`agent_trigger.py` ~`:2451-2560`, `parse_line` consumer) records it through 2.2 when the run was given
  MCP, inside a `try` (design D1, R3). Test 1.2 passes.
- [ ] 2.6 Codex app-server (R2 settled open question 3):
  - in `run_turn`'s `mcpServer/startupStatus/updated` branch (`codex_appserver.py:1162-1183`), when
    `name == own_server_name`, map `ready` → `connected` and `failed` → `failed`, through a new callback into 2.2.
    The callback never raises out of `run_turn` (design D1, R3);
  - the existing `failed` error event is unchanged;
  - no status leaves the run untested;
  - test: extend `TestRunTurnMcpStartupFailure` (`test_codex_appserver_run_turn.py:555`) with a `ready` case;
  - (review fix 6, design D12) `map_mcp_server_failure` takes `told_access_path`. For `"shim"` the own-server
    message says the run was told to reach the Hub with `aw-tool` and contains no "no AgentWeave tools"; for `"mcp"`
    it is today's text; the code and once-per-turn rule are unchanged. `run_turn` passes the request's told surface.
    Test: the same class, a `failed` status with each told surface.
- [x] 2.7 `RunFacts` gains the two fields at both construction sites (`agents.py:898`, `agent_chat.py:341` at R2). Test
  1.11 passes.
  - **Done 2026-10-01**: `RunFacts.harness_mcp_status`/`plane_surface` (`schemas/agents.py`), set at both
    construction sites (`agents.py` timeline, `agent_chat.py` chat). Test 1.11 passes.

## 3. The call mode (design D3, D4, D6, D7)

- [x] 3.1 In `mcp_server.py`, before the fastmcp import:
  - `_CALL_MODE` and the `_CallRegistry` stand-in (import `sys` at the top);
  - (review note 12) `_CALLABLE_TOOLS` and the `_tool()` decorator that records the function and applies
    `mcp.tool()`; every `@mcp.tool()` becomes `@_tool()` (design D3);
  - keep the `ImportError` message for server mode;
  - re-read `.claude/rules/mcp-server.md` first, and keep `approve_tool_call` without a return annotation.
  - **Done 2026-10-01**: `_CALL_MODE`, `_CallRegistry`, `_CALLABLE_TOOLS`/`_NOT_CALLABLE` and `_tool()` in
    `mcp_server.py`; all 27 `@mcp.tool()` became `@_tool()`; `approve_tool_call` keeps no return annotation.
    New stdlib imports: `codecs`, `inspect`, `locale`, `sys`.
- [x] 3.2 `call_main(argv) -> int`:
  - `--list` / `--help`;
  - bind with `inspect.signature`;
  - read the file only when the calls-root rule holds (design D3, *Where the file may be*; D8), else `usage`;
  - decode it in design D3's order: BOM, strict UTF-8, then on Windows the ANSI code page, else `usage` naming
    `-Encoding utf8`;
  - map `HubAPIError` / `HubUnreachableError` / `UnboundIdentityError` / usage errors to the D3 envelope and exit
    codes, and every other exception to `kind: internal`, exit 70;
  - never call `_announce_adapter_online` (design D4);
  - `json.dumps(result, default=str)`;
  - refuse `approve_tool_call`.
  The entry guard at the end of the file dispatches to `call_main(sys.argv[2:])` in call mode (keep it the last
  block; its comment explains why).
  - **Done 2026-10-01**: `call_main(argv)`: `--list`/`--help`, options refused (so `--token x` is usage), at most
    one file, `approve_tool_call` and unknown names refused, `_read_call_args` (calls-root rule, then D3's decode
    order), `inspect.signature().bind`, the envelope kinds with exit codes 0/1/2/2/64/70, `ensure_ascii` output, no
    announce. The entry guard dispatches `call_main(sys.argv[2:])` and stays the last block.
- [x] 3.3 Tests 1.3–1.5 pass. Then `py -3.11 -m pytest hub/tests/test_mcp_server_stdio_surface.py
  hub/tests/test_mcp_server.py hub/tests/test_fastmcp_api_contract.py hub/tests/test_mcp_tool_schemas.py -q`
  (server mode unchanged).
  - **Done 2026-10-01**: tests 1.3-1.5, 30 passed. Server mode unchanged: `test_mcp_server_stdio_surface.py`,
    `test_mcp_server.py`, `test_fastmcp_api_contract.py`, `test_mcp_tool_schemas.py` (plus
    `test_copilot_acp_decide.py`, `test_permission_approver.py`, `test_tool_surface_matches_server.py`): 487
    passed, 1 skipped.
- [x] 3.4 Update `.claude/rules/mcp-server.md`, one bullet: call mode exists, is decided before the fastmcp import,
  and a new tool is callable through it automatically.
  - **Done 2026-10-01**: `.claude/rules/mcp-server.md` gains the call-mode bullet, and its step 1 now says
    `@_tool()` (verification finding 14: step 1 named `@mcp.tool()`).

## 4. The launcher, the run's PATH and the calls directory (design D5, D14)

- [x] 4.1 `ToolServerPin.launcher_dir()` in `tool_server.py` (launchers pass `-I -S`), and prune with the digest
  directory. Test 1.7 passes.
  - **Done 2026-10-01**: `ToolServerPin.launcher_dir()`, with `path()` and it sharing one `_write_verified`
    (compare, touch, or atomic replace). Pruning needed no change: the launchers live inside the digest
    directory `prune_stale` removes. Test 1.7 passes.
- [x] 4.2 `agent_trigger.py`:
  - the `PATH` prepend, with a case-insensitive key, beside `AW_RUN_TOKEN` (`:1246`);
  - `.agentweave/calls/` created beside the context file (`:1160-1169`), with an `OSError` refused as the context
    write is. A `calls` that is a link or junction is removed (the link, never its target's contents) and recreated
    as a directory; a `.agentweave` that is a link is left alone with a logged warning (design D14, review fix 1);
  - `PIN.path()` and `PIN.launcher_dir()` for **every** run, before the `mcp_command` branch. An `OSError` is
    refused with the tool-server reason (`:1197-1203`), and the MCP branch then reuses the path (design D5).
  Test 1.8 passes.
  - **Done 2026-10-01**: `prepend_run_path` beside `AW_WORKSPACE_DIR`; `prepare_calls_dir` right after the context
    write, with its refusal; `pinned_server_path()` and `PIN.launcher_dir()` for every run before
    `mcp_command`, which reuses the path. Verification finding 13 applied: `ValueError` is caught beside `OSError`
    at both new steps. Test 1.8 passes.
- [x] 4.3 `repo_hygiene.EXCLUDE_PATTERNS` gains `.agentweave/calls/` with a one-line reason. Test 1.8 (hygiene half)
  passes.
  - **Done 2026-10-01**: `.agentweave/calls/` in `repo_hygiene.EXCLUDE_PATTERNS`, with its reason.

## 5. What the run is told (design D9–D12)

- [ ] 5.1 **Check slice 2 first:** does `copilot.exe` itself (not only the `--additional-mcp-config` `env`) get
  `AW_RUN_TOKEN`, `HUB_URL`, `AW_WORKSPACE_DIR` and the run's `PATH`? Read slice 2's `build_launch`. If not, 5.4
  adds it.
- [ ] 5.2 `access_path_notice("shim")` (replacing the HTTP branch) and `_shim_lines` / the shim preamble in
  `_tool_surface_lines`. It takes `question_timeout` (the agent's `question_timeout_seconds` or the restated
  default 240).
  - `_http_lines` stays, reachable only by an explicit `access_path="http"` (design D11, open question 1). Any
    other value raises `ValueError`.
  - Move the tests that pass `"cli"`:
    - `HTTP_PATH` in `test_tool_surface_matches_server.py:36` → `"http"`;
    - `access_path_notice("cli")` in `test_agent_facing_text.py:162` and `test_launchability.py:588` →
      `"shim"`, with their assertions rewritten to the shim text.
  - If `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` has landed, the shim form renders its
    host-`SendMessage` sentence too.
  - (review fix 6, design D10) for a Codex run, the shim notice carries the sandbox-network sentence (*"… If
    `aw-tool` reports `unreachable`, say so in your reply rather than retrying."*), keyed on the runner; no other
    runner's notice carries it.
  - (review fix 3) the shim notice says to write the args file with the file tool, or from PowerShell only with
    `Set-Content -Encoding utf8`, and that the JSON envelope is the last line of output (design D3, note 9).
  - (review finding 4, design D16) a spec turn told `shim` is told to write the args file with the file tool.
  Test 1.9 passes.
- [ ] 5.3 `_render_hub_agent_context`: no `include_tool_surface` flag (contract reconciliation, 2026-09-28). Slice 2's D5 returns the
  tool section as its own key, carried as `RpcTurnRequest.tool_surface_context`.
  - `agents.py:2126` is the only `_tool_surface_lines` call.
  - The claude/codex paths are unchanged.
  - Record `plane_surface` when the prompt is composed. On the Claude/Codex path that is the `Run(...)`
    constructor (`agent_trigger.py:1306`), which comes after the prompt.
- [ ] 5.4 Copilot, in slice 2's adapter and transport:
  - `tests_mcp_before_first_prompt = True` on the ACP **transport** (slice 1 D16: a transport `ClassVar`);
  - the transport waits with `mcp_announce.wait` after `session/new` / `session/load`, **only when the run was
    given the server**, honouring `should_interrupt`. On timeout it sends `/mcp list` as a bare single text block,
    then calls `cb.render_surface(surface)` (an `RpcCallbacks` field, total) and sends `session/prompt`;
  - the pre-spawn `notices` omit `access_path_notice` for such a runner (`agent_trigger.py:1173`), because
    `render_surface` supplies it (design D9, R3);
  - the pre-spawn `tool_surface_context` is not sent; `render_surface`'s output replaces it (slice 2's agent file never
    carried the section);
  - `render_surface` returns the notice and the section, and rewrites `.agentweave/context/<agent>.md` with the
    section for the decided surface (design D9);
  - `mcp_announce.wait` is total: a failing row check counts as "not yet";
  - slice 2's `copilot_mcp_server_failed` error event is suppressed for a run told `shim` and kept for a run told
    `mcp` (design D9, R3); the mapper reads slice 2's `RpcTurnRequest.told_access_path`, which the transport
    replaces with the surface it passed to `render_surface` (contract reconciliation, 2026-09-28);
  - slice 2's `CopilotEventMapper` passes `session.mcp_servers_loaded` / `mcp_server_status_changed` entries for `agentweave` with
    status `connected` or `failed` to 2.2 as `source="harness"`, and stores any other status as a diagnostic;
  - `copilot.exe`'s env per 5.1;
  - (review finding 4, design D16) spec turns: `create` leaves `--excluded-tools`; the handler's spec-turn `edit`
    rule in every posture; no `allow_all` on a spec turn; Plan mode after the wait, for `mcp` only (consistency pass
    2026-09-28: slice 2's D9 item 1a now ships the first three with every spec-turn `edit` refused, so here only the
    step-3 args-file allow and the plan-mode move remain, unless slice 2 landed without them; the full-access non-`edit`
    answer is judged as `workspace`, design open question 11 DECIDED (c) 2026-09-28, which slice 2 ships too; add it
    here only if slice 2 landed without it);
  - (review fix 7) a run's own wait timeout gives `shim` even under `hub_client: "mcp"` (design D1).
  Tests 1.14 and 1.15 (Copilot half) pass.
- [ ] 5.6 (review finding 4, design D16; slice 1's builder) `restrict_spec_writes` with the described surface: the
  `described_access_path` keyword, and `Write` kept only for Claude spec turns described `shim`. Test 1.15 (Claude
  half) passes.
- [ ] 5.5 The `plane_surface` status event, once per run, when a run given MCP is recorded `absent` or `failed`
  (quoting the `/mcp list` line on Copilot, bounded by `_truncate_utf8`). Its wording follows the run's
  `plane_surface` (design D12, R3), and for `mcp` its second sentence depends on a `hub_client: "mcp"` declaration
  (review fix 7). It is not emitted where the runner's own failure event states it: Codex `failed` (reworded for
  `shim` by 2.6), and Copilot told `mcp`. Test 1.14 (event half) passes. Add a Claude case beside 1.2's consumer test: a
  run told `mcp` whose `init` omits the server gets the "although the run was told to use it" wording.

## 6. The approver recognises the call command (design D8)

- [x] 6.1 `_hub_own_call(tool_name, tool_input, *, workspace=None)` in `mcp_server.py`. It uses:
  - the character allow-list;
  - `_lex`;
  - the callable set from 3.1;
  - `_HUB_OWN_WRITE_TOOLS` (restated);
  - `workspace`, defaulting to `AW_WORKSPACE_DIR`.
  `_decide` and `approve_tool_call`'s operator branch call it in place of their `mcp__agentweave__` lines. Test 1.6
  passes.
  - **Done 2026-10-01**: `_hub_own_call` with `_hub_calls_root`, `_inside_hub_calls_root`, `_plain_calls_path`,
    `_hub_own_command`, `_hub_own_write`, `_PLAIN_COMMAND_CHARS` (+ `\` for PowerShell) and `_HUB_OWN_WRITE_TOOLS`
    in `mcp_server.py`; total (any exception is None). `_decide` and `approve_tool_call`'s operator branch call it
    in place of their `mcp__agentweave__` lines. Case 2 and 3 need a known workspace (an empty one gives no
    standing). Test 1.6 passes; the approver suites (`test_permission_approver.py`, `test_copilot_acp_decide.py`,
    `test_ask_me_card_verdicts.py`, `test_mcp_server.py`) still pass: 515 with the new files.
- [ ] 6.2 Slice 2's ACP permission handler calls `_hub_own_call(..., workspace=<run work dir>)` before `_decide` or
  the card, in every posture, on its normalised `(tool_name, tool_input)`. It reports the allow like any other
  decision (`on_decision`, if `a-run-records-that-its-calls-were-allowed` has landed).
- ~~6.3~~ **Cut by R3** (design D8, open question 4). The original text is kept below for the record. The cut's
  consequences are already applied: 1.12 dropped, D8's Codex caller struck, the sandboxing requirement narrowed.
  Codex's `decide_approval`: the command-approval branch accepts on `_hub_own_call` before the
  posture branches (imported from `hub.mcp_server`; the Hub side may import it, as `agents.py:1016` already does).
  Test 1.12 passes.
  - **R2 recommends cutting** (design D8, open question 4). The approval's command is wrapped, and the Codex shell
    probably has neither the token nor the network.
  - If kept, first unwrap exactly one wrapper, as D8 specifies.
  - If cut:
    - drop 1.12 and D8's Codex caller;
    - narrow the first line of *"The Hub's own call command is decided like the Hub's own tools"* in
      `specs/agent-run-sandboxing/spec.md` from "Wherever the Hub answers a run's permission request" to
      "Wherever the Hub answers a Claude or Copilot run's permission request" (open question 8);
    - re-run `openspec validate --strict`.

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
  event. Record the time from `session/new` returning to the announce (open question 2), and the literal raw
  `mcp_servers_loaded` status string for `agentweave` (review note 10).
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
  Expect `absent`, and one `plane_surface` status event with the wording for the surface the first turn was told.
  Record the literal `init` status string for `agentweave`, or its absence (review note 10: a `pending` there is the
  latch's way back).
  The second turn, *"Reply ok."*, is recorded `plane_surface = shim`, and its `.agentweave/context/<agent>.md`
  holds the `aw-tool` tool section. R3: the Hub stores no composed prompt (`agent_trigger.py:1194` builds it,
  `:1217`/`:1403` pass it, and `Run` has no prompt column), so "read the stored prompt" could not be done.
- [ ] 9.8 **Claude, F301** (group 7; Haiku, 1 turn). A Claude agent with `config.hub_client = "cli"`: *"Create an
  AgentWeave task titled S3-F301, then stop."* Expect the task created through `aw-tool` with no denial.
  - If it holds, F301 is closed for Claude.
  - If the harness refuses the command, record the refusal verbatim, F301 stays open for Claude, and group 7 is
    reported rather than reverted.
- [ ] 9.10 (review finding 4, design D16) **Copilot spec turn told `shim`** (1 prompt), on 9.3's blocked agent, with
  a specification document open: *"Submit this document unchanged, then stop."* Expect `absent` + `shim`; the model
  wrote `.agentweave/calls/*.json` with `create` (allowed by standing, no card) and ran `aw-tool
  submit_spec_document …`; the document's submission recorded; any other write in the turn refused. If Copilot never
  sends the `create` request, record what it did instead.
- [ ] 9.9 Append the outcome to `scripts/drive/FINDINGS.md`: the F340 status line (fixed), F301 (fixed for Copilot;
  Claude per 9.8), and F299 (answered for Copilot; open for Claude). File any new defect as a new finding.

## 10. Archive

- [ ] 10.1 The human-only checks in `test-guide.md` are done by the operator on the work PC, or explicitly waived by
  them. Step 8's answer (whether Copilot's shell sessions persist between a run's commands there, and whether any
  run activated a venv, imported a module or set `ComSpec` before an `aw-tool` call) is recorded in the Round log:
  it is the trigger for the detect-and-degrade follow-up change (design open question 7, DECIDED (a) now, (c) as a
  follow-up, 2026-09-28). If it shows persistent sessions in use, raise that change; it is not built here.
- [ ] 10.2 `openspec validate a-run-reaches-the-hub-without-mcp --strict`, then the `openspec-archive-change` skill.
  Sync the four deltas. Commit and push per CLAUDE.md, staging paths explicitly.
