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
log's R2 entry.

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
| any | the adapter's announce (`POST /mcp-adapter-online`, `agent_actions.py:459-483`). It keeps stamping `mcp_adapter_online_at` as today, and now also sets `connected`. | — | — |
| claude | `init.mcp_servers[agentweave].status == "connected"` | `"failed"` → `failed`; no `agentweave` entry → `absent` | no `init` line seen (spawn failure, killed before init) |
| copilot | announce within the wait (D9) | wait timed out → `absent` | the run ended before `session/new` returned |
| codex (app-server) | announce; or `mcpServer/startupStatus/updated` for `agentweave` with status `ready` | the same notification with status `failed` → `failed` | no status for `agentweave` by run end (R2: the "completed with no announce → `absent`" row is dropped, open question 3) |
| codex (exec) | announce | — | every other end |

R2: the Codex app-server source already exists. `run_turn` reads `mcpServer/startupStatus/updated`
(`codex_appserver.py:1162-1183`; `McpServerStartupState` is `starting | ready | failed | cancelled`), and today
it only turns `failed` into an error event (`map_mcp_server_failure`, `:547-567`). This slice also routes `ready`
and `failed` for the Hub's own server name to `record_harness_mcp_status`. Whether Codex reports anything for a
server that a policy removed is not known, so a Codex run with no status stays untested rather than guessed
`absent`.

