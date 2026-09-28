# Design — a run reaches the Hub without MCP

Evidence tags, as in the exploration: **VERIFIED** means measured on this machine (by this R1 today, or read
from a probe transcript on disk). **DOCUMENTED** means vendor docs or the shipped changelog. **INFERRED** means
reasoned from code or strings, not exercised. Copilot facts below were measured on **Copilot CLI 1.0.88**,
spawned as `copilot.exe --acp --stdio --no-auto-update` under a scratch `COPILOT_HOME`
(`%TEMP%\ghcp-s3-home`), with no model-calling prompt. The probe scripts and logs are in this session's
scratchpad (`s3/run1.log`, `run2.log`, `run3.log`, `tsrv.py`).

**Line numbers.** Rebased by R2 on 2026-09-28 against master `ef55e6f`. Only five of the 2026-09-27 night
ORDER's changes had landed then, and none of the ones this change depends on. A site that an unbuilt change will
move is marked **(rebase at IMPL: `<change>` unbuilt at R2)**. The expected post-landing shape is in the round
log's R2 entry. R3 (2026-09-28, master `fc33ff9`, whose only change since `ef55e6f` is R2's documents)
re-checked every site it relies on and found no drift.

## D1. Detection is per run, recorded, and the latest test decides (F340)

**What is wrong today.** `harness_has_honoured_mcp` (`hub/hub/launchability.py:252-280`) returns true if **any**
run of the agent has `mcp_adapter_online_at`. It uses `.limit(1)`, with no ordering and no recency. Its docstring
says there is *"no negative form to record: a harness that ignores the configuration is silent"*. F340 measured
that the harness is not silent:
- Claude's first stream-json line (`system`/`init`) lists `mcp_servers` with `connected` or `failed`, and **omits**
  a server blocked by `deniedMcpServers` (F340's table, 2.1.269).
- `parse_claude_line` has no `system` branch (`hub/hub/runner_parsing.py:229-371`; the fall-through is at the end
  of the function).

**The record.** Two nullable columns on `runs`:

| column | values | written when |
|---|---|---|
| `harness_mcp_status` | `connected` \| `failed` \| `absent` \| NULL | the run was given the Hub's MCP server (slice 1's `tool_surface` axis is MCP), and a runner-specific source reported. NULL means the run was never tested. |
| `plane_surface` | `mcp` \| `shim` | what this run was **told** (the notice and tool section it received). Written once the run's prompt is composed. |

The sources, per runner (all feed one writer, `record_harness_mcp_status(session, run_id, status)`):

| runner | `connected` | a negative | "untested" |
|---|---|---|---|
| any | the adapter's announce (`POST /mcp-adapter-online`, `agent_actions.py:459-483`). It keeps stamping `mcp_adapter_online_at` as today, and now also sets `connected` (subject to the precedence below). | — | — |
| claude | `init.mcp_servers[agentweave].status == "connected"` | `"failed"` → `failed`; no `agentweave` entry → `absent` | no `init` line seen (spawn failure, killed before init). R3: an `init` status other than `connected`/`failed` (for example `pending`) is **not a report**; the announce, if any, decides that run |
| copilot | announce within the wait (D9); a raw `connected` for `agentweave` | wait timed out → `absent`; a raw `failed` for `agentweave` → `failed` (R3; `failed` is VERIFIED in appendix A §D, every other raw string stays a diagnostic) | the run ended, or was cancelled, before the wait finished (R3); the run was not given the server (no wait, D9) |
| codex (app-server) | announce; or `mcpServer/startupStatus/updated` for `agentweave` with status `ready` | the same notification with status `failed` → `failed` | no status for `agentweave` by run end (R2: the "completed with no announce → `absent`" row is dropped, open question 3) |
| codex (exec) | announce | — | every other end |

**R3: F340 is not closed for Codex `exec`, nor for a Codex app-server run that reports no status.** The latest-test
rule skips untested runs. A runner with no negative source therefore keeps its last verdict, and that may be an
old `connected`. That is today's latch, narrowed to those runs. `exec` is a live transport
(`codex_appserver.uses_app_server`, `agent_trigger.py:1210`, opted into by a runner flag). Recording "completed
with no announce → `absent`" would close it by guessing, and for Codex the guess is not the safe direction: a Codex
run told `shim` points at a command whose shell may have no network (open question 4). So the rule is not added.
`proposal.md`'s F340 line says so.

R2: the Codex app-server source already exists. `run_turn` reads `mcpServer/startupStatus/updated`
(`codex_appserver.py:1162-1183`; `McpServerStartupState` is `starting | ready | failed | cancelled`), and today
it only turns `failed` into an error event (`map_mcp_server_failure`, `:547-567`). This slice also routes `ready`
and `failed` for the Hub's own server name to `record_harness_mcp_status`. Whether Codex reports anything for a
server that a policy removed is not known, so a Codex run with no status stays untested rather than guessed
`absent`.

**Precedence, not "`connected` is final" (R3).** R1 and R2 made `connected` final, on the grounds that the announce
is direct evidence that the harness started the program. That is what it proves, and no more.
`_announce_adapter_online` runs first in `main()` (`mcp_server.py:2091-2094`), after the module's imports and
**before** `mcp.run` answers `initialize`. So a harness that started the server and then failed the connection has
already produced the announce. Examples are a handshake timeout, or a crash inside `mcp.run`. Claude's
`init` then says `failed`, Codex's `startupStatus` says `failed`, and Copilot's raw event says `failed`.

Under "`connected` is final", each such run was recorded `connected`, and the next Claude/Codex run was told MCP. Its
own announce would again be final, so the next run would be told MCP too. That is F340's positive-only latch, rebuilt
one level down, for exactly the "started but not usable" case. The rule is therefore a precedence over sources. The
result is the same whatever order the sources arrive in:
1. **The harness's own recognised report decides.** That is Claude `init` `connected`/`failed`/absent entry, Codex
   `ready`/`failed`, and Copilot raw `connected`/`failed`. A later recognised report from the harness replaces an
   earlier one; Copilot's `mcp_server_status_changed` can move a server twice.
2. **Otherwise the announce decides `connected`.** It writes over NULL and `absent`, never over `failed`.
3. **Otherwise Copilot's wait decides `absent`.** It writes only over NULL.

One column suffices. `failed` can only come from a harness report, and a harness `absent` (Claude omitted the server)
is never legitimately followed by an announce, because the process was not started. The one sequence this gets wrong
is a Claude `absent` followed by an announce that something other than the harness posted. Anything holding the run
token can post one: the model with `curl`, or by running the pinned file without `--call`. That makes one run's
record `connected`, and the next run's own test corrects it. This is recorded, not guarded.

**Unknown vendor strings are not reports.** An `init` status other than `connected`/`failed` is ignored, not stored
as `failed`. R2's "store as `failed`" would, under this precedence, outrank a real announce. If Claude ever reports
`pending` at `init` for a slow server, every run would then be recorded `failed` and told `shim` for ever. A raw
Copilot status other than `connected`/`failed` is only a diagnostic (D12). F340's own requirement says: *"A status
string the Hub does not recognise must count as 'no grounds'"*. An ignored string gives no grounds.

**What ignoring them costs (review note 10, 2026-09-28).** An ignored string is not free. It is the gap through which
a narrow latch returns:
- **Claude `pending`.** If a Claude version reports `pending` at `init` for a slow fastmcp start, the announce decides
  `connected`. If the server then fails, Claude emits no second `init`, and nothing later corrects the record: F340's
  latch is back for that version, one run at a time. Drive 9.7 (and 9.8) records the literal `init` status string for
  `agentweave`, so a `pending` shows up as a measurement, not a guess. If it does, the fix is a later Claude status
  source, not storing `pending` as `failed`.
- **Codex `cancelled`.** Likewise ignored; the announce, if any, decides. Codex is undrivable here, so this stays a
  stated gap.
- **Copilot, late announce.** An announce after the 15 s wait writes `connected` over the wait's `absent`, by the
  precedence. D12's event has already said *"did not start"*, and the `/mcp list` quote may say `(connected)`. The
  record is right and the event is stale. It is benign but self-contradictory, and D12 says so. A cold first start
  under corporate antivirus is the likely cause.

