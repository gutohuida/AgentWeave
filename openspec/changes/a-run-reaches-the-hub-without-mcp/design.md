# Design — a run reaches the Hub without MCP

Evidence tags, as in the exploration: **VERIFIED** means measured on this machine (by this R1 today, or read
from a probe transcript on disk). **DOCUMENTED** means vendor docs or the shipped changelog. **INFERRED** means
reasoned from code or strings, not exercised. Copilot facts below were measured on **Copilot CLI 1.0.88**,
spawned as `copilot.exe --acp --stdio --no-auto-update` under a scratch `COPILOT_HOME`
(`%TEMP%\ghcp-s3-home`), with no model-calling prompt. The probe scripts and logs are in this session's
scratchpad (`s3/run1.log`, `run2.log`, `run3.log`, `tsrv.py`).

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
| codex | announce | the run ended `completed` with no announce → `absent` (INFERRED that Codex starts MCP servers eagerly at `thread/start`; open question 3) | any other end |

Two rules make the record monotone and safe:
- **`connected` is final for a run.** The announce is direct evidence that the harness started the program. A
  later `absent` or `failed` from a slower source does not overwrite it. An `absent` or `failed` may be upgraded
  to `connected` (a late announce, or Copilot's raw `session.mcp_servers_loaded` saying `connected`).
- **Unknown vendor strings are not grounds.** Any `init` status other than `connected`/`failed` is stored as
  `failed`. A raw Copilot status other than `connected` is recorded only as a diagnostic (D12), never as
  grounds (F340's own requirement: *"A status string the Hub does not recognise must count as 'no grounds'"*).

**The grounds.** `harness_has_honoured_mcp` is replaced by `latest_mcp_test(db, project_id, agent) ->
Optional[str]`: the `harness_mcp_status` of the agent's most recent run (by `started_at`, then `id`) whose status
is not NULL. `described_access_path(..., latest=...)` describes MCP iff the operator declared `hub_client:
"mcp"` or `latest == "connected"`. Per agent, as today; the docstring's argument for that grain
(`launchability.py:258-265`) still holds.

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
  runtime endpoint (`UNDESCRIBED_TOOLS`, `agents.py:986-991`) and means nothing when called by an agent.
  `submit_checkpoint_notes` stays callable, because the checkpoint prompt names it.
- **Output.** One JSON object on stdout.
  - Success: `{"ok": true, "result": <the tool's return>}`, exit **0**.
  - Refusal: `{"ok": false, "error": {"kind": "rejected", "status": <int>, "detail": <str>, "data": {...}}}`,
    exit **1** (a `HubAPIError`: the Hub was reached and said no).
  - `{"kind": "unreachable", …}`, exit **2** (`HubUnreachableError`, naming `HUB_URL`'s value; the URL is not a
    secret).
  - `{"kind": "unbound", …}`, exit **2** (`UnboundIdentityError`: no `AW_RUN_TOKEN`).
  - `{"kind": "usage", …}`, exit **64**.

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
(`:2106`) dispatches `main()` or `call_main(sys.argv[2:])`.

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
- **The pin failing.** The shim is the same file as the MCP server, so a pin that cannot be written already
  refuses the run (`agent_trigger.py:1197-1203`; the requirement's "refuses the run with its reason"). The
  launcher uses the same refusal. No run exists that has MCP but not the shim, or the reverse.
- **Codex.** Slice 1 keeps Codex's explicit MCP env allow-list (appendix B §12). Whether Codex's *shell* sees the
  run's `PATH` and `AW_RUN_TOKEN` is **INFERRED**, not measured (open question 4).
- **Copilot.** The shim runs in Copilot's `powershell` tool. It needs `AW_RUN_TOKEN`, `HUB_URL`,
  `AW_WORKSPACE_DIR` and the prepended `PATH` in **`copilot.exe`'s own process environment**, not only in the
  `--additional-mcp-config` `env` block. This is a requirement on slice 2's `build_launch`. Task 5.1 checks it,
  and task 5.4 adds it if slice 2 did not.

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
- **The harness's shell timeout can be shorter.** Claude's Bash tool defaults to 120 s. Copilot's `powershell`
  tool's timeout and backgrounding behaviour are **INFERRED**; open question 5 covers them.
- The call-command tool section therefore says, for `ask_user` and `archive_job`: *"this call waits up to N
  seconds for the operator; give the command a timeout longer than that"*. N is this run's own value: the agent's
  `question_timeout_seconds`, or the default restated.
- A shim killed mid-wait loses nothing the Hub needs. The question stays open. The run-end sweep records the
  expiry (`run_task_binding.py:905-960`, *"the tool's report and the run-end sweep"*), and the agent can still
  poll `aw-tool get_answer`. `blocking: false` plus `get_answer` stays the documented alternative.

## D8. The approver recognises the Hub's own call command, exactly

**One predicate in `mcp_server.py`**, `_hub_own_call(tool_name, tool_input) -> Optional[str]`. It returns a
reason (`"the Hub's own tools"`, the wording `_decide` already uses at `:1557`) when the call is the Hub's own,
and `None` otherwise. It is true in exactly three cases:

1. `tool_name` starts with `mcp__agentweave__`. This moves today's check (`:1556-1557`, `:1714`) into the
   predicate unchanged. Slice 2's Copilot names (`agentweave-<tool>`, `agentweave/<tool>`) are recognised by slice
   2's own normalisation before the predicate is called.
2. **A shell command that is exactly one call-command invocation.** The command text is lexed with the existing
   `_lex` in the tool's dialect (`_TOOL_DIALECTS`, `:1072`; a tool of unknown dialect must satisfy **both**
   readings, as `_decide` already requires). It must satisfy **all** of:
   - it has no command separator, pipe, background `&`, newline, redirection, substitution (`$(…)`, backticks,
     `<(…)`), variable reference (`$x`, `${x}`, `$env:x`, `%x%`), glob character, or PowerShell call operator
     `&`. Concretely, `_lex` yields no `nested` substitutions, and the raw text contains none of
     `; | & < > \n \r ` $ % * ?` outside the words checked below;
   - word 0 is exactly `aw-tool`, or `aw-tool.cmd` in the PowerShell reading. PowerShell compares command names
     case-insensitively and bash case-sensitively. A path to it (`./aw-tool`, `C:\…\aw-tool.cmd`) does **not**
     match, because the Hub cannot tell a path to its launcher from a path to a file the agent wrote;
   - word 1 is `--list`, `--help`, or a name in the callable set (D3). The set is computed in the same module, so
     it cannot drift;
   - there is at most one more word. It must be a plain relative path (no `..` component, no leading separator,
     no drive, no `~`), end in `.json`, and resolve with `os.path.realpath` against `AW_WORKSPACE_DIR` to a file
     inside `<workspace>/.agentweave/calls/`;
   - there are no further words.
3. **A file write whose every declared path is a `.json` file inside `<workspace>/.agentweave/calls/`**, resolved
   the same way. A symlink out resolves out and fails. "File write" means `_PATH_KEYS` (`:1009`) on the tool
   kinds slice 1's `write_tool_kinds` names for the runner.

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
asking (`mcp_server.py:1711-1714`: *"asking a human to approve each `send_message` would make collaboration
unusable, and those calls are already bounded by the run's own credential"*). The shim reaches exactly those
operations under exactly that credential, and nothing else:
- it runs a fixed program with no shell of its own;
- the file it reads is data;
- the auto-approved write can only create `.json` data inside a Hub-owned, git-excluded directory, which nothing
  executes (D14).

**Callers.**
- `_decide`: the predicate is first, replacing the `mcp__agentweave__` line.
- `approve_tool_call`'s operator branch: replacing its own copy of that line.
- Slice 2's ACP `request_permission` handler: in every posture before `_decide` or the card. Slice 2 normalises
  the Copilot shell tool (`powershell`, `kind: execute`) to `tool_name="PowerShell"` with
  `tool_input={"command": rawInput.command}`, and writes to `{"path": …}`. If slice 2 chose other names, R2
  rebases.
- Codex's `decide_approval` (`codex_appserver.py:244-300`): for a command approval whose command satisfies case 2,
  accept in every posture, before the `ASK_OPERATOR` return (`:276-279`). Group 6 is severable.

Tonight's `an-ask-me-card-says-what-workspace-only-would-decide` adds `_decide` advice to `_ask_operator`, and
`a-run-records-that-its-calls-were-allowed` counts decisions. Both are compatible: a predicate allow is a decision
like any other and is reported through `_report_decision` as today. Re-verify in R2.

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
     wait.
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

**Where the tool section goes for such a runner.** It is **per-turn material in the prompt**, not in the
stable custom-agent file of `ghcp-d1-instructions`: the section now depends on the run, and D1 of the operator's
decisions puts per-turn material in the prompt. Slice 2's `instruction_channel` must therefore render the
canonical context **without** its tool section for Copilot. This is a parameter of `_render_hub_agent_context`
(`include_tool_surface=False`) that this slice adds; `agents.py:2122` is the one call site of
`_tool_surface_lines`.

**Corroboration, after the fact.** Slice 2's `map_events` subscribes to `session.mcp_servers_loaded` and
`session.mcp_server_status_changed` (appendix A §A). This slice consumes them:
- the entry named `agentweave` with status `connected` upgrades the run's record (D1);
- any other status is stored as a diagnostic only.

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

`access_path_notice`'s non-MCP branch (`launchability.py:418-438`) and `_tool_surface_lines`'s HTTP preamble
(`agents.py:1545-1555`) are replaced by the call-command rendering. Reasons:
- **The HTTP form cannot be followed safely.** The model must write `Authorization: Bearer $AW_RUN_TOKEN` (or
  the value) into a command. On Copilot that command is stored as `rawInput`. F301 measured Claude refusing the
  interpolation shapes.
- **It is never the only path.** The shim exists wherever a run can be spawned: the same pin, and a spawn
  refused if the pin fails (D5).

The HTTP contract stays the application contract. The equal-capability requirement is unchanged in substance.

**What happens to the HTTP rendering code.** `_http_lines` and the `http_note` strings (`agents.py:1480-1501`)
stay, rendered only when `access_path="http"` is passed explicitly, which no run does.
`test_tool_surface_matches_server.py` renders them (`:74`, `:355`, `:378`). Those tests are today's only check
that each described operation's method, path and fields match a mounted route. Deleting the rendering would
delete that check. Open question 1 asks R2 whether to move the check onto `_Operation` and delete the rendering.

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
- `repo_hygiene.EXCLUDE_PATTERNS` (`repo_hygiene.py:59-86`) gains `.agentweave/calls/`, so `snapshot_worktree`'s
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

## Open questions for R2/R3

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