Two rules make the record monotone and safe:
- **`connected` is final for a run.** The announce is direct evidence that the harness started the program. A
  later `absent` or `failed` from a slower source does not overwrite it. An `absent` or `failed` may be upgraded
  to `connected` (a late announce, or Copilot's raw `session.mcp_servers_loaded` saying `connected`).
- **Unknown vendor strings are not grounds.** Any `init` status other than `connected`/`failed` is stored as
  `failed`. A raw Copilot status other than `connected` is recorded only as a diagnostic (D12), never as
  grounds (F340's own requirement: *"A status string the Hub does not recognise must count as 'no grounds'"*).

**The grounds.** Called at `agent_trigger.py:1106-1112` **(rebase at IMPL: slice 1 `each-runner-cli-is-one-adapter`
unbuilt at R2.** There, `resolve_access_path` is deleted and the call reads `described_access_path(axes.plane, …)`
after `resolve_access_axes`.) `harness_has_honoured_mcp` is replaced by `latest_mcp_test(db, project_id, agent) ->
Optional[str]`: the `harness_mcp_status` of the agent's most recent run (by `started_at`, then `id`) whose status
is not NULL. `described_access_path(..., latest=...)` describes MCP iff the operator declared `hub_client:
"mcp"` or `latest == "connected"`, and otherwise `shim`. A run that is *given* no server (slice 1's
`plane == "cli"`, today `access_path == "cli"`) is described `shim`, never `cli`: today's
`if access_path != "mcp": return access_path` (`launchability.py:311-312`) becomes `return "shim"`. Per agent, as
today; the docstring's argument for that grain (`launchability.py:258-264`) still holds.

**What the run is *given* does not move.** The record changes only what a run is *told*. Slice 1's axis 1
(`tool_surface`, whether the server is injected) stays decided by `hub_client` alone, and `posture_at_rest` keeps
reading the given path or `axes.approvals`. Nothing that decides containment reads `harness_mcp_status` or
`plane_surface` (the requirement *"A truer description does not silently widen permission"*). Slice 1's D16 row
*"per-run `tool_surface` detection … replaces D4's `hub_client`-only rule"* therefore describes something this
slice does **not** do. That is a note for slice 1's owner (R2 cross-slice gap 1).

**The announce route, when what it calls raises.** `report_mcp_adapter_online` (`agent_actions.py:459-483`) writes
the stamp and `harness_mcp_status = connected` in **one** commit. It calls `mcp_announce.notify(run_id)` only after
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
- **The file.** It is read as UTF-8, with or without a BOM, or as UTF-16 with a BOM, because
  `Out-File`/`Set-Content` in 5.1 write those. It must hold a JSON object. The path resolves against the shim's
  own cwd. The notice tells the agent to write it under `.agentweave/calls/` in its workspace (D14), and only that
  location is auto-approved (D8). The shim itself reads any path its process can read, because the restriction
  belongs to the approver, not the reader.
- **No file** means `{}`, for tools with no required arguments (`list_tasks`, `list_checkpoints`).
- **Binding.** The keys are the tool function's parameter names, which are the MCP argument names, not the
  route's field names. They are bound with `inspect.signature(fn).bind(**args)`. An unknown or missing key is
  a usage error naming the accepted parameters and which are required. Values are not type-checked here: the Hub
  validates, and its 422 comes back readable through `_readable_detail`, exactly as over MCP.
- **Callable set.** Every function registered with `@mcp.tool()` **except `approve_tool_call`**, which is a
  runtime endpoint (`UNDESCRIBED_TOOLS`, `agents.py:989-999`) and means nothing when called by an agent. R2 count:
  27 registered, so 26 callable. All 27 are plain `def`s, and none is `async`.
  `submit_checkpoint_notes` stays callable, because the checkpoint prompt names it.
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

  Nothing else is ever printed to stdout, so a model can parse it. Exceptions are not leaked as tracebacks.

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
It must stay there and must never run in call mode. The announce is the one `connected` source, and `connected` is
final (D1). If a shim call announced, a run whose harness refused the MCP server would record `connected` the first
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
  - `aw-tool.cmd`: `@"<sys.executable>" "<pinned mcp_server.py>" --call %*`, with CRLF line endings.
  - `aw-tool`: `#!/bin/sh` + `exec "<python, forward slashes>" "<pinned path, forward slashes>" --call "$@"`,
    mode 0700 on POSIX. Git Bash on Windows runs it (VERIFIED today with a stand-in: `command -v aw-tool` found
    it, and argv arrived intact).
- **Verified like the server.** `ToolServerPin` gains `launcher_dir()`. It is written with the same
  compare-and-rewrite and atomic replace as `path()` (`tool_server.py:39-56`), inside the Hub user's own
  directory (the existing requirement's shared-directory clause applies unchanged), and pruned with the digest
  directory.
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
its callers run in the **Hub** process, whose environment is not the run's. Those are slice 2's ACP handler and
Codex's `decide_approval`. Slice 2's D8 gives `_decide` the same keyword for the same reason. It is true in exactly
three cases:

1. `tool_name` starts with `mcp__agentweave__`. This moves today's check (`:1557-1558`, and `:1709-1710` in
   `approve_tool_call`) into the predicate unchanged. Slice 2 recognises its Copilot MCP requests itself, by
   server name from the raw `permission.requested` event or a `title` of `agentweave/<tool>` (its D8). It does not
   pass them through here.
2. **A shell command that is exactly one call-command invocation.** The command text is lexed with the existing
   `_lex` in the tool's dialect (`_TOOL_DIALECTS`, `:1072`; a tool of unknown dialect must satisfy **both**
   readings, as `_decide` already requires). It must satisfy **all** of:
   - **every character of the raw text is in a fixed plain set** (R2): ASCII letters, digits, `.`, `_`, `-`, `/`,
     the space, and `\` in the PowerShell reading only. Any other character makes the predicate `None`. R1 listed
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
     no drive, no `~`), end in `.json`, and resolve with `os.path.realpath` against `workspace` to a file
     inside `<workspace>/.agentweave/calls/`;
   - there are no further words.
3. **A file write whose every declared path is a `.json` file inside `<workspace>/.agentweave/calls/`**, resolved
   the same way. A symlink out resolves out and fails. **R2 correction:** R1 said "file write" means the tool
   kinds that slice 1's `write_tool_kinds` names. `mcp_server.py` cannot read that, because it is spawned
   standalone and imports only stdlib and fastmcp (`.claude/rules/mcp-server.md`). So the predicate restates
   Claude's write tools as `_HUB_OWN_WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit":
   "file_path", "NotebookEdit": "notebook_path"}`. A test asserts it equals `workspace_writes.CLAUDE_WRITE_TOOLS`
   (`workspace_writes.py:38-43`), the house pattern for a restated constant. Slice 2 judges a Copilot edit as
   `_decide("Write", {"path": p})` per path (its D8), so the predicate also reads the `path` key for `Write`. In
   other words, it reads every `_PATH_KEYS` entry (`:1009`) present on a tool in that set.

**Near misses fall through; they are never denied by this rule.** When the predicate returns `None`, today's
logic runs unchanged: the `workspace` posture's word-by-word `_decide`, or the operator card. So the predicate
can only turn an "ask" or an "allow by `_decide`" into an "allow by standing", never a refusal into an allow
that `_decide` would refuse *for a reason other than asking*.

Case 2 is strictly narrower than what `_decide` already allows under `workspace`, which permits any shell
command whose words resolve inside the workspace. So under `workspace` the predicate changes only the recorded
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
  executes (D14).

**A residual, for R3 and the Opus review (R2).** "A fixed program" assumes that the bare name `aw-tool` resolves to
the Hub's launcher. Copilot's shell is a *persistent* session (CODE, `app.js` help table). An earlier command in
the same session can define a PowerShell function or alias named `aw-tool`, or put another directory ahead of the
launcher on `PATH`. After that, the same exact text runs something else. The predicate cannot see this. It is not a
widening:
- under "Ask me", that earlier command was itself put to the operator, who approved it;
- under "Workspace only", `_decide` already allows the plain invocation's text, and it read the redefining
  command's words when that command ran.

It does mean the operator's approval of one innocuous-looking command can change what later unasked calls do. Say so
in the Opus review rather than claim the predicate alone bounds it.

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
- Codex's `decide_approval` (`codex_appserver.py:244-300`): **R2 found that this caller, as R1 wrote it, cannot
  fire on Windows.** Codex's command approval carries the command *as its harness wrapped it*. The live captures
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
   - `wait` first checks `Run.mcp_adapter_online_at` in a fresh session, because the announce can precede the
     wait;
   - `wait` is total. A database error in that check is logged and treated as "not yet", and the wait goes on to
     its timeout. So a failing check ends as `absent` + `shim`, the safe direction. It never fails the run (R2:
     the transport runs inside the trigger's executor, and an exception there fails the run).

   R2 on the 15 s (open question 2): the announce is posted from `main()`, after the module's fastmcp import (about
   1.4 s) and before the server answers `initialize`. The probe saw the server process start 0.64 s after
   `session/new` was sent, so the announce should land about 2–2.5 s after it. 15 s is a margin of about six
   times, kept until drive 9.2 measures the real gap.
3. `connected` → surface `mcp`. Timeout → `harness_mcp_status = absent`, surface `shim`, and then one prompt
   `/mcp list` (no model call). Its text is stored verbatim as a diagnostic (D12) and is not parsed for a
   decision.
4. The access-path notice and the tool section are rendered **now**, for the surface just decided, and
   `session/prompt` is sent.

Slice 2 composes the prompt in `trigger_agent_directly` before the transport starts, as the other runners do.
This slice changes that for a runner whose adapter declares **`tests_mcp_before_first_prompt = True`**, a new
`RunnerAdapter` class attribute (`False` on Claude and Codex; slice 1's D16 says each member is added by the
slice that first reads it):
- such a runner is handed `render_surface(surface) -> list[str]`, which returns the notice and the tool section;
- `plane_surface` is written when that callable is invoked.

**Where the tool section goes for such a runner (rewritten by R2 against slice 2's D5).** Slice 2 already keeps the
tool section out of the custom-agent file. Its D5 splits `_render_hub_agent_context` into `stable` (to the agent
file) and `per_turn` (a text block in `session/prompt`), and `per_turn` **contains** `_tool_surface_lines`. R1
aimed `include_tool_surface=False` at the agent file, which is the wrong target.

The real problem is timing. Slice 2 renders `per_turn` in `trigger_agent_directly`, before spawn, from the pre-spawn
`described_path`. A runner that tests before its first prompt must not send that section. So:
- for such a runner, the trigger renders the context with `include_tool_surface=False`. The only call site is
  `agents.py:2126`, and slice 2's tagged-section split carries the flag through;
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

**Corroboration, after the fact.** Slice 2's `map_events` subscribes to `session.mcp_servers_loaded` and
`session.mcp_server_status_changed` (appendix A §A). This slice consumes them:
- the entry named `agentweave` with status `connected` upgrades the run's record (D1);
- any other status is stored as a diagnostic only.

**R2: this supersedes one line of slice 2.** Slice 2's D10 (*"The Hub's own server failing"*) emits, once per turn,
an `error` event `copilot_mcp_server_failed` carrying the text of Codex's `map_mcp_server_failure`
(`codex_appserver.py:547-567`): *"… failed to start, so this turn had no AgentWeave tools -- no messages, evidence,
task updates or questions"*. Once this slice lands, that sentence is **false** for a run told `shim`, because the run
has every operation through `aw-tool`. Left in, a blocked run would show the operator an error saying the agent
cannot collaborate, beside D12's statement that it was told `aw-tool`. So for a Copilot run, the non-`connected`
raw status becomes D12's diagnostic, and slice 2's error event is not emitted. Task 5.4 carries this. Codex's own
event is left alone: whether a Codex shell can reach the Hub is open question 4.

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
  (existing kind, `runner_events.status_event`, `:221`). Its phase is `plane_surface` and its summary reads:
  *"The AgentWeave MCP server did not start for this run (absent); the run was told to reach the Hub with
  `aw-tool`."* On Copilot a second sentence quotes the `/mcp list` line for `agentweave` verbatim (vendor text,
  bounded by `_truncate_utf8`).
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
- **If group 7 is cut,** delete the ADDED requirement *"A Claude run pre-allows the Hub's call command"* from
  `specs/agent-run-sandboxing/spec.md`, and F301 stays open for Claude.

## D14. `.agentweave/calls/`

- The Hub creates `<effective_work_dir>/.agentweave/calls/` beside `.agentweave/context/`
  (`agent_trigger.py:1160-1169`) on every turn.
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
| Codex's shell drops `*TOKEN*` variables by default, and its sandbox has network off | recalled vendor documentation, not re-read (R3 verifies); Codex undrivable here |
| Copilot's shell tool is a persistent session with `mode sync\|async` and `initial_wait` | CODE (`app.js` 1.0.88, tool help table) |

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