**Recording never fails a run (R3).** Every writer (the Claude read loop, the Codex `run_turn` callback, and
slice 2's Copilot `CopilotEventMapper`) calls `record_harness_mcp_status` inside a `try` that logs and continues. These run inside
the executors, and there an exception fails the run or the turn (Codex: `run_turn` raises only the tuple
`agent_trigger.py:3244` catches). A write that fails leaves the run untested, which is the safe direction. The
announce route is the one exception: it has its own transaction (below).

**The grounds.** Called at `agent_trigger.py:1106-1112` **(rebase at IMPL: slice 1 `each-runner-cli-is-one-adapter`
unbuilt at R2.** There, `resolve_access_path` is deleted and the call reads `described_access_path(axes.plane, …)`
after `resolve_access_axes`.) `harness_has_honoured_mcp` is replaced by `latest_mcp_test(db, project_id, agent) ->
Optional[str]`: the `harness_mcp_status` of the agent's most recent run (by `started_at`, then `id`) whose status
is not NULL. `described_access_path(..., latest=...)` describes MCP iff the operator declared `hub_client:
"mcp"` or `latest == "connected"`, and otherwise `shim`. A run that is *given* no server (slice 1's
`plane == "cli"`, today `access_path == "cli"`) is described `shim`, never `cli`: today's
`if access_path != "mcp": return access_path` (`launchability.py:311-312`) becomes `return "shim"`. Per agent, as
today; the docstring's argument for that grain (`launchability.py:258-264`) still holds.

**The operator's declaration against a run that tests itself (review fix 7, 2026-09-28).** `described_access_path`
returns `"mcp"` on `override == "mcp"` (`launchability.py:313-314`), and the capability-plane spec keeps *"The
operator's own statement is honoured"*. R1–R3 did not say which wins for a Copilot run whose own wait times out. The
order is:
1. **A run's own negative test before its first prompt decides that run** (`absent` from the wait, D9): it is told
   `shim`, declaration or not. The declaration is a statement about what the agent should be *given* and how it is
   usually reached. The run's own test is a measurement of what this harness did this turn, and telling a run tools
   it measurably lacks is the defect the requirement exists to prevent. The declaration still decides what is
   *given* (axis 1 stays `hub_client`-only), so the server is still injected and tested next turn.
2. **Otherwise the declaration decides**, as today, for every run described before spawn (Claude, Codex).
3. **Otherwise the latest test decides.**

`hub_client: "mcp"` is rare: the review read 0 agents holding it in the backup and profile databases (`mode=ro`).
D12's "next turn" wording depends on it (below).

**What the run is *given* does not move.** The record changes only what a run is *told*. Slice 1's axis 1
(`tool_surface`, whether the server is injected) stays decided by `hub_client` alone, and `posture_at_rest` keeps
reading the given path or `axes.approvals`. Nothing that decides containment reads `harness_mcp_status` or
`plane_surface` (the requirement *"A truer description does not silently widen permission"*). Slice 1's D16 row
*"per-run `tool_surface` detection … replaces D4's `hub_client`-only rule"* therefore describes something this
slice does **not** do. That is a note for slice 1's owner (R2 cross-slice gap 1).

**The announce route, when what it calls raises.** `report_mcp_adapter_online` (`agent_actions.py:459-483`) writes
the stamp and, by the precedence above, `harness_mcp_status = connected` in **one** commit. It calls `mcp_announce.notify(run_id)` only after
that commit. If `record_harness_mcp_status` or the commit raises, the route returns 500 and writes nothing. The
adapter swallows the failure (`_announce_adapter_online`, `mcp_server.py:2073-2088`, `contextlib.suppress`), and a
Copilot waiter times out. So the run is recorded `absent` and told `shim`. That is a false negative, but it is in the
safe direction, and the shim still works.

**Backfill.** The migration sets `harness_mcp_status = 'connected'` wherever `mcp_adapter_online_at` is set, so
an agent that has grounds today keeps them on the first turn after upgrade. Later untested runs stay NULL and
are skipped, so the first negative test after the upgrade is what revokes them. That is F340's repair.

**Why not a per-CLI grain, or a machine-wide one.** A policy is a machine fact, but a per-agent runner override
is ordinary, and one agent's harness must not speak for another's (the existing docstring's reason). The cost
is one no-grounds turn per new agent on a claude/codex runner, and it is paid in the safe direction (D10).

## D2. The shim is Hub-owned run tooling, not a sixth `agentweave` subcommand

CLAUDE.md: the CLI keeps only five `cmd_*` functions (`src/agentweave/cli.py`: `status`, `doctor`, `stop`,
`hub_start`, `reset`). `.claude/rules/cli.md` sends a sixth through the product direction first. The shim is
not an exception to that rule. It is outside the CLI, for four reasons:

1. **Version.** The installed `agentweave`/`aw` console script is whatever `pip` last installed, and CLAUDE.md
   warns that it lags this checkout. A run's calls must speak the routes of **the Hub that minted its token**.
   The pinned tool server already guarantees exactly that (`agent-tool-surface`, *"The tool server a run is
   given is the one its Hub loaded"*; `hub/hub/tool_server.py`).
2. **One implementation.** `ask_user`'s batch/poll/wait-ended protocol (`mcp_server.py:360-525`),
   `archive_job`'s direction wait (`:871-919`), `HubAPIError`/`HubUnreachableError` and `_readable_detail`
   already live in `mcp_server.py`. A CLI subcommand would restate them, and the equal-capability requirement
   calls a second copy of a waiting rule a defect.
3. **Identity.** The shim reads the run's own credential from the run's own environment. The CLI's `HttpTransport`
   is an operator-credential client, and `agent_trigger.py:1292` deliberately strips `HUB_API_KEY` from runs.
4. **The name is taken.** `pyproject.toml:82` installs `aw = "agentweave.cli:main"`. VERIFIED today:
   `(Get-Command aw).Source` is `C:\Users\huida\AppData\Local\Programs\Python\Python311\Scripts\aw.exe`, and
   `aw send_message …` prints the agentweave CLI's usage error. A shim called `aw` would shadow the product's
   own CLI alias inside runs, and would silently *be* that CLI wherever the `PATH` prepend failed. So the shim
   is **`aw-tool`**. This corrects the exploration's `aw <tool> --json @file` spelling (appendix C §3/§6).

## D3. The command's shape: `aw-tool <tool> [<args-file>]`

```
aw-tool <tool> [<args-file>]   call one AgentWeave tool; <args-file> holds a JSON object of its arguments
aw-tool --list                 print the callable tools and their parameters as JSON
aw-tool --help
```

- **The arguments are a file, never inline, never `@`-prefixed, never on stdin.** VERIFIED today on Windows
  PowerShell 5.1:
  - `aw-tool send_message --json @args.json` is a **parse error** ("The splatting operator '@' cannot be used to
    reference variables in an expression").
  - `aw-tool send_message '{"recipient":"x","text":"a b; c"}'` reaches the program as
    `{recipient:x,text:a b; c}`, with the inner double quotes stripped (5.1's native-argument quoting).
  - A bare relative path passes unchanged in both PowerShell and Git Bash (`['send_message',
    '.agentweave/calls/1.json']`).

  Stdin is left out because PowerShell 5.1 re-encodes piped strings through `$OutputEncoding` (ASCII by default)
  (DOCUMENTED PowerShell behaviour), and F301 measured Claude's analyser refusing heredoc brace forms.
- **The file's encoding (review fix 3, 2026-09-28).** R1–R3 said *"UTF-8 or UTF-16 with a BOM, because
  `Out-File`/`Set-Content` in 5.1 write those"*. That is half wrong. `Out-File` in 5.1 writes UTF-16LE with a BOM, but
  `Set-Content` writes the **ANSI code page with no BOM**. VERIFIED 2026-09-28 on 5.1.26100: an em dash written by a
  bare `Set-Content` is the single byte `0x97`, and a strict UTF-8 decode raises `UnicodeDecodeError`. `Set-Content
  -Encoding utf8` writes UTF-8 with a BOM. The decode order is therefore:
  1. a UTF-8 BOM → UTF-8; a UTF-16 BOM → UTF-16;
  2. otherwise strict UTF-8;
  3. if that fails, **on Windows only**, the ANSI code page (`locale.getencoding()`, 3.11+), which is what a bare
     `Set-Content` wrote;
  4. if that fails too, or on POSIX, a `usage` error that says to write the file with the file tool, or with
     `Set-Content -Encoding utf8`.

  The notice gives the same advice: write the args file with the file tool, and from PowerShell only with
  `-Encoding utf8`. It must hold a JSON object.
- **Where the file may be (review fix 8, 2026-09-28).** R1–R3 let the shim read *"any path its process can read,
  because the restriction belongs to the approver, not the reader"*. That is withdrawn. On Claude's `cli` path the
  approver is group 7's prefix rule `Bash(aw-tool:*)`, which restricts no path. And the predicate resolves a relative
  path against the workspace, while the shell resolves it against its current directory, which a persistent shell
  (Copilot's) and Claude's Bash tool both keep across a `cd`. So the shim enforces D8's path rule itself:
  - the path is resolved against the shim's own cwd, as the shell meant it;
  - the root is `os.path.join(os.path.realpath(AW_WORKSPACE_DIR), ".agentweave", "calls")`, not resolved further;
  - the file is read only when `normcase(realpath(root)) == normcase(root)` (no component of `.agentweave/calls` is
    a link or junction, D8) and the file's realpath is inside `root` by `commonpath`, and it ends in `.json`;
  - otherwise, and when `AW_WORKSPACE_DIR` is unset, it is a `usage` error naming the calls directory, and no
    request is made.

  Both approvers then mean the same thing, and a drifted working directory fails closed with a readable error.
- **No file** means `{}`, for tools with no required arguments (`list_tasks`, `list_checkpoints`).
- **Binding.** The keys are the tool function's parameter names, which are the MCP argument names, not the
  route's field names. They are bound with `inspect.signature(fn).bind(**args)`. An unknown or missing key is
  a usage error naming the accepted parameters and which are required. Values are not type-checked here: the Hub
  validates, and its 422 comes back readable through `_readable_detail`, exactly as over MCP.
- **Callable set.** Every function registered with `@mcp.tool()` **except `approve_tool_call`**, which is a
  runtime endpoint (`UNDESCRIBED_TOOLS`, `agents.py:989-999`) and means nothing when called by an agent. R2 count:
  27 registered, so 26 callable. All 27 are plain `def`s, and none is `async`.
  `submit_checkpoint_notes` stays callable, because the checkpoint prompt names it.
  **How the set is known in both modes (review note 12, 2026-09-28).** The predicate runs synchronously, and in the
  Hub process (slice 2's handler) and in the server mode `approve_tool_call` runs in, fastmcp is loaded, and
  enumerating its registered tools is async or private. So the module keeps one plain name set,
  `_CALLABLE_TOOLS: Dict[str, Callable]`, filled by a thin module-level decorator, `_tool()`, that records the
  function and then applies `mcp.tool()` (in server mode) or `_CallRegistry.tool()` (in call mode). Every
  `@mcp.tool()` becomes `@_tool()`. `approve_tool_call` is recorded like the rest and left out of the callable set
  by name, and it keeps its missing return annotation (`.claude/rules/mcp-server.md`). The predicate, `call_main` and
  `--list` read only this set, and test 1.3 asserts it equals the fastmcp-registered set minus `approve_tool_call`.
  That is what keeps *"cannot drift"* true.
- **Output.** One JSON object on stdout.
  - Success: `{"ok": true, "result": <the tool's return>}`, exit **0**.
  - Refusal: `{"ok": false, "error": {"kind": "rejected", "status": <int>, "detail": <str>, "data": {...}}}`,
    exit **1** (a `HubAPIError`: the Hub was reached and said no).
  - `{"kind": "unreachable", …}`, exit **2** (`HubUnreachableError`, naming `HUB_URL`'s value; the URL is not a
    secret).
  - `{"kind": "unbound", …}`, exit **2** (`UnboundIdentityError`: no `AW_RUN_TOKEN`).
  - `{"kind": "usage", …}`, exit **64**.
  - `{"kind": "internal", "detail": <str>}`, exit **70** (R2). This covers any other exception. They are real:
    `_hub_request` catches only `HTTPError` and `URLError` (`mcp_server.py:183-200`). A read timeout inside
    `response.read()` under `urlopen(timeout=10)` raises `TimeoutError` unwrapped, and a 2xx body that is not JSON
    raises `ValueError`. For a call that writes, the detail says the outcome is unknown and names `list_tasks` /
    `get_task` as the way to check. It does not say "failed", because the Hub may have committed the write.

  The shim prints nothing else to stdout, so a model can parse it. Exceptions are not leaked as tracebacks.
  **One exception the shim cannot control (review note 9).** PowerShell runs a `.cmd` as `%ComSpec% /c "…"`, without
  `/d`, so a machine whose `HKCU`/`HKLM` `Software\Microsoft\Command Processor\AutoRun` prints anything (`chcp 65001`
  prints `Active code page: 65001`) puts that text ahead of the envelope on every call. Corporate images set
  `AutoRun`, and the work PC is one. The envelope is still the last line, and the notice says so. Human-only step 3
  lists it as a likely cause. The `.exe` launcher (open question 7) would remove it.
  R3: the output keeps `json.dumps`'s default `ensure_ascii=True`. PowerShell 5.1 decodes a native command's stdout
  with the console code page, so non-ASCII text in a task title would otherwise arrive mangled. Escaped output is
  pure ASCII, so it is identical in every shell.

## D4. One file, fastmcp not imported in call mode

`mcp_server.py` imports fastmcp at module top and raises if it is missing (`:18-21`). `@mcp.tool()` returns the
plain function on fastmcp 3.1.0 (VERIFIED: `type(hub.mcp_server.send_message)` is `function`). The only other
`mcp.` use is `mcp.run` in `main()` (`:2094`).

**Call mode is decided before the import:**
```python
_CALL_MODE = __name__ == "__main__" and sys.argv[1:2] == ["--call"]
if _CALL_MODE:
    FastMCP = _CallRegistry          # stdlib stand-in: .tool() records the function by name, returns it
else:
    try: from fastmcp import FastMCP
    except ImportError as exc: raise ImportError(...) from exc
```
`_CallRegistry(name, instructions)` keeps a `{name: function}` dict. The entry-point guard at the bottom
(`:2106`) dispatches `main()` or `call_main(sys.argv[2:])`. `sys` is not imported today (`:8-16`), so the
import is added.

**Call mode never announces (R2).** `_announce_adapter_online` (`:2073-2088`) runs only from `main()` (`:2091-2094`).
It must stay there and must never run in call mode. The announce is the `connected` source for runs that have no
harness report, and it outranks a Copilot wait's `absent` (D1). If a shim call announced, a run whose harness refused the MCP server would record `connected` the first
time it used `aw-tool`, and every later run of the agent would be told MCP. That is F340's latch again, rebuilt out of
the fix. Test 1.4 asserts the stub Hub never sees `POST /mcp-adapter-online` from call mode.

**Why guard rather than split into two files.** Measured: importing `mcp_server.py` with fastmcp costs 1.39 s
per process, against 0.09 s for the stdlib alone. That is paid on every shim call.
- A split (`tool_calls.py` imported by `mcp_server.py`) would break `tool_server.py`'s premise that the server
  *"imports nothing from its own directory, so a byte-for-byte copy is the same program"* (`tool_server.py:3-5`).
  The pin would have to become a directory with a joint digest.
- The guard keeps one file, one pin and one digest, and it keeps `.claude/rules/mcp-server.md`'s import rule
  (stdlib + fastmcp) intact.
- Tests import the module (`__name__ != "__main__"`), so they keep the fastmcp path.

**Parity is checked by spawning.** A test spawns the **pinned** file as `--call --list` from a working
directory that is not the package root. It asserts that the names equal the fastmcp-registered tools minus
`approve_tool_call`. This is the same "verify the program as it is spawned" discipline `agent-tool-surface`
*"One tool surface, configured automatically"* requires of the MCP mode.

## D5. Where `aw-tool` lives, and how a run finds it

- **Location.** `~/.agentweave/hub/tool-server/<digest>/bin/<exe>/`, where `<digest>` is the pin's digest and
  `<exe>` is `sha256(sys.executable)[:8]`. The launcher embeds the interpreter path, and two Hubs with the same
  server bytes but different Pythons must not rewrite each other's launcher. Two files:
  - `aw-tool.cmd`: `@"<sys.executable>" -I -S "<pinned mcp_server.py>" --call %*`, with CRLF line endings.
  - `aw-tool`: `#!/bin/sh` + `exec "<python, forward slashes>" -I -S "<pinned path, forward slashes>" --call "$@"`,
    mode 0700 on POSIX. Git Bash on Windows runs it (VERIFIED today with a stand-in: `command -v aw-tool` found
    it, and argv arrived intact).
  - **`-I` (R3).** Isolated mode ignores every `PYTHON*` variable (`PYTHONPATH`, `PYTHONSTARTUP`, `PYTHONHOME`,
    …) and the user site, and it leaves the script's directory off `sys.path`. Call mode imports only the stdlib, so
    it loses nothing. `-I` does not touch `os.environ`, so `AW_RUN_TOKEN` and `HUB_URL` still reach the shim.
  - **`-S` (review fix 2, 2026-09-28).** `-I` still runs `site`, and `site` executes every `.pth` file in
    site-packages. The review counted five on this machine, `pywin32.pth` and three `__editable__` finders among them.
    `-S` skips `site` entirely. Call mode is stdlib-only, so it loses nothing, and the review measured it slightly
    faster (85 ms against 92 ms). What `-I -S` does **not** isolate is listed in D8's residual: `ComSpec`, `AutoRun`,
    `LD_PRELOAD`/`DYLD_*`, and PowerShell functions, aliases, modules and `PATH`.
    Without `-I`, an earlier command in a persistent shell could set `$env:PYTHONPATH='.'` next to a `json.py` in
    the workspace, and every later auto-approved `aw-tool` would run that file. Under "Workspace only", `_decide`
    allows both the assignment and the write, because both name only workspace words. The server mode that the
    harness spawns is unchanged.
  - **Resolution, VERIFIED by R3** on PowerShell 5.1.26100 with both files in one directory first on `PATH`.
    `Get-Command aw-tool -All` lists `aw-tool.cmd` first and the extensionless `aw-tool` second, and a bare
    `aw-tool …` runs the `.cmd`. The extensionless file would be tried only if the `.cmd` were missing, and then
    through its file association. The compare-and-rewrite below restores a deleted `.cmd` on the next trigger.
- **Verified like the server.** `ToolServerPin` gains `launcher_dir()`. It is written with the same
  compare-and-rewrite and atomic replace as `path()` (`tool_server.py:39-56`), inside the Hub user's own
  directory (the existing requirement's shared-directory clause applies unchanged), and pruned with the digest
  directory.
- **The pin is now executed per call, not loaded once (review note 11, 2026-09-28).** Before this change the pinned
  file was verified at trigger and loaded once per harness start. Now every `aw-tool` call re-reads
  `~/.agentweave/hub/tool-server/<digest>/mcp_server.py`. The compare-and-rewrite runs at trigger, not per call. So a
  change to that file in the middle of a run reaches that run's later, unasked calls, and those of every other
  in-flight run of this Hub, not only the next spawn. Making that change needs a write outside every workspace, into
  the Hub user's own directory, which the posture judges like any other outside write. The risk is low. It is stated,
  not guarded.
- **`PATH`.** In `trigger_agent_directly`, beside `AW_RUN_TOKEN` (`agent_trigger.py:1246`), the launcher
  directory is prepended to the run's `PATH`. On Windows the environment key may be spelled `Path`, so the
  existing key is found case-insensitively and reused. Every run gets it, whatever its surface: it is harmless
  when MCP is present, and it lets an agent with a wrong description still reach the plane.
- **The pin failing.** The shim is the same file as the MCP server. **R2 correction:** today the pin is
  materialized **only when `access_path == "mcp"`** (`agent_trigger.py:1195-1203`). A `hub_client: "cli"` run never
  calls `pinned_server_path()`. R1's "a pin that cannot be written already refuses the run … No run exists that has
  MCP but not the shim, or the reverse" was therefore false for exactly the runs that need the shim most. The
  trigger now calls `PIN.path()` and `PIN.launcher_dir()` for **every** run, before the `mcp_command` branch, and
  refuses with the existing 409 wording (*"Could not materialize the tool server for <agent>: …"*) on `OSError`.
  This is a new refusal for `cli` runs whose pin cannot be written. Such a run would otherwise be told a command
  that does not exist, so the refusal is the requirement *"A launcher that cannot be made refuses the run"*.
  **(rebase at IMPL: slice 1 `each-runner-cli-is-one-adapter` unbuilt at R2.** There, `mcp_command` is
  materialized iff `axes.tool_surface == "mcp"`, at the same place.)
- **Codex.** Slice 1 keeps Codex's explicit MCP env allow-list (appendix B §12). Whether Codex's *shell* sees the
  run's `PATH` and `AW_RUN_TOKEN` is **INFERRED**, not measured (open question 4).
- **Copilot.** The shim runs in Copilot's `powershell` tool. It needs `AW_RUN_TOKEN`, `HUB_URL`,
  `AW_WORKSPACE_DIR` and the prepended `PATH` in **`copilot.exe`'s own process environment**. R2: slice 2's design
  as written already does this. Its D3 *Environment* passes the whole run env the trigger builds
  (`agent_trigger.py:1243-1304`) to `copilot.exe`, and `agentweave-mcp.json` carries **no** `env` block, because the
  stdio child inherits (VERIFIED there). The `PATH` prepend sits in that same block, beside `AW_RUN_TOKEN`, so it
  reaches `copilot.exe` too. Task 5.1 still re-reads slice 2's code at IMPL, and 5.4 adds the env only if the built
  code differs from its design.

## D6. The credential never appears in text the Hub stores

- The shim reads `AW_RUN_TOKEN` and `HUB_URL` through the existing `_bound_token()`/`_hub_request`
  (`mcp_server.py:70-77`, `:164-200`). It takes no `--token` and no `--hub-url` option, and has no argv
  spelling of either.
- The notice and tool section name `aw-tool` and never the variables' values. They no longer need to name
  `AW_RUN_TOKEN` at all (D11).
- The command the model runs (`aw-tool create_task .agentweave/calls/1.json`) is what Copilot stores as
  `rawInput` and Claude as `tool_use.input`. It holds no secret. The args file holds only the tool's arguments.
- **Not `--secret-env-vars AW_RUN_TOKEN`** (DOCUMENTED: it strips the variable from shell and MCP environments).
  That would take the credential away from the shim too.

## D7. Operations that wait, wait through the shim too

- `ask_user` runs its own loop (`mcp_server.py:404-525`). It blocks for up to `QUESTION_ANSWER_TIMEOUT` (default
  240 s, `AW_QUESTION_TIMEOUT` 10–600, `:1005`), polls every 2 s, and posts `/questions/wait-ended` for expired
  ones. `archive_job` waits up to `OPERATOR_DECISION_TIMEOUT` (default 120 s) on the direction request.
- **The harness's shell timeout can be shorter.** Claude's Bash tool defaults to 120 s. For Copilot, R2 read
  `app.js` 1.0.88 (CODE, the in-app tool help table): the shell tool is *"a persistent Bash session"* taking
  `command`, `description`, `mode (sync | async)` and `initial_wait (number)`, with *"Long-running commands should
  use mode=async with read_bash for polling"*. So a long call is continued in the background and polled, not
  necessarily killed. The default `initial_wait` and what `sync` does when it is exceeded were not found. Open
  question 5 stays open for those.
- The call-command tool section therefore says, for `ask_user` and `archive_job`: *"this call waits up to N
  seconds for the operator; give the command a timeout longer than that, or run it in the background and read
  its output when it finishes"*. N is this run's own value: the agent's
  `question_timeout_seconds`, or the default restated.
- A shim killed mid-wait loses nothing the Hub needs. The question stays open. The run-end sweep records the
  expiry (`run_task_binding.py:905-960`, *"the tool's report and the run-end sweep"*), and the agent can still
  poll `aw-tool get_answer`. `blocking: false` plus `get_answer` stays the documented alternative.

## D8. The approver recognises the Hub's own call command, exactly

**One predicate in `mcp_server.py`**, `_hub_own_call(tool_name, tool_input, *, workspace=None) -> Optional[str]`. It
returns a reason (`"the Hub's own tools"`, the wording `_decide` already uses at `:1558`) when the call is the Hub's
own, and `None` otherwise. `workspace` defaults to `AW_WORKSPACE_DIR`. R2: the keyword is required because two of
its callers run in the **Hub** process, whose environment is not the run's. Since R3 cut group 6 that caller is slice
2's ACP handler alone. Slice 2's D8 gives `_decide` the same keyword for the same reason.

**Total (R3).** The predicate never raises. Every `os.path.realpath`/`commonpath` failure, and any other exception,
means `None`, which falls through. The reason is what each caller does when it raises:
- `approve_tool_call` is a FastMCP tool, so an exception becomes a tool error that the harness must interpret;
- slice 2's `decide_permission` answers `reject_once` on any client error (its D8, *"Every request is answered"*).

A raising predicate would therefore turn a request that should have fallen through into a refusal. That is the one
thing the rule promises never to do. A test patches `os.path.realpath` to raise `OSError` and asserts `None`.

It is true in exactly three cases:

1. `tool_name` starts with `mcp__agentweave__`. This moves today's check (`:1557-1558`, and `:1709-1710` in
   `approve_tool_call`) into the predicate unchanged. Slice 2 recognises its Copilot MCP requests itself, by
   server name from its raw-event `calls` map (`tool.execution_start` / `permission.requested`), never from a
   `title` (its D8 R3; contract reconciliation, 2026-09-28). It does not pass them through here.
2. **A shell command that is exactly one call-command invocation.** **R3: only for a tool named in
   `_TOOL_DIALECTS` (`Bash`, `PowerShell`, `:1072`).** R1 and R2 accepted a tool of unknown dialect read both ways, as
   `_decide` does. For `_decide` that is a stricter reading of a command it would judge anyway. For this predicate it
   is a widening. Under "Ask me", a foreign MCP tool such as `mcp__other__run` with input `{"command": "aw-tool
   list_tasks", "target": "…"}` would be allowed without a card, because its `command` key reads as a plain call.
   The predicate cannot know what a foreign tool does with its other keys. **Slice 2's `"Shell"` key never gets
   standing (conflict 1, DECIDED 2026-09-28).** Slice 2 normalises a shell request from `local_shell`, or one whose
   tool name it does not know, to `("Shell", {"command": …})`. Case 2 stays limited to `Bash`/`PowerShell`, so such a
   request goes to the judge, and under "Ask me" to a card. That is a real case lost, deliberately: an unnamed shell is
   exactly the one whose name lookup nobody knows, and `cmd` looks in the current directory first (the review measured
   `cmd /d /c "aw-tool list_tasks …"` running a workspace `aw-tool.bat` ahead of the launcher first on `PATH`, once
   `NoDefaultCurrentDirectoryInExePath` was unset; Claude Code sets it in its own shells, runs do not). Reading the
   text both ways checks characters, not resolution. Copilot's `write_powershell` is `execute`-kind, but its input is
   `{shellId, input, delay}`, text for a running process, not a command; it never reaches case 2 either. If slice 2's
   task 1.1 capture finds genuine `powershell` requests commonly arriving with no known name, the fix is in slice 2's
   `calls` map, not here. The command text is lexed with the existing `_lex`
   in that tool's dialect. It must satisfy **all** of:
   - **every character of the raw text is in a fixed plain set** (R2): ASCII letters, digits, `.`, `_`, `-`, `/`,
     the space, and `\` in the PowerShell reading only. Any other character makes the predicate `None`. R3: the set
     is an explicit ASCII `frozenset`, not `str.isalnum`, `str.isspace` or regex `\w`/`\s`. Those accept non-ASCII
     letters, digits and spaces, and `_lex` itself splits at `char.isspace()` (`:1476`), which includes U+00A0 and
     U+2028. R1 listed
     the forbidden characters instead (`; | & < > \n \r ` $ % * ?`), and that list missed grouping.
     `_ARGUMENT_ENDS` (`:1061`) splits arguments at `(` and `)`, so in PowerShell
     `aw-tool list_tasks (.agentweave/calls/1.json)` lexes to exactly the three words the rule accepts. PowerShell
     evaluates the parenthesised path **as a command**, which opens the data file with its associated program.
     `{…}` (a script block), `,` (an array), `@`, `#` and the quote characters are refused by the same allow-list.
     A deny-list of shell syntax fails open the next time it misses something; an allow-list of the characters an
     invocation needs cannot;
   - `_lex` yields no `nested` substitutions. This is implied by the allow-list, and is kept as a second check;
   - word 0 is exactly `aw-tool`, or `aw-tool.cmd` in the PowerShell reading. PowerShell compares command names
     case-insensitively and bash case-sensitively. A path to it (`./aw-tool`, `C:\…\aw-tool.cmd`) does **not**
     match, because the Hub cannot tell a path to its launcher from a path to a file the agent wrote;
   - word 1 is `--list`, `--help`, or a name in the callable set (D3). The set is computed in the same module, so
     it cannot drift;
   - there is at most one more word. It must be a plain relative path (no `..` component, no leading separator,
     no drive, no `~`, **R3: not beginning with `-`**), end in `.json`, and resolve with `os.path.realpath`
     against `workspace` to a file inside the **calls root**, by the *calls-root rule* below. The leading `-` is excluded because R3 measured that PowerShell 5.1 splits a
     native argument that begins with `-` and contains a `.`: `aw-tool create_task -x.agentweave/calls/1.json`
     reaches the program as `['create_task', '-x', '.agentweave/calls/1.json']`. The word the predicate judged is
     then not the argv the program gets. It cannot do more than a usage error, but "exactly" should mean exactly;
   - there are no further words.
3. **A file write whose declared paths are all `.json` files inside `<workspace>/.agentweave/calls/`, and that
   declares at least one** (R3: "every declared path" is vacuously true of none). The paths are resolved the same
   way, by the calls-root rule. A symlink out resolves out and fails. A write tool whose input carries a `command` key is not this case. **R2 correction:** R1 said "file write" means the tool
   kinds that slice 1's `write_tool_kinds` names. `mcp_server.py` cannot read that, because it is spawned
   standalone and imports only stdlib and fastmcp (`.claude/rules/mcp-server.md`). So the predicate restates
   Claude's write tools as `_HUB_OWN_WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit":
   "file_path", "NotebookEdit": "notebook_path"}`. A test asserts it equals `workspace_writes.CLAUDE_WRITE_TOOLS`
   (`workspace_writes.py:38-43`), the house pattern for a restated constant. Slice 2 judges a Copilot edit as
   `_decide("Write", {"path": p})` per path (its D8), so the predicate also reads the `path` key for `Write`. In
   other words, it reads every `_PATH_KEYS` entry (`:1009`) present on a tool in that set.

**The calls-root rule (review fix 1, BLOCKING, 2026-09-28).** R1–R3 said each path is *"resolved with `realpath`
and compared with `normcase` as `_where` does"*. `_where` compares against a **realpath'd** root (`_decide`: `root =
os.path.realpath(workspace)`, `mcp_server.py:1567`). The natural implementation, `_where(p,
os.path.realpath(<ws>/.agentweave/calls))`, therefore accepts everything under wherever `calls` points. VERIFIED
2026-09-28 (5.1.26100, Python 3.11): after `New-Item -ItemType Junction -Path ws\.agentweave\calls -Target ws\.claude`,
then `New-Item -Force` of the directory as a per-turn `mkdir` would do (it leaves the junction in place),
`realpath(<calls>/settings.json)` is `…\ws\.claude\settings.json` and `realpath(<calls>)` is `…\ws\.claude`. Under
"Workspace only", `_decide` allows the junction's creation, because every word names the workspace (the review
measured `{'allow': True, 'reason': 'inside your workspace'}`). The junction
then persists across postures, runs, agents and runners. Later, under "Ask me", a write of
`.agentweave/calls/settings.json` would be allowed by standing and land in `.claude/settings.json`, whose hooks run
code at the next Claude start. A junction to the workspace root reaches `.mcp.json` and `package.json`, and one to
`.vscode` reaches `tasks.json`. So the rule, used by cases 2 and 3 and by the shim itself (D3):
- **The calls root** is `os.path.join(os.path.realpath(workspace), ".agentweave", "calls")`, **not resolved further**.
- **The root must be itself.** The predicate is `None` unless `normcase(realpath(root)) == normcase(root)`. So neither
  `.agentweave` nor `calls` may be a symlink or a junction. The workspace itself may be one, because its realpath is
  what the root is built on. The check is this comparison, not `os.path.islink`: VERIFIED, `islink` is `False` for a
  directory junction on 3.11, and `os.path.isjunction` does not exist before 3.12.
- **The file must be inside it.** `commonpath([root, realpath(file)])` equals `root` under `normcase`. A file-level
  link out, `..`, and a different drive all fail this.
- Any exception is `None` (the predicate is total).

A junction swapped in between the decision and the write (a background shell job, say) is not caught. Starting that
job needed its own decision, so this is the same class as the persistent-session residual below. D14 says how the Hub
makes and checks the directory.

**Near misses fall through; they are never denied by this rule.** When the predicate returns `None`, today's
logic runs unchanged: the `workspace` posture's word-by-word `_decide`, or the operator card. So the predicate
can only turn an "ask" or an "allow by `_decide`" into an "allow by standing", never a refusal into an allow
that `_decide` would refuse *for a reason other than asking*.

Case 2 (limited to `Bash`/`PowerShell` since R3) is strictly narrower than what `_decide` already allows under
`workspace`, which permits any shell command whose words resolve inside the workspace. So under `workspace` the predicate changes only the recorded
reason. It changes behaviour only where someone would have been **asked**: the operator posture (`manual`, "Ask
me"), and Copilot/Codex requests routed to a card.

**Why this is not a widening.** The plane operations were never subject to the posture. Claude pre-allows
`mcp__agentweave__*` (`runner_commands.py:262`), and `approve_tool_call`'s operator branch answers them without
asking (`mcp_server.py:1705-1710`: *"asking a human to approve each `send_message` would make collaboration
unusable, and those calls are already bounded by the run's own credential"*). The shim reaches exactly those
operations under exactly that credential, and nothing else:
- it runs a fixed program with no shell of its own;
- the file it reads is data;
- the auto-approved write can only create `.json` data inside a Hub-owned, git-excluded directory, which nothing
  executes (D14), and only once the calls-root rule holds.

  **One residue (review note 13).** Nothing *automatically* executes the file, and nobody sees its content: Python
  runs any file as a script, whatever its extension, so a later card for `py .agentweave/calls/x.json` asks the
  operator to approve code they never saw. That command is a card under "Ask me" and a judged command under
  "Workspace only", as any other. Flagging a card whose command names a file under `.agentweave/calls/` belongs to
  the card's own change (`an-ask-me-card-says-what-workspace-only-would-decide`), and is not a reason to refuse case 3.
  It is recorded, not built here.

**A residual, for R3 and the Opus review (R2).** "A fixed program" assumes that the bare name `aw-tool` resolves to
the Hub's launcher. Copilot's shell is a *persistent* session (CODE, `app.js` help table). An earlier command in
the same session can define a PowerShell function or alias named `aw-tool`, or put another directory ahead of the
launcher on `PATH`. After that, the same exact text runs something else. The predicate cannot see this. It is not a
widening:
- under "Ask me", that earlier command was itself put to the operator, who approved it;
- under "Workspace only", `_decide` already allows the plain invocation's text, and it read the redefining
  command's words when that command ran.

It does mean the operator's approval of one innocuous-looking command can change what later unasked calls do. Say so
in the Opus review rather than claim the predicate alone bounds it. R3 narrowed the residual by one class: an
interpreter variable (`PYTHONPATH`, `PYTHONSTARTUP`) set earlier no longer changes what the launcher runs, because
the launcher passes `-I` (D5).

**The residual is wider than R3 stated (review fix 2, 2026-09-28).** What remains, after `-I -S`:
- **`ComSpec`.** PowerShell runs a `.cmd` as `%ComSpec% /c ""<path>\aw-tool.cmd" <args>"`. VERIFIED 2026-09-28 on
  5.1.26100: with `$env:ComSpec` set to a copy of `python.exe`, a bare `aw-tool list_tasks …` ran that program with
  `/c` as its first argument. The review measured the same with a workspace `argv.exe`, and `_decide` allows the
  assignment under "Workspace only". A relative `ComSpec` is not honoured.
- **cmd `AutoRun`.** The same command line has no `/d`, so `Command Processor\AutoRun` runs before every call (and
  may print, D3).
- **Site `.pth` files.** Closed by `-S` (D5).
- **POSIX loader variables.** `LD_PRELOAD`, `LD_LIBRARY_PATH` and `DYLD_*` are untouched by `-I`.
- **PowerShell command precedence.** An alias or function beats an application. The realistic triggers are ordinary
  commands, not odd ones: `Import-Module .\helpers.psm1` exporting an `aw-tool` function, and a virtualenv's
  `Activate.ps1`, which prepends `.venv\Scripts` to `PATH`, where an `aw-tool.cmd` then wins (both measured by the
  review). Under "Ask me" the operator approves "activate the venv" or "import the helper module" once, and every
  later `aw-tool` call in that persistent Copilot session runs workspace code with no card.
- **A user profile** loaded by the shell.

It is **Copilot-specific** in practice: Claude's Bash tool does not persist aliases, functions or environment
variables between calls. The predicate cannot close any of it. Two further measures would, and they are put to the
operator with open question 7 rather than assumed:
- **an `.exe` launcher** in place of `aw-tool.cmd`, which takes `cmd.exe` out of the chain, and with it `ComSpec`,
  `AutoRun` and `%*` re-parsing. pip's own console-script launcher (`pip/_vendor/distlib/t64.exe`, how `aw.exe`
  exists) is one ready-made form. It does **not** close functions, aliases, modules or `PATH`;
- **detect and degrade**: an auto-approved shell call after which no call-mode request reaches the Hub under that
  run's token before the tool call completes withdraws case 2's standing for the rest of that run, returning it to
  the judge or cards. The shim would mark its requests (a header), and `--list`/`--help`/usage failures, which make
  no request, would degrade too, in the safe direction. This is the only measure that closes the venv and module
  triggers.

**R3's attack on the allow-list (task 0.2).** Each attempt below was run against `_lex`/`_words` as they are
(`mcp_server.py:1403-1505`) and against case 2 as now written. The PowerShell rows marked "measured" were run on
PowerShell 5.1.26100, with stand-in launchers that print their argv.

| attempt | outcome |
|---|---|
| `…; rm x`, `… && x`, `… \| x`, `… > f`, `… 2>&1`, a newline, CR | `;`, `&`, `\|`, `>`, `<`, the newline and CR are outside the set, so the result is `None` |
| `(…)`, `{…}`, `$(…)`, `@(…)`, a backtick, `$env:X`, `${X}`, `%X%`, `!X!` | `(`, `{`, `$`, `@`, the backtick, `%` and `!` are outside the set |
| `'create_task'`, `"…"`, a quote in the middle of a word, the PowerShell `--%` stop-parsing token | quotes and `%` are outside the set |
| `,` (array), `=` (assignment prefix `X=y aw-tool`), `#` (comment), `~`, `*`, `?`, `[` | outside the set |
| a tab, U+00A0, U+2028 (split by `_lex`'s `isspace`) | outside the set, which holds only the ASCII space |
| U+2013 en dash in `–list`; U+2018 and U+201C smart quotes, which PowerShell treats as quotes; fullwidth letters | outside an ASCII set. Measured: `–list` reaches argv unchanged. These are the rows an `isalnum`/`\w` implementation would get wrong, so test 1.6 carries two of them |
| `.\aw-tool`, `C:\…\aw-tool.cmd`, `\\host\share\aw-tool.cmd` (UNC) | word 0 is not exactly the name, so `None` |
| `. aw-tool …` (dot-source), `& aw-tool …` | word 0 is `.`, or `&` is outside the set |
| `aw-tool.cmd` in bash, `Aw-tool` in bash | refused (bash names are exact) |
| `AW-TOOL.CMD --list` in PowerShell | allowed. Measured: it runs the launcher |
| path `\\host\share\x.json`, `C:x.json`, `.agentweave\calls\..\..\x.json`, `.agentweave/calls/1.json:ads`, `…/1.json.` | leading separator, drive, `..`, `:` and suffix rules all give `None` |
| path `-x.agentweave/calls/1.json` behind a junction `-x.agentweave` → `.agentweave` | before R3 it resolved inside `calls/`, and was measured to reach argv as two arguments. It is now refused by the leading-`-` rule |
| path `.agentweave/calls/CON.json`, `NUL.json`, `COM1.json` | measured on this Windows 11 build: `realpath` keeps them inside `calls/`, and `open` raises `FileNotFoundError`, so they are ordinary names, not devices. Allowed, and harmless |
| numeric-looking words (`1kb`, `0x10`, `1e3`) | measured: passed to the native command unchanged. None is a tool name or a `calls/` path anyway |
| a foreign tool, `mcp__x__y` with `{"command": "aw-tool list_tasks", …}` | **allowed before R3** (unknown dialect, read both ways). Now `None`, because case 2 is limited to `_TOOL_DIALECTS` |
| a Copilot `edit` request that names no path (its `write_powershell` input to a running shell) | **allowed before R3** if a caller asked "every path passes" of an empty list. Now it needs at least one path, and slice 2 already rejects it (its D8) |
| `aw-tool create_task .agentweave/calls/1.json` after an earlier `$env:PYTHONPATH='.'` and a workspace `json.py` | **ran agent code before R3**, under an auto-approved call. Closed by `-I` (D5) |
| after an earlier `Set-Alias aw-tool x`, `function aw-tool {…}`, or a `PATH` prepend | the same text runs something else. **Not closable by the predicate**: this is the recorded residual above |
| (review) `.agentweave/calls` itself a junction to `.claude`, then a write of `.agentweave/calls/settings.json` | **allowed by R3's wording**, which compared against the resolved calls directory. Now `None` by the calls-root rule (review fix 1) |
| (review) after an earlier `$env:ComSpec = "<ws>\x.exe"`, `Import-Module .\m.psm1`, or `.venv\Scripts\Activate.ps1` | the same text runs something else. Residual, widened above (review fix 2) |

No attempt produced more than one plane call from text the predicate allows. Three produced something other than
"exactly one invocation of the Hub's launcher": the foreign tool, the empty edit and the interpreter-variable
poisoning. Each is closed above. The fourth, alias/function/`PATH`, is the residual.

**Callers.**
- `_decide`: the predicate is first, replacing the `mcp__agentweave__` line (`:1557-1558`).
- `approve_tool_call`'s operator branch: replacing its own copy of that line (`:1709-1710`). It runs before
  `_ask_operator`, so a predicate allow opens no card and computes no workspace verdict. **(rebase at IMPL:
  `an-ask-me-card-says-what-workspace-only-would-decide` unbuilt at R2.** It adds a guarded `_decide` verdict and a
  422 retry inside `_ask_operator`, `mcp_server.py:1630-1655`. The predicate sits before that call, so the two do
  not interact.)
- Slice 2's ACP `request_permission` handler: in every posture before `_decide` or the card, with
  `workspace=<run's work dir>`. R2 checked slice 2's D8 as currently written: it judges `kind:"execute"` as
  `_decide("PowerShell" if Windows else "Bash", {"command": rawInput.command})` and each `kind:"edit"` path as
  `_decide("Write", {"path": p})`. Those are exactly the names cases 2 and 3 read. Open question 6 is answered.
  R3: for an `edit` request the handler allows by standing only when the request names at least one path and
  `_hub_own_call("Write", {"path": p}, workspace=…)` holds for **every** path. Otherwise the whole request goes to
  its existing per-path judge. A standing allow for some paths and a judge for the rest would be two answers to one
  request, and ACP takes one.
- ~~Codex's `decide_approval`~~ **cut by R3 (group 6 removed).** R3 kept R2's recommendation, for reasons partly
  different from R2's:
  - The predicate cannot match what Codex sends without an unwrap. This is VERIFIED from the fixtures below.
  - The unwrap is a second quoting layer, Windows argv plus PowerShell `-Command` re-parsing. That is the class of
    reading R2's `()` finding came from.
  - The only evidence available is fixtures, because Codex is undrivable here, and Codex is not the work PC's
    runner.
  - Cutting costs little. Under "Workspace only", `decide_approval` already accepts a command approval whose `cwd`
    is inside the workspace (`codex_appserver.py:280-283`). Only "Ask me" puts a Codex shim call on a card, and that
    card works.

  **R2's second reason was wrong.** Codex's current configuration reference, read 2026-09-28
  (`learn.chatgpt.com/docs/config-file/config-reference`), says `shell_environment_policy.ignore_default_excludes`
  *"Keep variables containing KEY, SECRET, or TOKEN before other filters run (default: true)"*. So by default a Codex
  shell **does** keep `AW_RUN_TOKEN`. The network default for `workspace-write` is not stated there, and it stays
  unverified. R2's text, kept for the record: **R2 found that this caller, as R1 wrote it, cannot fire on
  Windows.** Codex's command approval carries the command *as its harness wrapped it*. The live captures
  in `hub/tests/test_codex_appserver.py:73` (`powershell -Command "Set-Content …"`) and `:141`
  (`"C:\…\powershell.exe" -Command 'echo …'`) show that word 0 is `powershell`, never `aw-tool`. Case 2 would
  therefore never match, and test 1.12 as R1 wrote it (a bare `aw-tool …` command) would pass against a shape
  Codex never sends. That is the F190 failure mode. Two further facts point the same way (open question 4):
  - the default `workspace-write` sandbox has network off;
  - Codex's default `shell_environment_policy` excludes variables whose names contain `TOKEN` (recalled Codex
    configuration documentation, not re-read this round; R3 verifies), so the shell would not see
    `AW_RUN_TOKEN`.

  Codex is undrivable on this machine (2026-08-29), so none of this can be measured. **R2 recommends cutting group
  6.** If it is kept, the Codex caller must first unwrap exactly one `<powershell|pwsh|bash|sh>[.exe]
  -Command|-c|-lc <one argument>` wrapper (lexed in the outer dialect, exactly three arguments), and then apply
  case 2 to the inner text. Test 1.12 must use the captured wrapped shape.
  **(rebase at IMPL: `an-ask-me-card-says-what-workspace-only-would-decide` unbuilt at R2.** It rewrites
  `decide_approval`'s workspace branch, `:280-283`, onto a new `workspace_verdict` helper. The Codex caller would
  sit above the `posture == OPERATOR_POSTURE` return at `:276-279`.)

**Decision reporting and counting (re-verified by R2 against the unbuilt changes' designs).**
- `a-run-records-that-its-calls-were-allowed` counts what reaches `POST /permission-decisions`.
  `_report_decision` (`mcp_server.py:1595-1614`) is called unchanged after every `approve_tool_call` decision
  (`:1715`), so a predicate allow is counted as allowed.
- On the in-process paths, that change's `on_decision` callback carries the count (its D3, Codex). Slice 2's ACP
  handler must call the same callback for a predicate allow as for any other decision. This is a requirement on
  slice 2's handler, recorded here.
- **(rebase at IMPL: `a-run-records-that-its-calls-were-allowed` unbuilt at R2.)** `_report_decision`'s body does
  not change there. The route (`agent_actions.py` `record_permission_decision`) gains the tally.

## D9. Copilot tests the run before its first prompt

VERIFIED today, Copilot 1.0.88 over ACP, with a stdio server `agentweave` passed with `--additional-mcp-config @file`:

| step | time (s, relative) |
|---|---|
| `session/new` sent | 0.000 |
| the server process starts (`server/discover`, `initialize`, `notifications/initialized`) | +0.636 |
| `session/new` returns | +1.848 |
| `/mcp list` prompt, 6 s later | answered in 4 ms with text `- agentweave (connected)`, and **no** `github.com/copilot/sessionEvent` notification although `session.mcp_servers_loaded` was subscribed |

The same probe with `--disable-mcp-server agentweave` never started the server (no log file) and `/mcp list`
said `- agentweave (disabled)`.

So the MCP server starts **inside `session/new`**, and the Hub sends the first prompt. That settles the brief's
question (*"these arrive only with the first prompt … decide how the first turn's notice handles not
knowing"*): **the first turn does not have to not-know.** The raw events are late. The announce is not.

**The sequence (slice 2's ACP transport, extended here):**
1. `session/new` (or `session/load`) returns.
2. `await mcp_announce.wait(run_id, timeout=MCP_ANNOUNCE_WAIT_SECONDS)`. This is `15` s: the pinned server's
   fastmcp import alone is about 1.4 s, and GitHub issue #4957 reports policy resolving fail-closed for about
   3 s on 1.0.88. `mcp_announce` is a new, tiny module:
   - a per-run `asyncio.Event` registry;
   - the announce route sets the event after its commit;
   - **`wait` registers its Event first, and only then checks `Run.mcp_adapter_online_at`** in a fresh session,
     because the announce can precede the wait. R1–R3 checked first and registered second (review fix 5,
     2026-09-28). An announce that committed between the two notified no one, and the run was recorded `absent` and
     told `shim` while it held MCP. By this section's own timings the announce is expected about +2–2.5 s after
     `session/new` is sent, and `session/new` returns at +1.85 s, so that window was the expected arrival time.
     Register-then-check closes it: an announce committed before the check is seen by the check, and one after it
     finds the Event registered. The wait also **re-checks the stamp at every poll step** (it already polls for
     `should_interrupt`), so a lost notification costs at most one poll interval;
   - `wait` is total. A database error in that check is logged and treated as "not yet", and the wait goes on to
     its timeout. So a failing check ends as `absent` + `shim`, the safe direction. It never fails the run (R2:
     the transport runs inside the trigger's executor, and an exception there fails the run).

   R2 on the 15 s (open question 2): the announce is posted from `main()`, after the module's fastmcp import (about
   1.4 s) and before the server answers `initialize`. The probe saw the server process start 0.64 s after
   `session/new` was sent, so the announce should land about 2–2.5 s after it. 15 s is a margin of about six
   times, kept until drive 9.2 measures the real gap.
3. `connected` → surface `mcp`. Timeout → `harness_mcp_status = absent`, surface `shim`, and then one prompt
   `/mcp list` (no model call). Its text is stored verbatim as a diagnostic (D12) and is not parsed for a
   decision. **R3:** that prompt's content is exactly one text block, `/mcp list`, and nothing else. Slice 2's D5
   puts the per-turn block ahead of every prompt, and a slash command that is not the prompt's first text is sent
   to the model as ordinary text. Slice 2's R2 left this gap to slice 3 (its round log, `:1347`). The transport
   therefore sends this one diagnostic prompt without the per-turn block, and every model prompt keeps it.
4. The access-path notice and the tool section are rendered **now**, for the surface just decided, and
   `session/prompt` is sent.

**R3: when there is no wait.** A Copilot run that was **not given** the server (slice 1's `tool_surface == "none"`,
from `hub_client: "cli"`) skips steps 2–3. Its surface is `shim`, it sends no `/mcp list`, and its status stays NULL.
Nothing was tested, and waiting 15 s for an announce that cannot come would only delay the turn. A run cancelled
during the wait ends untested (NULL), not `absent`. `should_interrupt` is honoured within the wait's poll, as slice
1's `run_turn` contract requires (*"within one poll interval"*), so `wait` takes the interrupt check, or polls in
steps of at most that interval.

Slice 2 composes the prompt in `trigger_agent_directly` before the transport starts, as the other runners do.
This slice changes that for a runner whose transport declares **`tests_mcp_before_first_prompt = True`**, a
`ClassVar[bool]` on both of slice 1's transport ABCs, `False` by default and `True` on slice 2's ACP transport
(slice 1's D16 places it on the transport, not on `RunnerAdapter`; contract reconciliation, 2026-09-28):
- such a runner is handed `render_surface(surface) -> list[str]`, which returns the notice and the tool section;
- `plane_surface` is written when that callable is invoked.

R3 pins the shape in slice 1's names. It is an `RpcCallbacks` field, `render_surface: Optional[Callable[[Literal["mcp",
"shim"]], list[str]]]`, set by the executor only when `transport.tests_mcp_before_first_prompt` is true. It is a
callback, not an `RpcTurnRequest` field, because it writes: `plane_surface`, and the context file below. It is
**total**. The rendering is pure. The two writes are best-effort: logged on failure, never raised. The prompt is what
the run is told, and failing the run after spawn over a record would be worse than a stale record. The transport
calls `mcp_announce.wait` itself. That module is a Hub-side import with no database session of the caller's.

**R3: the access-path notice leaves the pre-spawn `notices` too.** `notices = [access_path_notice(described_path)]`
(`agent_trigger.py:1173`) is joined into `prompt` at `:1194`. For such a runner, R2's design left that pre-spawn
notice in place, so the run would have received two access notices, the pre-spawn one possibly for the other
surface. The trigger omits it from `notices`, and `render_surface` supplies it. No other notice moves.

**Where the tool section goes for such a runner (rewritten by R2 against slice 2's D5).** Slice 2 already keeps the
tool section out of the custom-agent file. Its D5 splits `_render_hub_agent_context` into `stable` (to the agent
file) and `per_turn` (a text block in `session/prompt`), and `per_turn` **contains** `_tool_surface_lines`. R1
aimed `include_tool_surface=False` at the agent file, which is the wrong target.

The real problem is timing. Slice 2 renders `per_turn` in `trigger_agent_directly`, before spawn, from the pre-spawn
`described_path`. A runner that tests before its first prompt must not send that section. So:
- slice 2's D5 (R3) already renders the tool section as its own key and carries it as
  `RpcTurnRequest.tool_surface_context`, apart from `per_turn_context`. For such a runner the transport does not
  send the pre-spawn `tool_surface_context`; `render_surface`'s output replaces it. No `include_tool_surface` flag
  is added (contract reconciliation, 2026-09-28: R3 wrote one; slice 2 provides the separate field instead);
- `render_surface(surface)` returns the notice, then the tool section, and the transport puts both in the
  `session/prompt` content ahead of the operator's message;
- **the canonical context file** `.agentweave/context/<agent>.md` is written pre-spawn with the full `context`
  (`agent_trigger.py:1160-1169`, kept by slice 2's D5 as *"the materialized record of what the agent was told"*).
  For such a runner it would record a tool section the run was never sent, perhaps for the other surface. So for
  such a runner, `render_surface` also rewrites that file, with the section for the decided surface. The requirement
  *"A run is told the access path it actually has"* binds the canonical context to the same decision as the notice.
  A record that disagrees with what was sent breaks that.

**(rebase at IMPL: slice 2 `a-copilot-agent-runs-over-acp` unbuilt at R2.)** Slice 2's own R2 is running
concurrently and may move `per_turn`'s composition.

**Corroboration, after the fact.** Slice 2's `CopilotEventMapper` (via `COPILOT_RAW_EVENTS`) subscribes to `session.mcp_servers_loaded` and
`session.mcp_server_status_changed` (appendix A §A). This slice consumes them:
- the entry named `agentweave` with status `connected` or `failed` is a harness report (D1's precedence). R3 added
  `failed`: it is VERIFIED in appendix A §D, and it is how a run whose server started (so the announce came and it
  was told `mcp`) and then failed is recorded at all;
- any other status (`pending`, and whatever a policy block says) is stored as a diagnostic only.

**R2: this supersedes one line of slice 2.** Slice 2's D10 (*"The Hub's own server failing"*) emits, once per turn,
an `error` event `copilot_mcp_server_failed` carrying the text of Codex's `map_mcp_server_failure`
(`codex_appserver.py:547-567`): *"… failed to start, so this turn had no AgentWeave tools -- no messages, evidence,
task updates or questions"*. Once this slice lands, that sentence is **false** for a run told `shim`, because the run
has every operation through `aw-tool`. Left in, a blocked run would show the operator an error saying the agent
cannot collaborate, beside D12's statement that it was told `aw-tool`. So for a Copilot run, the non-`connected`
raw status becomes D12's diagnostic, and slice 2's error event is not emitted. Task 5.4 carries this. Codex's own
event is left alone: whether a Codex shell can reach the Hub is open question 4. **Review fix 6 corrects that last
sentence:** after D10, every Codex run with no grounds is told `shim`, so Codex's own message is reworded for a run
told `shim` (D12), not left alone.

**R3: narrowed, to agree with slice 2 as it now stands.** Slice 2's R2 wrote the opposite rule. Its D10 says
*"whichever lands second removes the duplicate, and this slice's once-per-turn error for the Hub's own server is the
one to keep"*. Both halves are right for different runs:
- **For a run told `mcp`** (the announce came, and the server then failed), slice 2's sentence is **true**. The
  run has no AgentWeave tools it was told about. Slice 2's event is kept, and it is that run's only statement. D12
  emits nothing more for it.
- **For a run told `shim`**, the sentence is false. D12's status event has already been stored at the wait's
  timeout, quoting `/mcp list`. Slice 2's event is suppressed.

So slice 2's mapper needs the run's told surface. Slice 2 carries it as `RpcTurnRequest.told_access_path` (its
D18). This slice lands second: for such a runner the transport replaces that value with the surface it passes to
`render_surface`, and the mapper reads it (contract reconciliation, 2026-09-28). Slice 2 keeps its code, its message and its once-per-turn rule.

A `Warning:` message chunk naming the server (`MCP server "agentweave" was blocked by your enterprise …`,
DOCUMENTED wording) is **not** parsed. It is already shown to the operator as text by slice 2's mapper, and the
Hub does not key on vendor prose.

**Resume.** Whether `session/load` also starts the servers is **INFERRED**. A probe was attempted today and could
not run, because a session holding only slash commands was not persisted (`-32002 Resource not found`). If it does
not, every resumed Copilot run would time out and be told `shim` while holding MCP. That is safe, since the shim
works, but it is wrong. Drive task 9.6 measures it on the second turn of a conversation.

## D10. Claude and Codex keep the latest-test rule, and their first run is told the shim

Claude's prompt is on its argv (`-p`, `runner_commands.py:287`), so its surface cannot be decided after the harness
starts. Codex's app-server could wait between `thread/start` and `turn/start`, but that is not needed for parity,
and Codex is not deployed on the work PC. It stays a named option (open question 3).

So for both, the notice and the tool section are decided before spawn from `latest_mcp_test` (D1), as today. The
one change is that **no grounds → `shim`**, where today it is HTTP. The requirement *"A run holding the tools is
not told it is empty"* still holds: the shim text asserts nothing about MCP (D11). F302's measurement (3 of 3
fresh first turns reached for MCP anyway) is why no conditional wording is added.

**The Codex caveat (review fix 6, 2026-09-28; R2's open question 4 sentence, which reached no task).** Every first
Codex run is now told `shim`, where before it was told the HTTP form, and whether a Codex shell under
`workspace-write` can reach `127.0.0.1` is unverified (D15). So the shim notice, rendered for a Codex run, carries one
more sentence: *"Your shell's sandbox may not allow network access to the Hub. If `aw-tool` reports `unreachable`,
say so in your reply rather than retrying."* It is keyed on the runner (slice 1's adapter), like the host-tool
sentence (D11). It is no worse than today's HTTP form, which has the same network question, and it stops the notice
asserting reachability as a fact for a runner where it is not known. The capability-plane scenario is scoped to
match (*"A run whose shell may not reach the Hub is told so"*). Task 5.2 carries it.

## D11. Runs are no longer told the raw HTTP form

`access_path_notice`'s non-MCP branch (`launchability.py:414-438`; the MCP branch is `:409-413`) and
`_tool_surface_lines`'s HTTP preamble (`agents.py:1547-1560`) are replaced by the call-command rendering.
**(rebase at IMPL: `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` unbuilt at R2.)** That change
gives `access_path_notice` and `_tool_surface_lines` a `tool_prefix`, so the MCP branch names
`mcp__agentweave__send_message` and so on for a Claude-family run. It also adds a host-`SendMessage` sentence,
keyed on the runner family alone and rendered after the preamble "in both forms". With this slice there are three
forms, and the sentence belongs in the shim form too: a Claude run told `shim` still has the host tool. Slice 1
then replaces its `CLAUDE_FAMILY_RUNNERS` with `adapter.mcp_tool_prefix` / `host_tool_note`. Reasons:
- **The HTTP form cannot be followed safely.** The model must write `Authorization: Bearer $AW_RUN_TOKEN` (or
  the value) into a command. On Copilot that command is stored as `rawInput`. F301 measured Claude refusing the
  interpolation shapes.
- **It is never the only path.** The shim exists wherever a run can be spawned: the same pin, and a spawn
  refused if the pin fails (D5).

The HTTP contract stays the application contract. The equal-capability requirement is unchanged in substance.

**What happens to the HTTP rendering code.** `_http_lines` (`agents.py:1484-1505`) and the `http_note` field
(`:983`, and its strings in `_operations()`) stay. They are rendered only when `access_path="http"` is passed
explicitly, which no run does. `test_tool_surface_matches_server.py` renders them (`:74`, `:355`, `:378`). Those
tests are today's only check that each described operation's method, path and fields match a mounted route.
Deleting the rendering would delete that check.

**R2: the key changes, and so do the tests.** Today *any* value other than `"mcp"` renders HTTP
(`over_mcp = access_path == "mcp"`, `agents.py:1541`, and `render = _mcp_lines if over_mcp else _http_lines`), and
the tests reach it with `"cli"`: `HTTP_PATH = "cli"` in `test_tool_surface_matches_server.py:36`, plus
`test_agent_facing_text.py:162` and `test_launchability.py:588` (`access_path_notice("cli")`). After this change,
`_tool_surface_lines` dispatches on exactly `"mcp"` / `"shim"` / `"http"` and raises `ValueError` on anything else.
`access_path_notice` takes exactly `"mcp"` / `"shim"`. A caller still passing `"cli"` then fails loudly in a test,
instead of silently rendering the form this change stops telling runs. The only route that renders context without
a run, `GET /agents/agent-context`, passes nothing and gets the `"mcp"` default. It cannot reach the `ValueError`.
Those tests move to `"http"`, or to `"shim"` where they assert what a run is told (task 5.2).

**The call-command rendering** (`_shim_lines`) reuses `_Operation.tool`, `.args`, `.text` and `.detail`. `.args`
is the MCP argument list, which `test_tool_surface_matches_server.py` already checks against the tool
signatures. Each line reads ``- `aw-tool send_message` — JSON keys: to_agent, content, … — <text>``.

The preamble names the one rule that maps every short tool name elsewhere in the turn onto the call command: the
checkpoint prompt, spec notices and the 35+ other mentions (R2 count in tonight's full-names change). It reads:
*"Every AgentWeave operation named anywhere in this turn by its short name — `create_task`,
`submit_spec_document`, … — is called as `aw-tool <name> <args-file>`."*

## D12. The operator sees how a run reached the Hub

- `RunFacts` (`hub/hub/schemas/agents.py:140-169`) gains `plane_surface` and `harness_mcp_status`, read from the
  row. `None` means untested or pre-change.
- When a run given MCP is recorded `absent` or `failed`, **one** `status` event is appended to that run's stream
  (existing kind, `runner_events.status_event`, `:221`). Its phase is `plane_surface`. **R3: its summary depends on
  what the run was told.** R2's single wording (*"… the run was told to reach the Hub with `aw-tool`"*) is false
  for every Claude and Codex run told `mcp` from history whose own test then came back negative. Those runs are told
  before spawn (D10), and the test is what a stale `connected` looks like when it fails:
  - `plane_surface == "shim"`: *"The AgentWeave MCP server did not start for this run (absent); the run was told
    to reach the Hub with `aw-tool`."*
  - `plane_surface == "mcp"`: *"The AgentWeave MCP server did not start for this run (failed), although the run
    was told to use it."*, followed by **one of two** second sentences (review fix 7, 2026-09-28):
    - no `hub_client` declaration: *"Its next turn is told `aw-tool`."* That is true for Claude, from the latest test;
    - `hub_client: "mcp"` declared: *"This agent is declared to use MCP (`hub_client: "mcp"`), so its next turn is
      told the same; change the declaration to stop that."* R1–R3's unconditional "next turn is told `aw-tool`" was
      false under a declaration, because a run described before spawn follows the declaration (D1, *The operator's
      declaration*).

    For Copilot, which tests every turn, this wording is never used, because slice 2's event carries this case (D9).
  - A runner that already reports the failure in its own words emits no second statement: Codex `failed`
    (`map_mcp_server_failure`), and Copilot told `mcp` (slice 2's `copilot_mcp_server_failed`).
  - **Codex told `shim` (review fix 6, 2026-09-28).** `map_mcp_server_failure`'s own-server text (*"… so this turn had
    no AgentWeave tools -- no messages, evidence, task updates or questions"*, `codex_appserver.py:557-561`) is false
    for a run told `aw-tool`, the same defect D9 fixed for Copilot, and it would break `runtime-diagnostics`'
    *"naming the surface the run was actually told to use"*. After D10 every Codex run with no grounds is told `shim`,
    so this is the common case. `map_mcp_server_failure` gains a keyword `told_access_path`, passed through
    `run_turn` from the request. For `"shim"` the own-server message reads *"The AgentWeave MCP server ({name})
    failed to start; this run was told to reach the Hub with `aw-tool`: {detail}"*. The code
    (`codex_mcp_server_failed`) and the once-per-turn emission are unchanged, and it stays the one statement: D12
    emits nothing more for Codex. For `"mcp"` the text is today's, which is then true. Task 2.6 carries it.
  - **A late Copilot announce (review note 10).** An announce after the wait makes the record `connected`, while
    the event already stored says the server did not start. The event is not withdrawn. It was true when written:
    the run was told `aw-tool` because nothing arrived in time. The run's facts show the final record.

  On Copilot the `shim` wording gains a second sentence quoting the `/mcp list` line for `agentweave` verbatim
  (vendor text, bounded by `_truncate_utf8`).
- The event is written **once per run**, not per status change. No new event kind and no UI change, so no bundle
  refresh.
- `RunFacts` is built at `agents.py:898` and `agent_chat.py:341` (R2 rebase; R1 had `:904` and `:351`).

## D13. Claude parity (task group 7, severable)

- **The problem.** On Claude's `cli` path (`hub_client: "cli"`, `acceptEdits`, no approver) a shell command that
  needs approval is denied, because nothing answers (F301's last rows). Under F299's condition A (MCP blocked,
  approver named) the run dies at its first approval-needing call.
- **The fix.** For non-yolo Claude runs, `_build_claude_command` adds `Bash(aw-tool:*)` and
  `PowerShell(aw-tool:*)` to `--allowedTools`, **whether or not MCP is injected**. Two things are DOCUMENTED for
  Claude Code: prefix rules are shell-operator-aware (`safe-cmd && other` does not match `Bash(safe-cmd:*)`), and
  allow rules apply in every permission mode but bypass. Two things are **INFERRED**: that `PowerShell(...)` takes
  the same rule syntax, and that the analyser passes `aw-tool x .agentweave/calls/1.json`, which has no `$`,
  braces or subexpressions (F301's refusal classes). Drive task 9.8 measures both.
- **The result, if the drive holds.**
  - F301 closes for Claude: the plane is reachable on the `cli` path.
  - Under F299 condition A the plane is reachable, but file writes still die. **F299 stays open for Claude**, and
    the containment choice stays the operator's (`DECISIONS.md` 2026-09-13 1b; F339).
- **The rule restricts no path, so the shim does (review fix 8, 2026-09-28).** `Bash(aw-tool:*)` matches `aw-tool
  <tool> <any path>`, so on the `cli` path it is wider than D8's case 2. The shim's own calls-root check (D3, *Where
  the file may be*) makes the two approvers mean the same thing: `aw-tool create_task C:\elsewhere\x.json` runs,
  but reads nothing and exits `usage`.
- **If group 7 is cut,** delete the ADDED requirement *"A Claude run pre-allows the Hub's call command"* from
  `specs/agent-run-sandboxing/spec.md`, and F301 stays open for Claude.

## D14. `.agentweave/calls/`

- The Hub creates `<effective_work_dir>/.agentweave/calls/` beside `.agentweave/context/`
  (`agent_trigger.py:1160-1169`) on every turn.
- **How it is made and checked (review fix 1, 2026-09-28).** A plain `mkdir(exist_ok=True)` leaves an existing
  junction or symlink in place (VERIFIED: `New-Item -Force` of the directory over a junction succeeds and the junction
  stays). So the per-turn step is:
  1. If `.agentweave/calls` exists and `normcase(realpath(p)) != normcase(p)` for its unresolved path `p` (built on
     `realpath(work_dir)`), or it is not a directory, the Hub **removes the link itself, never its target's
     contents** (`os.rmdir` for a directory junction or directory symlink on Windows, `os.unlink` for a POSIX
     symlink or a file), then creates a real directory. VERIFIED 2026-09-28: `os.rmdir` on the junction removed it
     and left the target's files in place. `calls` is the Hub's own; nothing else belongs there.
  2. If `.agentweave` itself is a link, the Hub does **not** replace it: it may hold the project binding
     (`.agentweave/project.json`). It creates nothing through it, logs a warning, and the turn proceeds. The
     calls-root rule then never matches for that workspace, so every `aw-tool` call and args-file write is decided
     as it would be without this change (the judge, or a card). The shim refuses to read, with a readable `usage`
     error. The safe direction, and visible.
  3. A removal or creation that raises `OSError` refuses the turn with the context write's existing refusal, as
     today's context write does.

  This is belt and braces. The predicate and the shim check the root at every decision and every read, whatever the
  Hub made at turn start, because the run can make a junction mid-turn.
- `repo_hygiene.EXCLUDE_PATTERNS` (`repo_hygiene.py:59-85`) gains `.agentweave/calls/`, so `snapshot_worktree`'s
  `git add -A` never commits call arguments.
- The files are not deleted by the shim, because the agent may reuse them. They are the agent's scratch, inside
  its workspace.

## D15. What is verified, documented and inferred

| claim | status |
|---|---|
| Copilot starts a `--additional-mcp-config` stdio server inside `session/new`, before any prompt | **VERIFIED** today (run1.log, tsrv.log) |
| `--disable-mcp-server agentweave` leaves the server unstarted; `/mcp list` says `(disabled)` | **VERIFIED** today (run2.log) |
| A `/mcp list` slash prompt makes no model call, answers in ms, and forwards no raw event | **VERIFIED** today |
| Raw `session.mcp_servers_loaded` arrives on the first model prompt | VERIFIED in the exploration (acp4) |
| A policy block shows as a `Warning:` text chunk and a non-`connected` status | DOCUMENTED + INFERRED (appendix A §D) |
| `session/load` starts the servers again | **INFERRED** (drive 9.6) |
| PowerShell 5.1 `@` parse error; inline-JSON quote loss; relative path passes intact | **VERIFIED** today |
| `aw` is the agentweave console script | **VERIFIED** today |
| fastmcp import costs 1.4 s per process; stdlib 0.1 s | **VERIFIED** today |
| Copilot's `powershell` tool inherits `copilot.exe`'s env and `PATH` | INFERRED (drive 9.3) |
| Copilot routes an `aw-tool` command to `request_permission` (not a read-only command) | INFERRED from the documented rule "non-read-only shell always asks" (drive 9.3) |
| Managed `deniedMcpServers` needs `%ProgramFiles%\GitHubCopilot\managed-settings.json` or HKLM, so admin | DOCUMENTED (appendix A §D). The local drive simulates with `--disable-mcp-server` instead |
| Claude `init` omits a `deniedMcpServers`-blocked server | VERIFIED in F340 (`--settings`, 2.1.269) |
| Codex app-server reports its MCP servers as `mcpServer/startupStatus/updated` `starting\|ready\|failed\|cancelled` | VERIFIED (live captures cited at `codex_appserver.py:655-657`, `:1167-1183`; `test_codex_appserver_run_turn.py:555-590`) |
| A Codex command approval's `command` is the wrapped shell line (`powershell -Command "…"`), not the model's bare command | VERIFIED (captured fixtures, `test_codex_appserver.py:73`, `:141`) |
| ~~Codex's shell drops `*TOKEN*` variables by default~~ **False (R3):** `ignore_default_excludes` defaults to `true`, so `*TOKEN*` variables are kept | DOCUMENTED (Codex configuration reference, read 2026-09-28) |
| Codex's `workspace-write` sandbox has network off by default | not stated in the configuration reference; unverified; Codex undrivable here |
| PowerShell 5.1 resolves a bare `aw-tool` to `aw-tool.cmd` over an extensionless `aw-tool` in the same directory | **VERIFIED** (R3, 5.1.26100, `Get-Command -All`) |
| PowerShell 5.1 splits a native argument that begins with `-` and contains `.` (`-x.a/b` → `-x`, `.a/b`) | **VERIFIED** (R3) |
| `CON.json`/`NUL.json`/`COM1.json` are ordinary file names on this Windows 11 build | **VERIFIED** (R3: `realpath` stays inside; `open` raises `FileNotFoundError`) |
| An announce can precede a failed connection (`main()` announces before `mcp.run`) | CODE (`mcp_server.py:2091-2094`) |
| Copilot's shell tool is a persistent session with `mode sync\|async` and `initial_wait` | CODE (`app.js` 1.0.88, tool help table) |
| A directory junction on `.agentweave/calls` makes `realpath(calls)` its target; a per-turn `New-Item -Force` leaves it; `os.path.islink` is `False` for it on 3.11 | **VERIFIED** (review fix 1, 2026-09-28) |
| `os.rmdir` on a directory junction removes the junction and keeps the target's files | **VERIFIED** (2026-09-28) |
| PowerShell 5.1 bare `Set-Content` writes the ANSI code page (em dash → `0x97`); `-Encoding utf8` writes UTF-8 with a BOM | **VERIFIED** (review fix 3, 2026-09-28) |
| PowerShell 5.1 runs a `.cmd` through `%ComSpec% /c`, and an absolute `ComSpec` set earlier in the session replaces `cmd.exe` | **VERIFIED** (review fix 2, 2026-09-28) |
| `Import-Module` of a workspace module, or a venv `PATH` prepend, makes a bare `aw-tool` run workspace code | measured by the review (2026-09-28), not re-run here |
| Plan mode blocks a Copilot `create` of `.agentweave/calls/*.json` | unmeasured; D16 avoids depending on it |

## D16. A specification turn told `shim` keeps the one write it needs (review finding 4, 2026-09-28)

**The gap.** A specification turn removes every file-write tool, as a declared nudge:
- Claude: `--disallowedTools Edit,MultiEdit,Write,NotebookEdit` (`runner_commands.py:229`, slice 1's
  `restrict_spec_writes`);
- Copilot: `--excluded-tools=apply_patch,create,edit,str_replace,str_replace_editor` plus Plan mode (slice 2 D9).

A spec turn told `shim` (every Copilot spec turn on the work PC) must write `.agentweave/calls/*.json` to call
`submit_spec_document`. Without a file tool it must write it from the shell. That write is neither case 2 nor case 3,
is denied on Claude's `cli` path (no approver), may be blocked by Plan mode (unmeasured), and meets fix 3's encoding
trap. R1–R3 never mentioned spec turns. The spec flow would be unusable exactly where this change is for.

**Options weighed.**
- *Tell a spec turn MCP.* Not an option where it matters: a run told `shim` is one whose MCP is absent or untested.
- *One card per args file on spec turns.* Needs a file tool to be asked about, which the turn does not have, and
  Claude's `cli` path has no one to ask.
- *The spec flow is MCP-only on locked-down machines.* Gives up the fire test's spec half.
- **The args-file write is the one write a spec turn keeps. Chosen.** It is the cleanest: the restriction's purpose
  is "do not implement", and a `.json` data file in the Hub's own git-excluded directory implements nothing.

**What it means per runner.**
- **Claude** (stream transport; the surface is decided before spawn, D10). When `restrict_spec_writes` is set **and**
  the run is described `shim`, `--disallowedTools` is `Edit,MultiEdit,NotebookEdit`: `Write` stays. Claude's permission
  rules have no negation, so `Write` cannot be confined to the calls directory by the harness. On a run described
  `shim` there is usually no Hub approver either (the approver is the same MCP server). So for that turn the nudge
  against `Write` is weaker: `Edit`/`MultiEdit`/`NotebookEdit` are still removed, and `Write` is decided by the posture
  (the workspace judge, a card, or `acceptEdits` on the `cli` path). This is stated, not hidden: the restriction was
  already *"a nudge, not a sandbox: `Bash` is not named either"* (`runner_commands.py:224-229`). A run described `mcp`
  keeps today's four-tool list.
- **Copilot** (RPC transport; the surface is decided *after* spawn, D9, but the argv is built at spawn). So the
  exclusion cannot depend on the surface:
  - on **every** Copilot spec turn, `create` leaves the `--excluded-tools` list (`apply_patch,edit,str_replace,
    str_replace_editor` stay excluded);
  - on a spec turn the ACP handler answers **every `edit`-kind request** itself: allowed by standing when it names at
    least one path and every path passes D8 case 3, and `reject_once` otherwise, **in every posture**. That is
    stronger than today's nudge, because it is the Hub's own answer, not a tool list;
  - so that such requests reach the handler at all, a spec turn does not set `allow_all` on under full access; the
    handler answers every non-`edit` request ALLOW itself, which is what full access means for them;
  - **Plan mode** (`session/set_mode`) is sent **after** the wait, and only when the run is told `mcp`. Whether Plan
    mode blocks the args-file write is unmeasured, and for a `shim` spec turn the handler's rule above replaces it.
    Slice 2's `SPEC_TURN_USES_PLAN_MODE` switch stays for the `mcp` case.
- **Codex.** Unchanged: `restrict_spec_writes` does not reach Codex app-server today (slice 1 D3/D11, a declared gap).

**The notice** for a spec turn told `shim` names the file tool for the args file (UTF-8, fix 3). Drive 9.10 makes one
Copilot spec turn told `shim` submit a document. Test 1.15 covers both runners' launch and the handler's spec-turn rule.

## Round log

- **R1, 2026-09-27.**
  - **Read:** the brief; the exploration and appendices A, B and C; `DECISIONS.md` ghcp-d1..d6; F299, F300,
    F301, F302, F339, F340 and F354 in full; the archived `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`
    (proposal headers, design D3/D4/D5/D11/D12); slice 1's `proposal.md` as it stood mid-afternoon;
    `.claude/rules/mcp-server.md`, `db-migrations.md` and `cli.md`.
  - **Code:** `launchability.py:220-440`; `mcp_server.py:1-200`, `:360-525`, `:860-1110`, `:1500-1740` and
    `:2060-2107`; `tool_server.py`; `agent_trigger.py:1090-1420`; `agents.py:925-1010` and `:1472-1620`;
    `agent_actions.py:459-483`; `runner_commands.py:55-110` and `:175-290`; `runner_parsing.py:51-56` and
    `:229-260`; `codex_appserver.py:100-135` and `:244-300`; `repo_hygiene.py:55-120`;
    `run_task_binding.py:905-960`; `schemas/agents.py:125-170`; `models.py:1225-1250`; `pyproject.toml:80-83`.
  - **Probes, no model call:**
    - Copilot 1.0.88 ACP `initialize` + `session/new` + `/mcp list`, with and without
      `--disable-mcp-server agentweave`;
    - an attempted `session/load` of a slash-only session, which was not persisted;
    - PowerShell 5.1 and Git Bash argument passing to a `.cmd`/sh stand-in;
    - fastmcp import timing.
  - **Found against the exploration:** the name `aw` is taken; `--json @file` cannot be typed in PowerShell;
    inline JSON loses its quotes; the first Copilot turn *can* know its surface (the server starts in
    `session/new`); raw events do not arrive on slash prompts.
- **R2, 2026-09-28** (task 0.1; an independent re-derivation from the code, on master `ef55e6f`).
  - **Drift, stated.** Task 0.1 asks for the tree "the night ORDER and slices 1–2 leave". That tree does not exist
    yet. Five of the 2026-09-27 ORDER's 28 changes had landed: `a-runner-choice-names-its-model`,
    `an-estimate-that-misses-turns-says-so`, `a-model-alias-is-a-model-choice`,
    `the-codex-models-offered-are-the-ones-its-cli-lists`, and `a-firing-is-counted-once-however-many-agents-it-starts`.
    None of them touches a site here. Still unbuilt under `openspec/changes/`:
    - `a-claude-run-is-told-its-agentweave-tools-by-their-full-names`;
    - `an-ask-me-card-says-what-workspace-only-would-decide`;
    - `a-run-records-that-its-calls-were-allowed`;
    - `the-permissions-pill-shows-the-posture-the-run-gets`;
    - `a-runner-that-cannot-collaborate-says-so-where-it-is-bound`;
    - slice 1 and slice 2 (each has its own R2 running concurrently).

    Every `file:line` is therefore today's. Each site one of those will move is marked "(rebase at IMPL: … unbuilt
    at R2)", with the expected post-landing shape taken from that change's design as written today.
  - **Read (code):**
    - `launchability.py:225-440`;
    - `mcp_server.py:1-210`, `:1000-1089`, `:1395-1734`, `:2060-2107`, and the list of `@mcp.tool()` / `raise`
      sites;
    - `agent_trigger.py:1095-1310`, plus greps for `:2451`, `:2920-3021`, `:3102`;
    - `agents.py:235-265`, `:950-1020`, `:1480-1575`, `:2110-2134`;
    - `agent_actions.py:459-483`, `:971`;
    - `codex_appserver.py:95-300`, `:535-567`, `:650-660`, `:1155-1195`;
    - `runner_commands.py:199-290`;
    - `tool_server.py` whole;
    - `workspace_writes.py:30-55`;
    - `repo_hygiene.py:55-120`;
    - `schemas/agents.py:140-170`;
    - `runner_parsing.py` symbol greps;
    - `pyproject.toml:80-83`;
    - `src/agentweave/cli.py` `cmd_*`;
    - the migration head (`0110`).
  - **Read (tests):**
    - `test_codex_appserver.py:60-90`, `:130-160`;
    - `test_codex_appserver_run_turn.py:555-600`;
    - `test_tool_surface_matches_server.py` greps;
    - `test_launchability.py`, `test_agent_facing_text.py` greps;
    - that every test file the tasks name exists.
  - **Read (changes):**
    - slice 1 `design.md` D3, D4, D5 and D16;
    - slice 2 `design.md` D3, D4, D5, D8 and D10, and its open-changes table;
    - slice 5 `design.md` D2 and D3, and `:375-390`;
    - slice 4 grep;
    - the five night-ORDER changes named in `proposal.md` (their design Decisions sections);
    - F340 in `scripts/drive/FINDINGS.md`.
  - **Probe (no model call):** `copilot help`, and `app.js` 1.0.88 searched for the shell tool's parameters.
  - **Wrong, and changed:**
    1. **D5:** the pin is materialized only when `access_path == "mcp"` (`agent_trigger.py:1195-1203`), so R1's
       "no run has MCP but not the shim, or the reverse" was false for `cli` runs. Now the pin and launcher are
       made for every run.
    2. **D8 case 2:** the deny-list missed grouping. `aw-tool list_tasks (.agentweave/calls/1.json)` in PowerShell
       lexes to the three accepted words, because `_ARGUMENT_ENDS` includes `()` (`mcp_server.py:1061`), and it runs
       the path as a command. Replaced by a character allow-list.
    3. **D8 case 3:** `write_tool_kinds` cannot be read from the standalone `mcp_server.py`. Claude's write tools
       are restated, with an agreement test.
    4. **D8:** the predicate needs `workspace=`, because two callers run in the Hub process (slice 2's D8 makes the
       same change to `_decide`).
    5. **D8, Codex:** approvals carry the wrapped `powershell -Command "…"` line (captured fixtures), so R1's caller
       could never match, and its test would have used a shape Codex never sends. R2 recommends cutting group 6;
       the unwrap needed if kept is specified.
    6. **D4:** call mode must never announce, or a shim call records `connected` and re-creates F340.
    7. **D3:** added an `internal` kind (exit 70) for exceptions `_hub_request` does not wrap (`TimeoutError` on
       read, `ValueError` on a non-JSON 2xx).
    8. **D9:** slice 2 already keeps the tool section out of the agent file (its `per_turn` holds it), so R1's
       `include_tool_surface=False` was aimed at the wrong target. The real need is to keep it out of the
       pre-spawn `per_turn` and to rewrite the canonical context file when the late decision is made.
    9. **D9/D12:** slice 2's `copilot_mcp_server_failed` error text (*"no AgentWeave tools"*) becomes false for a
       run told `shim`, so it is superseded for Copilot.
    10. **D1:** Codex's negative source is `mcpServer/startupStatus/updated` (already parsed). The
        "completed-without-announce → absent" guess is dropped.
    11. **D11:** HTTP rendering is keyed on exactly `"http"`. Today every non-`mcp` value renders it, and three
        tests pass `"cli"`.
    12. **D1:** `described_access_path` must return `shim` for a `cli`-given run as well (`:311-312`).
    13. Line rebases: `_decide` `:1557-1558`; `approve_tool_call` `:1705-1712`; `UNDESCRIBED_TOOLS` `:989-999`;
        HTTP preamble `:1547-1560`; `_http_lines` `:1484-1505`; the `_tool_surface_lines` call `:2126`;
        `RunFacts` `agents.py:898`, `agent_chat.py:341`; `repo_hygiene` `:59-85`; notice branch `:414-438`.
    14. **Tasks:** test files `test_runner_commands*.py` (does not exist, now `test_agent_default_permission_mode.py`)
        and the env test (`test_agent_trigger.py:713`).
  - **Confirmed as R1 had them:**
    - `launchability.py:252-280`; `runner_parsing.py:229`/`:371`; `agent_actions.py:459-483`;
    - `mcp_server.py:18-21`, `:70-77`, `:164-200`, `:1005`, `:1009`, `:1072`, `:2094`, `:2106`;
    - `tool_server.py:39-56`; `agent_trigger.py:1160-1169`, `:1246`, `:1292`;
    - `runner_commands.py:262`, `:287`; `codex_appserver.py:244-300`; `pyproject.toml:82`;
    - five `cmd_*`; `schemas/agents.py:140-169`; `runner_events.status_event` `:221`.
  - **Slice 1 names (its `design.md` as written):**
    - `AccessAxes.tool_surface` (`"mcp"|"none"`), `.approvals` (`"mcp_permission_tool"|"rpc"|"none"`) and `.plane`
      (`"mcp"|"cli"`) match D1's usage;
    - `posture_at_rest(axes, *, yolo)` reads `axes.approvals`, which this slice does not feed.
    - **Mismatches** (slice 1 owns the fix):
      - its D16 reserves an adapter member `shim_allowed(command) -> bool`. This slice uses the module predicate
        `_hub_own_call` in `mcp_server.py` instead, because the approver that runs it is spawned standalone and
        cannot import adapters. The member should be retired;
      - its D16 says slice 3 resolves axis 1 per run. This slice changes only what is *told*, and axis 1 stays
        `hub_client`-only.
    - `tests_mcp_before_first_prompt`: slice 2 agrees that this slice adds it (slice 2 `:882`).
  - **Slice 2 names:** match D8, as described in the D8 callers list (`PowerShell`/`Bash` + `command`; `Write` +
    `path`).
    - `copilot.exe` gets the whole run env, and the MCP config has no env block (its D3). Task 5.1 is answered by
      design and re-checked at IMPL.
    - Prompt composition: `per_turn` is rendered pre-spawn in the trigger (its D5); see correction 8.
  - **Open questions:**
    - 1: kept (answered below);
    - 2: reasoned, still measured in 9.2;
    - 3: answered;
    - 4: answered as far as the machine allows (group 6 recommended cut);
    - 5: partly answered, rest carried;
    - 6: answered;
    - 7: carried to the Opus review, with the new session-state residual.
  - **Cross-slice gaps** (other agents own these files; not edited):
    1. Slice 1 D16: the two rows above.
    2. Slice 2 D5: `per_turn` must be renderable without the tool section, and the context file must be rewritten
       after the late decision.
    3. Slice 2 D10: `copilot_mcp_server_failed` is superseded for Copilot.
    4. Slice 2 D8: the ACP handler calls `_hub_own_call(…, workspace=…)` first, and reports a predicate allow through
       `a-run-records-that-its-calls-were-allowed`'s `on_decision`.
    5. Slice 5 D2 (the operator-overrule path) assumes a *"hook call mode"* taking an event name. This slice provides
       none: call mode is closed over the MCP tools, reads a file, and refuses stdin. Slice 5 would add its own
       mode and route.
    6. Slice 5 (`:385`) says *"slice 3's MCP status handling surfaces"* a failed **GitHub** MCP server. This slice
       records and reports only `agentweave`, so slice 5 must surface other servers itself.
    7. Slice 4: no dependency found.
- **R3, 2026-09-28** (task 0.2; a second independent re-derivation, on master `fc33ff9`).
  - **Tree.** `ef55e6f..fc33ff9` is R2's documents only. The five night-ORDER changes and slices 1 and 2 are still
    directories under `openspec/changes/`, so every "(rebase at IMPL: … unbuilt at R2)" marking still holds. R3 kept
    them all and added none.
  - **Read (code, first, before R2's entry):**
    - `mcp_server.py:1000-1740` (`_lex`, `_words`, `_judge_word`, `_decide`, `_ask_operator`, `approve_tool_call`)
      and `:2060-2107` (the announce and `main`);
    - `agent_actions.py:455-490`;
    - `agent_trigger.py:1100-1335` (the grounds call, notices, pin, env, the `Run(...)` row) plus greps for the
      executors;
    - `codex_appserver.py:244-300`;
    - `runner_parsing.py:424-520`;
    - `test_codex_appserver.py:68-78`, `:138-144`.
  - **Read (designs):**
    - this change whole;
    - slice 1 D4 and D16 and its round-log requests (`:178-232`, `:420-431`, `:538-595`);
    - slice 2 D5, D8, D10 and D18, and its R2 gap list (`:308-360`, `:420-460`, `:520-565`, `:640-660`,
      `:985-1000`, `:1340-1352`);
    - slice 5 D2 fallback, its GitHub-server paragraph and its contract table (`:105-135`, `:644-660`, `:688-694`,
      `:850-858`);
    - appendix A §D and appendix C's detection signals.
  - **Probes (no model call):**
    - PowerShell 5.1.26100 with stand-in launchers (`aw-tool.cmd` plus extensionless `aw-tool`, both printing
      argv) first on `PATH`: resolution order, `\` paths, `AW-TOOL.CMD`, the `-x.y` split, numeric words, the en
      dash;
    - Python `realpath`/`open` on device-named `.json` files;
    - Codex's configuration reference (WebFetch).
  - **Attack on D8 (task 0.2): 20 attempts, recorded in D8's table.**
    - No allowed text yields more than one plane call.
    - Three holes in the rule *around* the allow-list were closed:
      - case 2 accepted any tool with a `command` key, a foreign MCP tool included;
      - case 3 was vacuously true for a path-less edit;
      - `PYTHON*` variables could redirect the auto-approved program (now `-I`).
    - One word-vs-argv mismatch was closed: the PowerShell `-x.y` split (the path may not begin with `-`).
    - The ASCII set is now explicitly not `isalnum`/`\w`.
    - The predicate is now total. The reason is what its two callers return when it raises: a FastMCP tool error, and
      slice 2's `reject_once`.
  - **D1 against how each runner ends.**
    - **"`connected` is final" was wrong.** The announce precedes `mcp.run` (`mcp_server.py:2091-2094`). So
      "started, then failed" recorded `connected` on every run: F340's latch one level down. It is replaced by a
      source precedence (harness report > announce > wait).
    - An unknown Claude `init` status is ignored rather than stored `failed`, which would now outrank a real
      announce.
    - Copilot raw `failed` is now a report.
    - "Untested" gains: Copilot cancelled mid-wait, and a Copilot run not given the server, which now skips the wait.
    - **F340 is not closed for Codex `exec`** (no negative source), and `proposal.md` said "every runner".
    - Every recorder is best-effort inside the executors, so a failing write never fails a run.
  - **Also wrong, and changed:**
    - **D12:** the status event's single wording was false for a Claude/Codex run told `mcp` from history. The wording
      now depends on the told surface, and a runner's own failure event is not doubled.
    - **D9:** the pre-spawn `notices` kept an access notice for a runner that renders one late, which would have
      sent two. The `/mcp list` prompt must be sent without slice 2's per-turn block (slice 2's gap to this slice).
      `render_surface` is total and is an `RpcCallbacks` field.
    - **Test 9.7 and the test guide** read "the stored prompt". The Hub persists no composed prompt: `prompt` is
      built at `agent_trigger.py:1194` and passed at `:1217`/`:1403`, and `Run` has no prompt column. They now read
      `plane_surface` and the canonical context file.
    - **Test 1.3's second half** must spawn without `-I`, or `PYTHONPATH` is ignored and the fastmcp stub proves
      nothing.
  - **Disagreements with R2:**
    1. R2's Codex `*TOKEN*` premise is contradicted by the current vendor reference. R3 still cuts group 6, on the
       other reasons.
    2. R2's "unknown `init` status → `failed`" and "`connected` is final" (inherited from R1) are replaced, as above.
    3. R2's D9/D10 "slice 2's error is not emitted for Copilot" is narrowed to runs told `shim`. For a run told `mcp`
       it is true, and it is kept (slice 2's R2 wants it kept).
    4. R2 called the predicate "strictly narrower than what `_decide` allows under `workspace`". That is true of case
       2 only once it is limited to shell tools. For an unknown tool it was not narrower under "Ask me".
  - **Group 6: cut.** Tasks 1.12 and 6.3 are removed. D8's caller is struck. The sandboxing requirement's first line
    is narrowed (open question 8). `proposal.md` is updated.
  - **Contract resolutions:** the next section.

- **Contract reconciliation, 2026-09-28** (a textual pass over the five slices' contract sections after their
  concurrent R2/R3 rounds; not a design round; no code read). Changed here:
  - D9, *Required of slices 1, 2* and task 5.4: `tests_mcp_before_first_prompt` is a `ClassVar` on the
    transports (slice 1 D16), not on `RunnerAdapter`.
  - D9, *Required of slice 2* item 2, tasks 5.3/5.4: no `include_tool_surface` flag; slice 2's separate
    `RpcTurnRequest.tool_surface_context` is withheld and replaced by `render_surface`'s output.
  - D9, *Required of slice 2* item 4, task 5.4: the mapper's told surface is slice 2's `told_access_path`,
    replaced by the transport with the surface it passes to `render_surface`.
  - `map_events` for Copilot renamed to slice 2's `CopilotEventMapper` (D1, D9, item 5, task 5.4); D8 case 1's
    `title` identification replaced by slice 2's `calls` map.
  - *Required of slice 1*: `render_surface` type and the `AccessAxes`/axis-1 items marked agreed (slice 1 R3).
  - Open question 10: **contract conflict** with slice 2's `"Shell"` key, left open.

- **Review fixes, 2026-09-28** (task 0.3: applying `spec-queue/tracks/reviews/ghcp-s3-2026-09-28.md`, Opus, APPROVE
  WITH FIXES, on master `450de52`). Each blocking and should-fix finding was re-verified before it was applied.
  Probes ran only under `%TEMP%\claude\s3fix\` (PowerShell 5.1.26100, Python 3.11); no copilot, claude or codex
  process was spawned. Code re-read: `mcp_server.py:1105-1135`, `:1555-1575`; `launchability.py:295-316`;
  `runner_commands.py:222-232`; `codex_appserver.py:545-565`; slice 1 D3/D6 and slice 2 D8/D9 on `restrict_spec_writes`.

  | # | finding | verified | done |
  |---|---|---|---|
  | 1 | BLOCKING: a junction on `.agentweave/calls` turns case 3 into "write any `.json`" | **yes**: junction → `.claude`, `realpath(calls)` is `.claude`, `New-Item -Force` leaves it; also `os.path.islink` is `False` for a junction on 3.11 | D8 *calls-root rule* (unresolved root, root must equal its realpath, file inside by `commonpath`), used by cases 2 and 3 and the shim; D14 per-turn replacement of a `calls` link (`os.rmdir` VERIFIED to keep the target's files), `.agentweave` link left with a warning; sandboxing requirement body + scenario *"A calls directory that is itself a link…"*; tasks 1.4, 1.6, 1.8, 4.2 |
  | 2 | residual wider than stated; the `-I` spec sentence false | **yes** for `ComSpec` (a python.exe copy as `ComSpec` ran in place of `cmd`); the module/venv/`.pth` rows taken from the review | D8 residual rewritten (ComSpec, AutoRun, `.pth`, loader variables, functions/modules/venv `PATH`, profile; Copilot-specific); `-S` **adopted** (D5, proposal, tasks 1.3, 1.7, 4.1); spec sentence now claims only interpreter variables and states the shell residual; `.exe` launcher and detect-and-degrade put to the operator with open question 7 (options a–d, recommendation a now, c later) |
  | 3 | `Set-Content` writes ANSI, not UTF-8 | **yes**: em dash → `0x97`, strict UTF-8 raises; `-Encoding utf8` writes a BOM | D3 decode order (BOM, strict UTF-8, Windows ANSI, else `usage` naming `-Encoding utf8`); notice advice; task 1.4 cp1252 row, 3.2, 5.2 |
  | 4 | spec turns remove the write tools the args file needs (cross-slice item a) | **yes**: `runner_commands.py:229`; slice 2 D9 | new **D16**: the args-file write is the one write a spec turn keeps. Claude: `Write` kept only for a spec turn described `shim` (stated weakening; no negation in Claude rules, no Hub approver on such runs). Copilot: `create` never excluded on spec turns, the handler allows only case-3 `edit`s and rejects every other in every posture, no `allow_all` on a spec turn, Plan mode after the wait for `mcp` only. New `spec-document-authority` MODIFIED delta. *Required of slice 1* (`restrict_spec_writes` + `described_access_path`) and *of slice 2* item 8; tasks 1.15, 5.2, 5.4, 5.6, drive 9.10, human step 6 |
  | 5 | `mcp_announce.wait` check-then-register race | yes, by reading D9 against the announce route's notify-after-commit | D9: register first, then check; re-check the stamp every poll step; task 1.10 race row that fails on R3's order |
  | 6 | Codex's failure text false for runs told `shim`; R2's Codex caveat dropped | **yes**: `codex_appserver.py:557-561` says "no AgentWeave tools" | D12: `map_mcp_server_failure(…, told_access_path)` rewords for `shim` and stays the one statement; D9's "left alone" sentence corrected; D10 Codex sandbox-network sentence in the shim notice; capability-plane scenario *"A run whose shell may not reach the Hub is told so"*; runtime-diagnostics scenario; tasks 2.6, 5.2 |
  | 7 | declared `hub_client: "mcp"` against a run's own test; D12's "next turn" | **yes**: `launchability.py:313-314` | D1 *The operator's declaration*: a run's own negative test decides that run; declaration next; then latest test. D12's second sentence conditional on the declaration. Capability-plane body + scenarios; tasks 1.14, 5.4, 5.5 |
  | 8 | group 7's rule restricts no path; cwd drift | yes, by reading D3/D13 | the shim enforces the calls-root rule itself (D3 *Where the file may be*; D13); R1–R3's "reads any path" withdrawn; sandboxing requirement body; task 1.4 rows (outside, unset workspace, drifted cwd, junction) |
  | 9 | NOTE: `AutoRun` output precedes the envelope | accepted | D3 caveat; notice says the envelope is the last line; human-only step 3 |
  | 10 | NOTE: Claude `pending`, Codex `cancelled`, late Copilot announce | accepted | D1 *What ignoring them costs*; D12 late-announce bullet; drives 9.2 and 9.7 record the literal status strings |
  | 11 | NOTE: the pin is re-executed per call | accepted | D5 bullet |
  | 12 | NOTE: the callable set in the Hub process | accepted | D3: `_CALLABLE_TOOLS` + `_tool()` decorator in both modes; tasks 1.3, 3.1; slice 5 bullet |
  | 13 | NOTE: the args file's content is never shown | **answered, not built** | D8 residue paragraph: flagging such a card belongs to the card's own change; not a reason to refuse case 3 |
  | conflict 1 | slice 2's `"Shell"` key (cross-slice item b) | **DECIDED**: case 2 stays `Bash`/`PowerShell`-only | D8 caller text rewritten (`write_powershell` never case 2 either); open question 10 closed; *Required of slice 2* item 7; sandboxing scenario *"A shell request from an unnamed shell tool…"* |
  | conflict 2 | other dependencies | consistent except finding 4 | covered by D16 |
  - **Disagreements with the review:** none on substance. Two differences of detail: (i) on finding 3 the ANSI fallback
    is **Windows-only**; on POSIX a non-UTF-8 file is a `usage` error, because there is no `Set-Content` to have
    written it; (ii) on finding 1, a `.agentweave` that is itself a link is **not** replaced (it may hold the project
    binding); the rule refuses standing there instead of the Hub deleting anything. On finding 4 the review listed
    three options; D16 takes a fourth, closest to the caller's "the one permitted write", and states Claude's
    weakening rather than hiding it. The operator may prefer "Claude spec turns told `shim` cannot submit" instead;
    it is one line in *Required of slice 1*.
  - **Answers to 0.3's three questions** (the review's, adopted): D2 sound; D8 case 3 acceptable once fix 1 holds,
    residual to the operator with open question 7; D11 sound, with finding 6's Codex correction.
  - `openspec validate a-run-reaches-the-hub-without-mcp --strict` re-run after these edits.

## Required of slices 1, 2; not provided to 5 (R3)

Each slice owns its own file. This section states, in the owning slice's names, what this change needs from each, and
what it does not provide. Where a slice's current text says otherwise, the difference is named. Nothing here edits
another change.

**From slice 1 (`each-runner-cli-is-one-adapter`; it owns member and axis names).**
- `tests_mcp_before_first_prompt: ClassVar[bool] = False` on **both transport ABCs** (`StreamTransport`,
  `RpcTransport`), `True` on slice 2's ACP transport. Slice 1's D16 (R3) moved it off `RunnerAdapter`, because
  only an RPC transport can defer its prompt. **Adopted** (contract reconciliation, 2026-09-28; R3 here still wrote `RunnerAdapter`).
- `RpcCallbacks.render_surface: Optional[Callable[[Literal["mcp", "shim"]], list[str]]] = None`, set by the executor
  only for such a transport (D9). Slice 1's D16 (R3) has it as an `RpcCallbacks` field. **Agreed** (contract reconciliation, 2026-09-28).
- **Not** a third `AccessAxes.plane` value. Slice 1's R2 D16 said *"slice 3 widens `AccessAxes.plane` with a
  third value, `"shim"`"*; slice 1's R3 corrected it (its D4, D16: *"Not a new `AccessAxes` value"*). **Agreed**
  (contract reconciliation, 2026-09-28). It does not. `AccessAxes.plane` is what the run is **given** and stays `"mcp" | "cli"`.
  What gains `"shim"` is the **described** value: `described_access_path(axes.plane, …)`'s return, which is `"mcp" |
  "shim"` and never `"cli"`, and the `access_path` accepted by `access_path_notice`/`_tool_surface_lines`
  (`"mcp" | "shim" | "http"`).
- **Not** per-run axis 1. Slice 1's R2 D4 (*"slice 3 turns axis 1 into a per-run detection"*) and D16 (*"per-run
  `tool_surface` detection … replaces D4's `hub_client`-only rule"*) described something this change does not
  do; slice 1's R3 corrected both (`resolve_access_axes` is final through slice 5). **Agreed** (contract reconciliation, 2026-09-28). Axis 1 (`tool_surface`) stays decided by `hub_client` alone. The per-run record changes only what is *told*
  (D1, *"What the run is given does not move"*). Slice 1's reason for not making `tool_surface` an adapter member
  still holds, for a different reason: it is `hub_client`'s, not the adapter's.
- `shim_allowed`: slice 1 has already struck it (`:430`). **Agreed.**
- Slice 1's open question 4 (the Codex MCP env allow-list): not this change's. The shim runs in the harness's shell,
  whose environment is the run's, not the MCP server's env block. This change changes neither.
- **`restrict_spec_writes` (review finding 4, 2026-09-28; D16). NEW, not yet in slice 1's text.** Precisely:
  1. The builder needs the **described** surface. `build_command`/`StreamTransport.build_launch` gain a keyword,
     `described_access_path: Literal["mcp", "shim"]` (slice 1 names it; default `"mcp"`, which reproduces today's
     argv), passed from the trigger's `described_access_path(axes.plane, …)` result (D1).
  2. Claude: `restrict_spec_writes and described_access_path == "shim"` → `--disallowedTools
     Edit,MultiEdit,NotebookEdit` (no `Write`). Every other combination → today's `Edit,MultiEdit,Write,NotebookEdit`.
     Still unconditional on yolo, as today.
  3. `RpcTurnRequest.restrict_spec_writes` keeps its meaning as a bool. An RPC transport cannot know the surface at
     spawn, so the Copilot half of D16 is slice 2's (below), not a builder input.
  4. Slice 1's golden-argv matrix (its task 1.x, `yolo × restrict_spec_writes`) gains the `described_access_path`
     axis for Claude.

**From slice 2 (`a-copilot-agent-runs-over-acp`; it owns the ACP client, executor and permission handler).** This
change lands after slice 2 and makes these edits itself at IMPL (task 5.4, 6.2). Slice 2 need only not contradict
them:
1. `decide_permission` calls `mcp_server._hub_own_call(tool, input, workspace=<run work dir>)` first, in every
   posture, on its own normalised `("PowerShell"|"Bash", {"command": …})` / `("Write", {"path": p})`. For `edit`, it
   allows by standing only with at least one path and every path passing (D8). The allow is recorded through the same
   `on_decision` as any other answer. The predicate is total. If it raises regardless, the handler treats that as
   `None` and falls through, not `reject_once`.
2. D5: for a runner that tests before its first prompt, the pre-spawn `RpcTurnRequest.tool_surface_context`
   (slice 2's separate field, its D5/D18 R3) is not sent, and the access-path notice is left out of the pre-spawn
   `notices`. `render_surface` supplies both after the wait, and rewrites the canonical context file. (contract reconciliation, 2026-09-28: R3
   wrote an `include_tool_surface=False` flag, which slice 2's separate field makes unnecessary.)
3. The one `/mcp list` diagnostic prompt is sent as a bare single text block, without the per-turn block (slice 2's
   gap list, `:1347`).
4. D10: `copilot_mcp_server_failed` is **kept** for a run told `mcp` and **suppressed** for a run told `shim`. The
   mapper reads the told surface from slice 2's `RpcTurnRequest.told_access_path`, which the transport replaces
   with the surface it passes to `render_surface` (contract reconciliation, 2026-09-28). Slice 2's message and once-per-turn rule are unchanged.
5. Slice 2's `CopilotEventMapper` passes an `agentweave` raw status of `connected` or `failed` to `record_harness_mcp_status`, inside a
   `try`. Any other status is a diagnostic.
6. D3: `copilot.exe` receives the whole run env, including the prepended `PATH`, and `agentweave-mcp.json` has no
   `env` block. This is slice 2's design today, and task 5.1 re-reads it at IMPL. This also answers slice 5's open
   question 10 for this change: an `env` block would keep the token from the tool server, but not from the shell that
   runs `aw-tool`. So it buys nothing here.
7. **The `"Shell"` key gets no standing (conflict 1, DECIDED 2026-09-28).** Slice 2's § *Provided to slices 3–5*
   item 4 (*"which slice 3 already requires to satisfy both readings"*) is wrong and should say that a request
   normalised to `"Shell"` gets no standing from `_hub_own_call` (the judge, and under "Ask me" a card), and that
   `write_powershell` (input `{shellId, input, delay}`) never reaches case 2. Slice 2's task 1.1 capture should
   count how often a genuine `powershell` request arrives with no known name; if that is common, the fix is in its
   `calls` map.
8. **Spec turns (review finding 4, 2026-09-28; D16). NEW, not yet in slice 2's text.** Slice 2's D9 changes:
   - `--excluded-tools` on a spec turn drops `create`: `apply_patch,edit,str_replace,str_replace_editor`;
   - on a spec turn, `decide_permission` answers every `edit`-kind request itself, in every posture: allowed by
     standing when it names at least one path and `_hub_own_call("Write", {"path": p}, workspace=…)` holds for every
     path, `reject_once` otherwise (recorded through `_on_refusal` like any Hub refusal);
   - on a spec turn under full access, `allow_all` is **not** set on, so `edit` requests still reach the handler; the
     handler answers every non-`edit` request ALLOW;
   - Plan mode's `session/set_mode` is sent after the D9 wait, and only for a run told `mcp`;
   - slice 2's drive task 11.3 (one spec turn) is unchanged for `mcp`; this change's drive 9.10 covers `shim`.

**Not provided to slice 5 (`a-copilot-agent-uses-hooks-and-its-own-agents`). This change is the authority on the
shim.** Slice 5's current text (`:118-123`, `:647-655`, `:692`) already matches all of the following. It is stated
here so it stays matched.
- **Slice 5 may assume:**
  - `mcp_server.py --call <tool> [<args-file>]`, run from the pinned copy (`tool_server.PIN.path()`), or through
    `aw-tool` in `PIN.launcher_dir()`;
  - it calls exactly the functions registered through the module's `_tool()` decorator except `approve_tool_call`
    (review note 12: every `@mcp.tool()` becomes `@_tool()`, so a tool slice 5 adds uses `_tool()` too);
  - it reads `AW_RUN_TOKEN`/`HUB_URL` from its own environment;
  - it prints one JSON envelope with D3's exit codes;
  - it never imports fastmcp, and never announces.
- **Slice 5 may not assume:**
  - a hook mode, an event-name argument, or any tool that receives a hook payload;
  - that call mode reads **stdin**. It refuses stdin (D3), and Copilot command hooks deliver their payload on stdin.
    A hook receiver is a new mode and a new route, slice 5's to design and to add to the callable-set parity test;
  - that `_hub_own_call` approves anything but `aw-tool` shell text and `calls/*.json` writes. A hook command is not
    a permission request, and the predicate never sees it;
  - that this change records or reports any MCP server but `agentweave`. `github-mcp-server` failures are slice 5's
    own mapping, as its R2 already says;
  - that `aw-tool` is on `PATH` outside a Hub-spawned run.

## Open questions for R3

Answered by R2 (kept for the record):

1. **Keep `_http_lines`.** It is still the only route-parity check, and it checks the text an agent on the
   application contract would read. Moving the check onto `_Operation` is a separate cleanup. R2 changes only the
   key it renders under (`"http"`, D11).
3. **Codex's source is `mcpServer/startupStatus/updated`.** `ready` means `connected` and `failed` means `failed`.
   No status means untested. Testing before `turn/start` is not built: Codex is undrivable, and whether that
   notification precedes the `thread/start` response is unmeasured.
4. **Probably not, on three counts.**
   - The approval's command is wrapped, which is VERIFIED.
   - The shell env drops `*TOKEN*` by default. This is recalled, and R3 verifies it.
   - `workspace-write` has network off.

   R2 recommends cutting group 6 (tasks 1.12 and 6.3, and D8's Codex caller). Say in the notice's Codex story that an
   untested Codex run points at a command that may not connect. That is no worse than today's HTTP form, which has
   the same network and variable problem.

   **R3: re-answered.** The variable count is **wrong**. Codex keeps `*TOKEN*` variables by default (D15, DOCUMENTED
   2026-09-28). The network count is unverified. The wrapped command stays VERIFIED. **Group 6 is cut** on D8's
   reasons. Tasks 1.12 and 6.3 are removed, and the sandboxing requirement is narrowed to Claude and Copilot.
6. **Slice 2 normalises to `PowerShell`/`Bash` + `command`, and to `Write` + `path` per edited path.** D8 matches.

Still open:

2. Is `MCP_ANNOUNCE_WAIT_SECONDS = 15` right? R2 expects the announce about 2–2.5 s after `session/new` is sent
   (D9). Drive 9.2 records the real gap.
5. Copilot's shell tool: the default `initial_wait`, and what `mode=sync` does to a command that outlives it. Asynchronous
   polling exists (CODE), so D7's sentence now offers "run it in the background". Measure in drive 9.4, or in the
   work-PC step 4.
7. Is the auto-approved args-file write (D8 case 3) acceptable under "Ask me"? This goes to the Opus review (0.3),
   together with D8's persistent-session residual: a function, alias or `PATH` change approved once can change
   what a later, unasked `aw-tool` runs.
8. (R2, new) If group 6 is cut, `specs/agent-run-sandboxing/spec.md`'s *"Wherever the Hub answers a run's
   permission request"* over-claims for Codex. Task 6.3 carries the narrowed first line to use.
   **R3: answered.** Group 6 is cut, and the first line now reads *"Wherever the Hub answers a Claude or Copilot run's
   permission request"*. The requirement body says that a Codex run's command approvals are decided as before.

R3 on the carried ones:
- **2** stays open for drive 9.2. R3 adds no measurement. The 15 s now also bounds a cancel, which the wait honours
  (D9).
- **5** stays open for drive 9.4 or the work PC. R3 found nothing newer than R2's `app.js` reading.
- **7** stays for the Opus review (0.3). R3 narrowed the residual: interpreter variables are closed by `-I`.
  Aliases, functions, profiles and `PATH` are not. Also put to the reviewer: case 2 now refuses any tool outside
  `Bash`/`PowerShell`, which R3 found to be a widening in R1/R2's wording.
9. (R3, new) Does `codex exec --json` report MCP server startup at all? `parse_codex_line` reads no MCP startup
   event (`runner_parsing.py:424-520`). Without one, F340 stays open for `exec` (D1). Undrivable here. Carry it until
   Codex can be driven.
10. **Contract conflict (contract reconciliation, 2026-09-28): slice 2's `"Shell"` key.** Slice 2's D8 (R3)
   normalises a shell request from `local_shell`, or with no tool name known, to `("Shell", {"command": …})`, a key
   `_TOOL_DIALECTS` lacks, and its § *Provided to slices 3–5* item 4 says this change already accepts an unknown
   dialect read both ways. This change's R3 limited D8 case 2 to `Bash`/`PowerShell`, and its D8 caller text still
   says slice 2 judges every Copilot shell request as `PowerShell`/`Bash` (*"no caller loses a real case"*). So an
   `aw-tool` call arriving as `"Shell"` gets no standing allow and goes to the judge (under "Ask me", a card): the
   safe side, but the two designs disagree. Not resolved here: either case 2 admits `"Shell"` read both ways (R3's
   reason for the limit was a foreign MCP tool's `command` key, which `"Shell"` is not), or slice 2 never hands the
   predicate `"Shell"`. Also carried in slice 2's open questions (its 11).
   **CLOSED 2026-09-28: DECIDED, as conveyed with the task that applied the Opus review (its contract conflict 1).** Case 2
   stays `Bash`/`PowerShell`-only. The `"Shell"` key never auto-approves: such a request goes to the judge, and under
   "Ask me" to a card. The review's reason, which is not R3's: an unnamed shell is exactly the one whose name lookup
   nobody knows, and `cmd` searches the current directory before `PATH`, so a bare `aw-tool` there can run an
   agent-written `aw-tool.bat`. D8's caller text and *Required of slice 2* item 7 say so. Slice 2 fixes its § *Provided
   to slices 3–5* item 4.

**Opus review, 2026-09-28, on open question 7 (the review's answer; the operator decides).** Case 3 under "Ask me" is
acceptable **once the calls-root rule holds** (review fix 1, applied): the file is then inert data in a Hub-owned,
git-excluded directory, the same standing `mcp__agentweave__*` already has, and note 13 (content never shown) is the
only residue. The persistent-session residual is **not** closable by the predicate, and it is wider and easier to
trigger than R3 stated (D8, review fix 2): `ComSpec`, `AutoRun`, `Import-Module`, a venv's `PATH` prepend. `-S` is
adopted (costless). **For the operator, with Q7:**
- (a) accept case 2 and case 3 as designed, residual stated;
- (b) also build the `.exe` launcher (closes `ComSpec`/`AutoRun`/`%*` re-parsing, not functions, modules or `PATH`);
- (c) also build detect-and-degrade (closes the venv and module triggers after their first use in a run);
- (d) withhold case 2's standing under "Ask me" (one card per call), keeping case 3.

This change's recommendation: **(a) now, (c) as a follow-up change** if the work-PC drive shows persistent sessions
in use. (b) adds a binary dependency on pip's private vendored launcher for the smaller half of the residual.

## Open questions as R1 posed them (answered or carried in the section above)

1. Delete `_http_lines` and `http_note` and move the route-parity assertions onto `_Operation` directly (D11)?
   R1 kept them because they are the only route-parity check.
2. Is `MCP_ANNOUNCE_WAIT_SECONDS = 15` right? Re-derive it from the pinned server's real start time on the trial
   Hub (task 9.3 records it) and from #4957.
3. Codex:
   - Does app-server start MCP servers at `thread/start`? If not, D1's "completed without announce → `absent`"
     row is wrong for Codex. Drop the row (Codex runs stay untested) rather than guess.
   - Should Codex also test before `turn/start`, as Copilot does?
4. Does a Codex shell under `workspace-write` see `PATH`/`AW_RUN_TOKEN`, and reach `127.0.0.1`? The sandbox's
   network is off by default. If it cannot, Codex's call-command approval (group 6) is moot, and the notice for
   an untested Codex run points at a command that cannot connect. That is no worse than today's HTTP form, but
   say so.
5. Copilot's `powershell` tool: its default timeout and whether a long command is backgrounded (the model reads
   its output later). This decides whether D7's timeout sentence is enough for `ask_user`. Probe with
   `copilot help` topics first; no model call.
6. Slice 2's normalised names for Copilot permission requests (`PowerShell`/`command`, and the write kinds'
   path key). D8's case 2 and case 3 depend on them.
7. Is the auto-approved args-file write (D8 case 3) acceptable under "Ask me"? R1 argues it is not a widening:
   Hub-owned, git-excluded, `.json`, inside the workspace. It is also the one rule here that decides a *write*
   rather than a call. The Opus review should attack it. If rejected, the fallback is that under "Ask me" the
   operator sees one card per args file, which makes the plane usable but noisy. This is listed as an operator
   decision in `proposal.md`'s return, not assumed.
