# Design — a Copilot agent runs over ACP

## Context

The exploration `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md` maps every function a
Claude or Codex run gets to its Copilot counterpart. Its appendices carry the evidence: A covers the
CLI, B the run inventory, C the fallback. Operator decisions `ghcp-d1` to `ghcp-d6`
(`spec-queue/DECISIONS.md:703`) bind this change:

- **D1:** a custom agent file for the stable context, with per-turn material in the prompt.
- **D2:** Copilot-native files are written into a Hub-owned `COPILOT_HOME` when a Copilot agent is
  created.
- **D3:** credits are information only (slice 4).
- **D4:** drive on the Free plan.
- **D5:** parity first.
- **D6:** the F299 trigger correction (slice 3).

This change is the runner itself. It sits on slice 1's `RunnerAdapter`, and it leaves three things
to later slices: reaching the Hub without MCP (slice 3), spend (slice 4), and hooks and built-in
agents (slice 5).

**The model to follow is `hub/hub/codex_appserver.py`.** It spawns one process per turn
(`AppServerProcess`, `:673`). A pure `decide_approval` (`:244`) answers every server request.
`map_item_to_events` (`:390`) maps into the closed kinds. It interrupts through `should_interrupt`
polling `_stop_requested` (`:1022`), and `run_turn` (`:904`) returns a `TurnOutcome`. The trigger
wires it through `_execute_codex_appserver_run` (`agent_trigger.py:3040`), which records output,
usage, refusals and the lifecycle exactly as `_execute_run` does. Copilot's ACP client has the same
shape, with three protocol differences:

1. **The prompt response arrives last.** `session/prompt` returns `{stopReason, usage}` *after* every
   `session/update` of the turn. The client must therefore send the prompt as a pending request and
   drain notifications until it resolves. Codex's `request()` awaits inline (`codex_appserver.py:817`),
   which would deadlock here.
2. **Requests from agent to client are ACP methods.** `session/request_permission` is answered with
   `{outcome: {outcome: "selected", optionId}}` or `{outcome: {outcome: "cancelled"}}`.
3. **Raw session events** arrive as `github.com/copilot/sessionEvent` notifications, and only when
   subscribed in `initialize`.

## What is VERIFIED, DOCUMENTED, INFERRED

Tags follow appendix A. **VERIFIED** means measured on this machine (Copilot CLI 1.0.88, Free plan).
**CODE** means read in the shipped `%LOCALAPPDATA%\copilot\pkg\win32-x64\1.0.88\app.js`.
**DOCUMENTED** means from docs.github.com or `copilot help`. **INFERRED** means reasoned from those.
R1's own probes made no model call. Their transcripts are in `evidence/`.

| Fact this design rests on | Tag | Evidence |
|---|---|---|
| `initialize` returns `agentInfo.version`, `authMethods`, `loadSession:true`, `promptCapabilities.embeddedContext:true` | VERIFIED | `evidence/r1-probe-agent.log:3` |
| `copilot.exe --no-auto-update` runs **1.0.88** here. Appendix C's "runs bundled 1.0.75" does not hold after today's npm upgrade | VERIFIED | `r1-probe-agent.log:3` (`agentInfo.version "1.0.88"`), `copilot.exe --no-auto-update --version` |
| With `$COPILOT_HOME/agents/probe-builder.agent.md` present, `session/new` offers config option `agent` (`category "_agent"`), with values `""` (Copilot) and `probe-builder` | VERIFIED | `r1-probe-agent.log:6-7` |
| `session/set_config_option {configId:"agent", value:"probe-builder"}` sets `currentValue:"probe-builder"` and emits `config_option_update` | VERIFIED | `r1-probe-agent.log:8-11` |
| `/env` lists the custom agent, `CLAUDE.md` as a custom instruction, and `agentweave (connected)` | VERIFIED | `r1-probe-agent.log:13` |
| `--agent probe-builder` at spawn leaves `agent` at `""` in `session/new`, so it does **not** reach an ACP session | VERIFIED | `r1-probe-flag.log` |
| The Hub's own `mcp_server.py` (fastmcp 3.1.0 on mcp 1.26.0) connects under Copilot. It answers `server/discover` with JSON-RPC `-32602` (`mcp/shared/session.py:380-395`), and Copilot proceeds to `initialize` with `2025-11-25`, which mcp 1.26 supports (`mcp/shared/version.py:3`) | VERIFIED (status) + code | `r1-probe-mcp.log` (`agentweave (connected)`); appendix A §A for the discover-then-initialize order |
| A stdio server from `--additional-mcp-config` **inherits `copilot.exe`'s environment**, and `${VAR}` in its `env` expands from it | VERIFIED | `evidence/r1_envsrv.py` logged `AW_INHERITED='inherited-ok' AW_EXPANDED='expanded-ok'` |
| `~/.agents/skills` **does** load under a custom `COPILOT_HOME` ("Inherited"). Appendix A §E says it did not | VERIFIED | `r1-probe-agent.log:13` |
| `session/load` of a session that never received a model prompt fails `-32002 Resource not found` | VERIFIED | `r1-probe-load.log:10` |
| `/context` needs a message first, so whether the agent file's body reaches the model is **not** measurable without a model call | VERIFIED (limit) | `r1-probe-context.log` |
| `session/set_mode` with the full URI `…session-modes#plan` succeeds and emits `current_mode_update`. `allow_all` `on` is accepted | VERIFIED | `r1-probe-plan.log` |
| `session/request_permission` params are `{sessionId, toolCall, options}`. Options are `allow_once`, `allow_always` (not for `factory`), `reject_once`. `toolCall` by permission kind: shell → `kind:"execute"`, `rawInput:{command, commands[]}`; write → `kind:"edit"`, `rawInput:{fileName, diff}`, `locations:[{path}]`; read or path → `kind:"read"`, `rawInput:{path}` (paths comma-joined); url → `kind:"fetch"`, `rawInput:{url}`; mcp → `kind:"other"` (`"read"` when readOnly), `title: toolTitle or "server/tool"`, `rawInput: args`; memory, custom-tool, extension-*, factory → `kind:"other"`. A `cancelled` outcome counts as reject | CODE | `app.js` functions `bke`, `HH`, `gke`, `XDo`, `nNo`, `eNo`, `tNo` |
| `allow_always` approves for this session only, in memory | CODE | appendix A §B; `HH` |
| Session updates: `agent_message_chunk`, `agent_thought_chunk`, `tool_call`, `tool_call_update` (streamed partial output; final `status: completed|failed`), `plan`, `usage_update {used,size}`, `session_info_update`, `current_mode_update`, `config_option_update`, `available_commands_update` | VERIFIED | `evidence/acp4-turn-mcp-shell-1.0.88.log` (a real turn from the exploration) |
| An ACP `tool_call` for a shell carries a descriptive `title` ("Echo the required text") and `kind:"execute"`, **not the tool name**. An MCP call's title is `server-tool` | VERIFIED | `acp4…log` |
| `session/prompt` returns `{stopReason, usage}`, and `usage` is cumulative per session | VERIFIED | appendix A §A; `acp4…log` |
| Raw events: `assistant.usage`, `session.usage_info`, `session.mcp_servers_loaded`, `permission.requested/completed`, `session.idle`, `hook.*`. Events emitted before the session registers are not forwarded | VERIFIED | `acp4…log`; appendix A §A |
| (R2) The raw-event subscription is `initialize.params.clientCapabilities._meta["github.com/copilot"].events: [<type>…]`; each event arrives as `github.com/copilot/sessionEvent {sessionId, type, timestamp, data}` | VERIFIED | `acp4…log:1`, `:9`, `:25` |
| (R2) **`acp4…log` holds no `session/request_permission` at all.** Its one MCP permission was `"resolvedByHook": true` (a `permissionRequest` hook in the exploration's probe home answered it, `:23-26`). So the ACP request shapes in the row above are CODE only, and the order of the raw `permission.requested` relative to the ACP request is **unmeasured** | VERIFIED (absence) | `acp4…log:23-26` |
| (R2) `permission.requested.data.permissionRequest` for MCP is `{kind:"mcp", toolCallId, serverName, toolName:"<server>-<tool>", toolTitle:"<tool>", args, readOnly}`. Because `toolTitle` is set, the ACP request's `title` (CODE: `toolTitle` or `server/tool`) is the bare tool name, not `server/tool` | VERIFIED + CODE | `acp4…log:25` |
| (R2) A `tool_call` session update for a call arrives **before** its permission (4 messages earlier in the capture), and an MCP call's `title` there is `<server>-<tool>` (`hubprobe-ping`) | VERIFIED | `acp4…log:20`, `:25` |
| (R2) The model Auto resolved to is carried by raw `session.tools_updated {model}` (before the first model call) and by every `assistant.usage {model}` | VERIFIED | `acp4…log:10`, `:19` |
| (R2) The `agent` config option's value carries the agent file's frontmatter `description` verbatim, so D6's marker is observable | VERIFIED | `r1-probe-agent.log:6` |
| MCP `timeout` is in milliseconds, default **30000**, "for tool discovery and tool calls" | DOCUMENTED | command reference (`scratchpad/ghcp/ref.md:904`) |
| A custom agent's `model`/`reasoningEffort` apply "whether dispatched through the task tool or started directly". A session agent receives repository instructions | DOCUMENTED | command reference, "Custom agents reference" |
| `COPILOT_HOME` isolates sessions, logs, hooks and custom agents, and auth survives it (the token is in the Windows Credential Manager) | VERIFIED | appendix A §E; R1 probes ran under `%TEMP%\ghcp-r1s2-home` |
| The npm `copilot.cmd` is a **JS** shim (`node npm-loader.js %*`), so `pty_runner._unwrap_cmd_shim` leaves it alone (`pty_runner.py:57-99`) | VERIFIED | `%APPDATA%\npm\copilot.cmd` |
| Platform binary packages for other OSes are named `@github/copilot-<platform>-<arch>` | INFERRED | only `copilot-win32-x64` is present here |
| Whether the frontmatter `model` or the spawn `--model` wins for a session agent | INFERRED / unknown | unmeasurable on Free, where every model is Auto |
| Whether session history replay on `session/load` arrives entirely before the load response | INFERRED (ACP spec) | handled order-independently (D7) |

## Goals / Non-goals

**Goals.** A Copilot agent can be created, bound, triggered, resumed and stopped, and it runs in each
of the four postures, with its events, context meter, refusals and operator cards on the same
surfaces as Claude and Codex. It can be a checkpoint or title runner. It is described by its real
launchability.

**Non-goals.** Everything listed under "Out of scope" in `proposal.md`, plus the ACP client
capabilities `fs/*`, `terminal/*` and `elicitation/create`. Copilot never calls them (appendix A §A,
CODE), so the Hub does not advertise them.

## Decisions

### D1 — `copilot` is a runner CLI; the constraint is widened by migration

`RUNNER_CLIS = ("claude", "codex", "copilot")` (`db/models.py:311`). Three consumers follow the tuple
with no further change:

- `RunnerCreate.validate_cli` (`schemas/runners.py:22`);
- `list_provider_launchability` (`api/v1/runners.py:116-118`);
- both seeders (`db/engine.py:253`, `project_lifecycle.py:299`).

The seeders name the default runner `f"{cli.capitalize()} (default)"`, giving `"Copilot (default)"`.

**R2: three more gates refuse `copilot` today, and none of them follows `RUNNER_CLIS`.** Widening the
tuple and the constraint alone produces a runner that is created, seeded and bound, and whose every
trigger fails:

- `agent_trigger.py:773` refuses any runner not in `runner_commands.SUPPORTED_RUNNERS`
  (`runner_commands.py:60`) with **501**, before launchability is even read.
- `agent_trigger.py:1214` calls `build_command`, which raises `UnsupportedRunnerError` for
  `copilot` (`runner_commands.py:193`) → **501** at `:1230`. A Copilot turn builds no argv here:
  its argv is built inside its `run_turn` (D3), as slice 1's D6 states for every RPC transport.
- `launchability.MCP_INJECTABLE_RUNNERS` (`launchability.py:230`) lacks `copilot`, so
  `resolve_access_path("copilot")` returns `"cli"` (`:247-248`). `mcp_command` stays `None`
  (`agent_trigger.py:1195-1203`), no `agentweave-mcp.json` is named, and the run is told the HTTP
  form. **This one would pass every unit test of `copilot_acp` and never inject the server in
  production.**

`SUPPORTED_RUNNERS` and `MCP_INJECTABLE_RUNNERS` gain `copilot`, and the trigger skips
`build_command` for it (task 7.2). If slice 1 lands first, all three become adapter-driven
(`ADAPTERS`, `transport(flags).kind == "rpc"`, `inject_mcp`) and the Copilot adapter's rows cover
them; either way a trigger-level test (task 7.2) asserts that a Copilot turn reaches `run_turn`
with a non-`None` `mcp_command`. `hub/tests/test_model_catalog.py:16-18` asserts every `CATALOG`
provider is in `SUPPORTED_RUNNERS`, so D13's catalog entry fails that test until this lands.

The database refuses the value today (`CheckConstraint("cli IN ('claude', 'codex')")`,
`db/models.py:340`; created in `0023_add_runner_charter.py:32`). One new revision recreates `runners`
through `op.batch_alter_table(..., recreate="always")` with the widened constraint. It guards a
missing table as `0033`/`0034` do. Its number is **the next free one after tonight's queue** (head is
`0110` today, `hub/tests/test_migrations.py:40`), and tonight lands migrations. Re-verify in R2.
Downgrade restores the two-value constraint and refuses when a `copilot` row exists, rather than
deleting it.

**Seeding.** Only a project with **zero** runners is seeded (`engine.py:248-251`). Existing projects
get no Copilot runner; the operator creates one on the Runners page or by choosing Copilot in the
Add-agent dialog, which finds or creates the runner (`agents.py:683-708`). That is the existing
requirement's rule, extended by one CLI.

### D2 — Executable resolution: `copilot.exe`, never the npm shim

A new `copilot_probe.resolve_copilot_executable(cli_override: Optional[str]) -> Path` tries, in
order:

1. A runner's pinned `cli` override. It must be a native executable, not a script.
2. `shutil.which("copilot")`. The result is used as-is when it is itself a native executable (a
   standalone install).
3. When it is an npm shim, meaning `copilot.cmd`/`copilot.ps1`/`copilot` next to
   `node_modules\@github\copilot\npm-loader.js`, or on POSIX a symlink into
   `…/node_modules/@github/copilot/`: the platform package binary
   `<pkg>/node_modules/@github/copilot-<platform>-<arch>/copilot[.exe]`. `<platform>` is
   `win32`/`darwin`/`linux` and `<arch>` is `x64`/`arm64`. Only the Windows layout is VERIFIED here;
   the others are INFERRED from it, and a miss says so (D11).

`pty_runner.resolve_executable` is not used for Copilot. Its shim unwrap deliberately refuses a JS
shim (`pty_runner.py:57-60`), and running the shim costs two processes plus an orphan risk when only
the node parent is killed (appendix A §K).

### D3 — One process per turn, and its argv

`copilot_acp.build_acp_argv(...)` returns:

```
<copilot.exe> --acp --stdio --no-auto-update --disable-builtin-mcps
  --additional-mcp-config @<COPILOT_HOME>/agentweave-mcp.json      # only when access path is MCP
  [--model <model>]                     # omitted for "auto"/None, Copilot's own default
  [--reasoning-effort <v>]              # from the Effort control
  [--excluded-tools=apply_patch,create,edit,str_replace,str_replace_editor]   # spec turns (D9)
  [<runner flags>]                      # after transport sentinels are stripped, as for Codex
```

Why each flag is there:

- `--no-auto-update` pins the bundled version, so the version the gate reads is the version that
  runs (VERIFIED: 1.0.88).
- `--disable-builtin-mcps` removes `github-mcp-server` for hermetic runs (VERIFIED honoured). Its
  exposure as an option belongs to slice 5.
- `--model` and `--reasoning-effort` are spawn flags because `session/new` cannot carry them
  (appendix A §A).
- `--excluded-tools` is a spawn flag for the same reason. Its value is one comma-joined word:
  `app.js`'s `Y0` splits a filter value on commas (respecting parentheses) and matches each entry
  by exact tool name across every source (CODE; SDK `types.d.ts:2002`). The five names are
  `app.js`'s ACP edit set `UDo = {apply_patch, create, edit, str_replace}` plus the legacy
  `str_replace_editor`, which its kind mapper also treats as an edit (CODE, R2). Only the first
  three are documented user-facing names (command reference `:683-686`); the other two cost nothing.
- `--agent` is **not** passed, because it does not reach ACP (VERIFIED, `r1-probe-flag.log`).
- `--model`, `--reasoning-effort` and every runner flag are rendered by the Copilot `run_turn` from
  the request it is handed; nothing in the trigger builds Copilot argv (D1, R2).

**Environment.** The run environment the trigger already builds (`agent_trigger.py:1237-1305`,
covering `AW_*`, `HUB_URL`, and the strips) is passed to `copilot.exe`. The stdio MCP child inherits
it (VERIFIED), so `agentweave-mcp.json` carries **no secret and no `env` block**. It holds exactly
what Claude's `--mcp-config` holds (`runner_commands.py:251-259`), plus `tools: ["*"]` and `timeout`.

Two additions to that environment:

- `COPILOT_HOME=<the agent's Hub-owned home>` (D4).
- `GH_TOKEN`, `GITHUB_TOKEN` and `COPILOT_GITHUB_TOKEN` are removed unless the agent's `env_vars` name
  them. An ambient token silently overrides the operator's stored Copilot login (appendix A §E).
  This mirrors the ambient-`ANTHROPIC_BASE_URL` rule for Claude (`launchability.py:190-194`) and
  lives beside it in `resolve_agent_env`.

**Inheritance is total (R2, for slice 5).** With no `env` block, the MCP child receives *everything*
`copilot.exe` holds, exactly as Claude's MCP child does today. That is right for this slice, whose
`copilot.exe` environment carries nothing the MCP server should not see. Slice 5's BYOK variables
(`COPILOT_PROVIDER_*`) would also reach it; slice 5's design assumes an explicit allow-list here that
this slice does not build. Whichever lands the BYOK variables adds that filter (an `env` map that
blanks them, since `${VAR}` expansion and inheritance are both VERIFIED); a test that only inspects
the config file's `env` cannot catch the leak, because inheritance does not appear in the file.

**The MCP `timeout`.** Copilot's MCP default is 30 s (DOCUMENTED). The Hub's `ask_user` blocks up to
`AW_QUESTION_TIMEOUT` (default 240 s, configurable to `MAX_WAITING_SECONDS` = 600,
`mcp_server.py:966-1005`). `archive_job` waits up to `AW_DECISION_TIMEOUT` on the operator. Every
such Copilot call would be cut at 30 s. The file therefore sets
`"timeout": (MAX_WAITING_SECONDS + 60) * 1000` = **660000**, a constant rather than the agent's own
setting, so that the file does not have to change when that setting does. `test_copilot_home.py`
binds the constant to `agents.MAX_WAITING_SECONDS`.

### D4 — The Hub-owned `COPILOT_HOME` and what is written into it (`ghcp-d1`, `ghcp-d2`)

**Where.** The home is `~/.agentweave/hub/copilot-home/projects/<project_id>/<agent>/`, created
with mode 0700 as `tool_server.py` creates its pin root (`tool_server.py:48-50`).

**R2: a project id is not always `proj-<hex>`, so it is validated before it becomes a path.**
Minted ids are (`project_lifecycle.py:129`, `utils.py:20-22`), but *adoption* creates the project
with the id a folder's `.agentweave/project.json` names (`project_lifecycle.py:95-96`), and
`_read_marker` checks only that it is a string (`:419-425`). A hand-written marker could therefore
name `_worker`, or `..\..\x`. `copilot_home_path` refuses (raising `ValueError`, which the callers
treat as they treat `OSError`) any project id or agent name that is not a single path component of
`[A-Za-z0-9_.-]`, is `.` or `..`, or whose resolved path is not under the copilot-home root. The
per-project homes sit under `projects/`, and the worker home is a sibling of that directory (see
**Worker home** below), so no project id can name it.

It is keyed by project id, not by Hub instance. The trial Hub and `:8000` have different databases
and so different project ids, so one agent's session store is never shared between them. An agent
name is unique per project (`ix_agents_project_name`), so the path is unique — case-sensitively.
On Windows two agents whose names differ only in case would share a directory; per-agent worktrees
already carry the same hazard, so this change does not solve it separately. Copilot's session
store (`session-state/`, `session-store.db`) lives under it, so a `provider_session_id` is only
ever loaded from the home that created it.

**What.** `copilot_home.ensure_copilot_home(project_id, agent, *, stable_context, model, effort,
mcp_command) -> Path` is idempotent. It writes a file only when its content differs, through a temp
file and `os.replace` as `tool_server.py` does. It writes two files:

1. `agents/<agent>.agent.md`:

   ```markdown
   ---
   name: <agent>
   description: "AgentWeave agent <agent> — context rendered by the AgentWeave Hub"
   tools: ["*"]
   model: <model>                # omitted when the model is "auto" or unset
   reasoningEffort: <effort>     # omitted when unset
   ---

   <precedence statement>

   <stable context>
   ```

   - The **precedence statement** (`ghcp-d2`) is fixed text: *"You are running under GitHub Copilot
     CLI for the AgentWeave Hub. This context comes from AgentWeave and takes precedence over
     repository instruction files (`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`,
     anything under `.claude/`) wherever they conflict. Where those files address "Claude" or
     "Claude Code", they were written for a different harness; follow their project facts, not their
     tool names or workflows."*
   - The **stable context** is the part of `_render_hub_agent_context` that does not depend on the
     turn (D5).
   - `description` doubles as the marker D6 checks.
   - The values are YAML-quoted.

2. `agentweave-mcp.json`:

   ```json
   {"mcpServers":{"agentweave":{"type":"stdio","command":"<py>","args":["<pinned mcp_server.py>"],"tools":["*"],"timeout":660000}}}
   ```

   It is written only when the run's access path is MCP. An existing file is left in place when it
   is not, because the file is harmless unless the flag names it.

**When.**

- **(a)** After `create_operator_agent` commits an agent whose runner is `copilot`
  (`agents.py:730-732`).
- **(b)** After `PATCH /agents/{name}` commits a change to the runner binding or the charter of an
  agent whose resulting runner is `copilot` (`patch_agent`, `agents.py:2562`; its commit is at
  `:2703`). R2: an `Agent` has no default model or effort of its own. The model is the bound
  runner's (`PATCH /runners/{id}`, `runners.py:134-160`), and effort is a per-conversation control,
  so both reach the file through (c), not (b).
- **(c)** Before every Copilot spawn, with that turn's effective model and effort.

(a) and (b) are `ghcp-d2` literally. (c) keeps the existing guarantee that *"an edited charter is
therefore visible on the next run"* (`agent_trigger.py:1115-1116`). A charter, a project's
instructions and a runner's model can each be edited on routes other than the agent's own
(`charters.py:62`, `instructions`, `runners.py:134`). (c) also makes the frontmatter `model`/`effort`
equal the spawn flags of the turn about to run, so the unknown precedence between them (Open
question 3) cannot produce a conflict. One agent has at most one running turn (the trigger's
"already has a run in progress" guard), so rewriting the file per spawn cannot race.

**The failure path.** In (a) or (b) an `OSError` is logged and the route still succeeds, because the
row is committed and (c) retries. In (c) it raises `TriggerAgentError(409, "Could not write
<agent>'s Copilot home: …")`, the same shape as the context-file failure at `agent_trigger.py:1164`.

**Worker home.** A second home, `~/.agentweave/hub/copilot-home/worker/`, is used by one-shot calls
(D14) and by the launchability probe (D15). It is a sibling of `projects/`, not of the project ids,
so no project id and no agent name can reach it (R2, Open question 9).

### D5 — The stable context and the per-turn context (`ghcp-d1`)

`_render_hub_agent_context` (`agents.py:1609`) builds one `lines` list in one order and returns
`{"context": …}`. It gains two more keys and leaves `context` byte-identical (Claude and Codex keep
reading it):

- **`stable`** (line numbers re-read in R2):
  - the title line, `## Project Operating Profile` and the `- Project:` line (`agents.py:1707-1716`);
  - `## Project Instructions` (`:2112-2117`);
  - `## Communication Mode`'s heading and sentence (`:2118-2125`), **but not** the tool surface
    that `:2126` appends inside the same `if registered:` block, which is `per_turn` (below);
  - `## Charter…` (`:2135-2145`).

  These depend only on the agent row, its charter and the project.
- **`per_turn`**: everything else, in its original order. That covers:
  - the workspace block;
  - both specification blocks;
  - Team;
  - Quality Gates;
  - the evidence rights;
  - other agents' history;
  - Registration;
  - **the tool surface** (`_tool_surface_lines`).

  The tool surface is per-turn because it renders the run's `described_path`, which is decided per
  run (`agent_trigger.py:1107-1112`), and `agents.py:1657-1671` requires the notice and the
  description of one turn to agree. R2: in `context` the tool surface sits *between* Communication
  Mode and the Charter (`:2126`), so `per_turn` is not one contiguous slice of `lines`; the tagging
  below is what makes the split exact, and the reassembled order is `stable` then `per_turn`, not
  `context`'s order. `## Registration` (`:2128`) is the `else` of the same block and only renders
  for an unregistered agent, which the trigger never spawns; it is tagged `per_turn`.

The implementation tags each section as it is appended (a parallel list of `(stable: bool, text)`)
rather than re-parsing the markdown. `test_copilot_context_split.py` asserts three things:

1. `stable` and `per_turn` together contain every section of `context` exactly once.
2. `context` is unchanged for a Claude run: a snapshot of today's output on a fixed fixture.
3. The charter text appears in `stable` and never in `per_turn`.

**Delivery.**

- `stable` goes to the agent file (D4).
- `per_turn` goes into the `session/prompt` content as its own text block, **before** the notices
  and the operator's message (`prompt = "\n\n".join([*notices, message])`, `agent_trigger.py:1194`,
  is unchanged and is the second block).
- The canonical context file `.agentweave/context/<agent>.md` is still written with the full
  `context`, so the materialized record of what the agent was told is unchanged.

**Cost, stated.** Unlike Claude's `--append-system-prompt-file`, a per-turn prompt block stays in the
session history, so each resumed turn carries every earlier turn's block. That is the price of
`ghcp-d1`'s split, and it is why the split keeps as much as it can in `stable`. It is reported, not
mitigated, here. Slice 5's hooks could inject the per-turn block as `additionalContext` instead
(Open question 5).

### D6 — Selecting the agent over ACP, and the fallback

After `session/new` or `session/load`, the client sends `session/set_config_option {configId:
"agent", value: <agent>}` and reads the returned `configOptions`. It proceeds when **all** of these
hold:

- the `agent` option exists;
- its `currentValue == <agent>`;
- the option value's `description` equals the marker written in D4.

A repository `.claude/agents/<agent>.md` or `.github/agents/<agent>.md` with the same id could
otherwise stand in for the Hub's file. **R2 answered Open question 2: the repository's wins.** The
command reference (`ref.md:1228`, DOCUMENTED) says the CLI walks from the working directory up to
the git root loading `.github/agents/` and `.claude/agents/` at each level, deepest first,
`.github` over `.claude` at one level, and that *"user-level agents have lower priority than
project-level agents"*. `$COPILOT_HOME/agents/` is the user level. The dedupe by name happens in the
native runtime, not in `app.js` (whose `buildAgentConfigOption` only drops blank names, CODE), so
"one option per name" is inferred. The fallback below is therefore a documented path, not a
hypothetical one, in any repository whose agents directory holds a file named after the AgentWeave
agent. The marker check detects the substitution without depending on the rule.

When the check fails (no option, a refused set, a foreign description), the run **falls back to the
embedded channel**. The stable context is sent as an ACP `resource` content block (`{"type":
"resource", "resource": {"uri": "agentweave://context/<agent>/stable", "mimeType": "text/markdown",
"text": …}}`; `embeddedContext: true` is VERIFIED) ahead of the per-turn block. A `diagnostic` event
records why: *"Copilot did not select the AgentWeave agent file (<reason>); this turn's context was
sent with the prompt instead."* The fallback repeats per turn, because each turn is a new process.

### D7 — New or load, and replayed history

- `Conversation.provider_session_id is None` → `session/new {cwd: work_dir, mcpServers: []}`.
  `mcpServers` is empty on purpose: stdio entries there are silently dropped (appendix A §A), and the
  server arrives by flag.
- Otherwise → `session/load {sessionId, cwd, mcpServers: []}`.

**Binding.** The session id is bound to the conversation through the same first-writer rules as
Codex's `_bind_session_id` (`agent_trigger.py:3102-3140`). It is bound **before** `session/prompt`
is sent, so every event of the turn carries it.

**Replay.** `session/load` replays the history as `user_message_chunk`/`agent_message_chunk` updates
(appendix A). The mapper is **disarmed** from spawn until the `session/prompt` request has been
written, so any update before that point, whether replay or `available_commands_update`, is
dropped. This holds whatever the order of replay relative to the load response (INFERRED to be
before it). `user_message_chunk` is also dropped when armed, as Codex drops `userMessage`
(`codex_appserver.py:402-404`): the Hub already recorded the input.

**A load that finds nothing.** A session that never received a model prompt is not persisted, so
its load fails `-32002` (VERIFIED). That happens after a turn that died between `session/new` and
the first prompt, or after the agent's home was removed.

- On `-32002` alone, the client starts `session/new`.
- The rebinding is a stated exception to the first-writer rule: the old id named nothing that
  exists.
- It is recorded as a `diagnostic` event: *"Copilot had no saved session <id>; a new one was
  started."*
- `_bind_session_id` takes an explicit `replace_missing=True` for exactly this call. In slice 1's
  vocabulary the bind callback is `RpcCallbacks.on_session(id)` (its D3), and this change adds
  `on_session_missing(old_id)` to that dataclass; slice 1 leaves it open for exactly such additions.
- Any other load error fails the turn, as `thread/resume` failures do for Codex.

### D8 — Approvals: `session/request_permission` → the Hub's judge (axis 2, no MCP dependency)

A pure `copilot_acp.decide_permission(params, *, posture, workspace, hub_url, mcp_server_names) ->
Decision` returns `ALLOW`, `REJECT` or `ASK_OPERATOR`, plus a reason. It maps each request onto
`mcp_server._decide`.

**Change to `_decide`.** `_decide` (`mcp_server.py:1543`) reads `AW_WORKSPACE_DIR` (`:1560`) and
`HUB_URL` (`:1191`, `:1241`) from `os.environ`. That is right in the spawned MCP process and wrong in
the Hub process, whose environment is not the run's. So `_decide` gains keyword-only
`workspace=None, hub_url=None`, which default to the environment. **R2:** `HUB_URL` is read two
calls below `_decide`, not in it: `_decide` → `_read_command` (`:1508`, recursive for nested
substitutions) → `_judge_word` (`:1232`, reads it at `:1241`) → `_judge_url` (`:1208`) →
`_is_own_hub` (`:1183`, reads it at `:1191`). `hub_url` is threaded through all five; naming three
would leave `_judge_url`'s call to `_is_own_hub` reading the Hub process's own `HUB_URL`, so a
command naming the run's Hub would be judged against whatever the Hub was started with. The Hub
process imports `mcp_server` only function-locally today (`agents.py:1020`, because importing it
builds the FastMCP instance and reads its wait settings at module load); `copilot_acp` does the
same. `mcp_server.py`'s stdlib-plus-fastmcp import restriction is untouched.
`test_permission_approver.py` gains a case asserting that the keyword arguments override the
environment, including a `$env:HUB_URL`/`http://…` word that only `_is_own_hub` decides.

**The mapping.** `decide_permission` matches `toolCall.kind` and `rawInput` (shapes are CODE,
§ VERIFIED). The judged tool name is `_decide`'s dialect key, from `_TOOL_DIALECTS`
(`mcp_server.py:1072`).

| Copilot request | Judged as | `workspace` | `acceptEdits` (emulated) |
|---|---|---|---|
| `kind:"execute"`, `rawInput.command` | `_decide("PowerShell" if Windows else "Bash", {"command": command})` | the judge | REJECT (Claude's `acceptEdits` prompts for `Bash`, which headless means refused) |
| `kind:"edit"`, `locations[].path` / `rawInput.fileName` | `_decide("Write", {"path": p})` for **each** path; REJECT if any refuses. R2: an `edit` request naming **no** path is REJECTed, never allowed by an empty loop — `app.js` maps `write_bash`/`write_powershell` (input to a running shell) to the `edit` kind too (CODE) | the judge | the same judge (edits inside the workspace only) |
| `kind:"read"` (outside trusted dirs), `rawInput.path` split on `", "` | `_decide("Read", {"path": p})` each | the judge | the judge |
| `kind:"fetch"`, `rawInput.url` | ALLOW, as Claude's `WebFetch` is today: `_decide` reads no fetch URL (`mcp_server.py:1554-1555`) | ALLOW | REJECT |
| MCP whose server is `agentweave` | ALLOW, "the Hub's own tools" (`mcp_server.py:1557`) | ALLOW | ALLOW |
| MCP of another server | `_decide("mcp__<server>__<tool>", args)`, as Claude's approver judges foreign MCP tools today | the judge | REJECT |
| `memory`, `custom-tool`, `extension-*`, `factory`, anything unrecognised | REJECT, "not a request this Hub decides" | REJECT | REJECT |

**The posture a Copilot run is judged under (R2).** R1's table had no row for a run whose
`permission_mode` is unset, which is the ordinary case: nothing in `control_overrides` unless the
conversation or the agent's `default_permission_mode` names one (`agent_trigger.py:800-809`).
Codex maps unset to `None` and lets its own sandbox decide (`_codex_posture`,
`agent_trigger.py:2926-2952`); Copilot has no sandbox of its own to fall back on, so the Copilot
mapping (`posture_for` in slice 1's vocabulary) is:

| `permission_mode` | Judged as |
|---|---|
| unset (and not `yolo`) | `workspace` |
| `workspace` | `workspace` |
| `acceptEdits` | the emulated column |
| `manual` | operator (below) |
| `bypassPermissions`, or legacy `yolo` | full access (below) |

That is also what "Copilot's posture at rest is `workspace`" in § Sites touched means, and D13's
Permissions control therefore declares `default=WORKSPACE_PERMISSION_MODE` rather than copying
Codex's `acceptEdits` default (`model_catalog.py:294`), so the pill and the run agree.

**Identifying the MCP server (corrected in R2).** The `toolCall` carries no server name, and its
`title` is `toolTitle` when the tool has one, else `server/tool` (CODE). `acp4…log:25` shows a Hub-
style tool *has* a `toolTitle` (`"ping"`), so R1's fallback, "`title` split on `/` when exactly
`agentweave/<tool>`", would never fire. R1's primary source, the raw `permission.requested`, is
real, but whether it arrives before or after the ACP request is unmeasured (§ VERIFIED: the capture
has no ACP request at all). The client therefore decides the server from, in order:

1. the raw `permission.requested` for that `toolCallId`, if it has already been read
   (`permissionRequest.serverName`);
2. otherwise the `title` of the `tool_call` session update with that `toolCallId`, which in the
   capture arrives before the permission (`acp4…log:20`) and reads `<server>-<tool>`. It counts as
   the Hub's own only when it is exactly `agentweave-<name>` with `<name>` one of the tool names the
   Hub's server serves (a set restated beside the mapper and asserted against `mcp_server`'s tools,
   so a foreign server named `agentweave-x` cannot pass);
3. otherwise foreign.

Task 1.1's capture records the real order of the raw event and the ACP request, and the round log
says which source decided each MCP request. Server name `agentweave` is the name the Hub registers
(D4).

**The shell's dialect.** On Windows, Copilot's shell tool is `powershell` (VERIFIED). `_decide`
already lexes PowerShell (`_TOOL_DIALECTS["PowerShell"]`, `_HUB_REFERENCE_RE["powershell"]`,
`mcp_server.py:1066-1072`). **The PowerShell judge exists; there is no gap to close here.** An
unknown tool name would be read in both dialects and refused if either refuses (`mcp_server.py:1070`
comment), which is stricter but still correct. When a raw `tool.execution_start` gives the real tool
name (`bash` on a machine where Copilot uses bash), the client uses it. Open question 6 asks R2
whether to subscribe that event.

**Answering.**

- ALLOW → `{"outcome": {"outcome": "selected", "optionId": "allow_once"}}`.
- REJECT → `…"reject_once"`.
- `allow_always` is **never** chosen. It would grant the rest of the session without asking the Hub
  again, and the Hub's judge is per request.

**Operator posture (`manual`, "Ask me").**

- `agentweave` MCP → ALLOW, as `approve_tool_call` does (`mcp_server.py:1709`).
- Everything else → `ASK_OPERATOR`. The client holds the JSON-RPC request open and calls the same
  `_await_operator_permission` Codex uses (`agent_trigger.py:2977`), which bounds the wait by
  `AW_DECISION_TIMEOUT`, with a timeout denying.
- The card's `tool_name` is a readable label per kind: `execute` → "a command", `edit` → "a file
  change", `fetch` → "a web address", MCP → "`<server>/<tool>`". The card's `tool_input` is the
  `rawInput` plus `locations`.
- The label table becomes per-runner, beside `_CODEX_APPROVAL_LABELS` (`agent_trigger.py:2920`).
  `_await_operator_permission` (`:2977`) takes a protocol `method` string and looks its label up in
  that Codex table (`:3001`, `:3014`), so the Copilot path passes a label key its own table knows
  (`copilot:execute`, `copilot:edit`, …) and the lookup becomes the runner's. Slice 1 names these
  `RpcTransport.permission_card_label(method)` and `refusal_label(method)` (its D3), which is where
  the Copilot table lands if slice 1 is first.
- R2, against `an-ask-me-card-says-what-workspace-only-would-decide` (**unbuilt at R2**; rebase at
  IMPL): that change gives `_await_operator_permission` a `workspace` argument and stores a
  `workspace_verdict` on the card (its design, `:42-66`), computed for Codex by a new
  `codex_appserver.workspace_verdict(subject, workspace)`. For Copilot the verdict is the D8 judge
  already computed for the `workspace` column, so the Copilot path passes that result rather than
  calling the Codex helper. Its migration is named `0106` in its tasks (`:19`), which is stale
  against head `0110`.

**Full access (`bypassPermissions`, or legacy `yolo`).**

- After `session/new`/`load`, the client sets `allow_all` to `on`, then reads the returned
  `configOptions`.
- If `allow_all` is absent, or the set fails (managed `permissions.disableBypassPermissionsMode`,
  DOCUMENTED), the run **does not** answer every request with ALLOW. That would grant through the Hub
  what the organisation withheld from Copilot.
- The run instead proceeds under `workspace` and emits a `diagnostic` event: *"Full access is disabled
  by this machine's Copilot policy; this run is deciding each action against its workspace
  instead."*
- Any request that still reaches the client under full access is answered ALLOW (defensive, as
  `decide_approval` does at `codex_appserver.py:289-290`).

**Recording.** Two kinds of decision are recorded:

- A **refusal** the Hub decided without the operator is recorded through the same `_on_refusal`
  shape Codex uses (`agent_trigger.py:3179-3214`). That covers the `permission_denied` event and its
  SSE.
- An **allow** is recorded as `a-run-records-that-its-calls-were-allowed` requires (**unbuilt at
  R2**; rebase at IMPL). Its design adds `hub/hub/permission_tally.py` with `note(run_id, allowed)
  -> bool`, `write_counts(run_id)` and `flush(run_id)`, a Codex `on_decision(method, subject,
  allowed)` callback, and a `Run.permission_decisions` JSON column (its design `:67-118`, tasks
  `:22`). The Copilot client calls the same `on_decision` callback for every answer it gives, and
  the executor's implementation is that change's (`note`, then `write_counts` when it returns
  `True`). Until that change lands there is no allow recorder, and this path records refusals only,
  as Codex does today.

**Every request is answered.** `decide_permission` is total, and the loop answers each request
before reading the next message. A client error while deciding answers `reject_once`, never silence.
An unanswered request would hang the turn (`codex_appserver.py:255-258`).

### D9 — Specification and review turns

- **Specification turn** (`restrict_spec_writes=True`, `agent_trigger.py:1227`). It gets two things:
  1. **`--excluded-tools` over Copilot's write tools**:
     `apply_patch,create,edit,str_replace,str_replace_editor` (R2, Open question 4: `app.js`'s ACP
     edit set plus the legacy combined editor, CODE; see D3). It applies unconditionally, including
     under full access, which is the rule `_build_claude_command` states for `--disallowedTools`
     (`runner_commands.py:218-229`). Like Claude's, it is a nudge and not a sandbox: `powershell` is
     not excluded, and `write_powershell` (which `app.js` also maps to the `edit` kind) writes to a
     running shell, not to a file, so it is left alone.
  2. **Plan mode**, through `session/set_mode` with the full URI
     `https://agentclientprotocol.com/protocol/session-modes#plan` (VERIFIED accepted). Plan mode
     blocks project edits at enforcement level (DOCUMENTED). It is set after agent selection and
     before the prompt.

  **Drive check.** Plan mode also changes Copilot's own behaviour towards writing a plan, which could
  compete with `spec_turn_notice`'s interview instructions. Task 11.3 drives one specification turn
  and checks the agent interviews and can call `agentweave-submit_spec_document`. If it cannot, the
  constant `SPEC_TURN_USES_PLAN_MODE` is set `False` and a finding is filed; `--excluded-tools`
  alone still meets the requirement.
- **Review turn.** Its workspace is a detached read-only checkout (`review_turn.py`). It gets no
  special flag, as for Claude: the posture's judge refuses writes outside the checkout's root. That
  is Claude's parity, not stronger.

### D10 — The event mapper

`copilot_acp.CopilotEventMapper` holds per-turn state and turns each armed notification into
`RunEvent`s (`runner_events.py`).

- **`agent_message_chunk`.** Text chunks are accumulated. The block is flushed as one `text_event`
  when any non-message update arrives, and at prompt completion. That matches Codex, which emits a
  message when it completes (`codex_appserver.py:406-410`), and it keeps the timeline one row per
  message.
- **`agent_thought_chunk`.** Accumulated and flushed the same way, as one `thinking_event`.
- **`tool_call`** (on first sight of a `toolCallId`) → `tool_use_event`:
  - `tool` is a label by `kind`: `execute`→`shell` (Codex's label, `codex_appserver.py:426`),
    `edit`→`edit`, `delete`→`delete`, `move`→`move`, `read`→`read`, `search`→`search`,
    `fetch`→`fetch`, `think`→`think`; for `other`, the `title` (an MCP tool's `server-tool`).
  - `category` is `command`, `file_change`, `mcp` or `other`.
  - `input_data` is `{"title", "rawInput", "locations"}`, plus `"changes": [{path, oldText,
    newText}]` from any `content` item of type `diff`.
  - `call_id` is `toolCallId`.
  - `summary` is `title`.
- **`tool_call_update`** with `status` `completed` or `failed` → `tool_result_event`:
  - `output` is the concatenated text of `content`, or `rawOutput.content`;
  - `is_error` is `status == "failed"`;
  - diff content from an update is added to that call's changes.

  Intermediate updates with no terminal status (streamed shell output) emit nothing. Only the
  terminal update carries the whole output (`acp4…log`).
- **`plan`** → `status_event("plan", summary="; ".join(entry.content))`, with Codex's dedupe of an
  unchanged summary (`codex_appserver.py:1158-1161`).
- **Dropped:** `usage_update` goes to D11's meter, not the timeline. `user_message_chunk`,
  `session_info_update`, `current_mode_update`, `config_option_update` and
  `available_commands_update` are dropped. The conversation title is `conversation_titles`'s job
  (D14).

**`Error:`/`Warning:`/`Info:` text.** Copilot turns `session.error`/`session.warning`/`session.info`
into `agent_message_chunk` text with that prefix (appendix A). A model can also write "Error:". The
mapper therefore classifies a flushed message block only when a raw `session.error|warning|info`
event of the same turn carries text the block contains. The match is on the raw event's `message`
field. R2 answered Open question 10 from the SDK's `session-events.d.ts` (CODE): `session.error`
is `{errorType, message, errorCode?, statusCode?, remediation?, …}`, `session.warning` is
`{warningType, message, url?, remediation?}` and `session.info` is `{infoType, message, tip?, url?}`;
`message` is required on all three. Task 1.1 still records a captured one.

- An `Error:` match → `error_event(code="copilot_session_error", message=…)`.
- A `Warning:`/`Info:` match → a new `diagnostic_event` builder in `runner_events.py`. That kind is
  in the closed set (`schemas/agents.py:19`) and has no builder today. R2: slice 5 adds the same
  builder as `diagnostic_event(*, code, message, severity, facts)` (its design `:206`), so this slice
  ships that keyword-only signature with `severity="info"` and `facts=None` defaults, and slice 5
  extends rather than re-adds it. The code is `copilot.<warningType|infoType>`, the dotted form slice
  5 uses; `copilot_session_error` and `copilot_mcp_server_failed` keep the underscore form of
  Codex's `codex_mcp_server_failed`, because they are `error` codes beside it.
- An unmatched block stays `text`.

Slice 5 (its D5) later re-maps a raw `session.error` to a `diagnostic_event(severity="error")` and
suppresses the echoed `Error:` block in either order; that replaces this bullet's `error_event` and
is slice 5's to change, recorded here so neither slice believes it owns the final shape.

The version gate (D12) guarantees raw events exist.

**The Hub's own server failing.** A raw `session.mcp_servers_loaded` or
`session.mcp_server_status_changed` naming `agentweave` with a status that is not connected emits,
once per turn, the same message `map_mcp_server_failure` builds for Codex (`codex_appserver.py:547`),
under the code `copilot_mcp_server_failed`. Deciding the run's tool surface from that status is
slice 3's. R2: slice 3's design (`:319-322`) also records "any other status as a diagnostic" from the
same events, and measured that they do not arrive before the first model prompt (`:281`); whichever
lands second removes the duplicate, and this slice's once-per-turn error for the Hub's own server is
the one to keep.

**Model substitution.** The raw `session.model_change {newModel, previousModel?}` and
`session.auto_mode_resolved {chosenModel, availableModels?}` events name the model Copilot actually
runs (both exist in `session-events.d.ts`, CODE; the second is marked experimental). R2: neither
appears in `acp4…log`, which was not subscribed to them; what the capture *does* show is raw
`session.tools_updated {model}` before the first model call (`:10`) and `assistant.usage {model}` on
every call (`:19`). The mapper takes the resolved model from the first of `session.model_change`,
`session.auto_mode_resolved` or `session.tools_updated` it sees, and `session.tools_updated` is
subscribed for that reason. When the requested model was not `auto` and differs from the resolved
one, the mapper emits one `diagnostic`, for example: *"Copilot ran mai-code-1.1-flash (Auto)
instead of the requested claude-haiku-4.5; this plan allows: [mai-code-1.1-flash]."* The list
comes from `availableModels` when present and is omitted otherwise. This is the Free plan's
behaviour (VERIFIED), and without it an operator would believe the requested model ran.

**Subscribed raw events.** The subscription is sent as
`initialize.params.clientCapabilities._meta["github.com/copilot"].events` (VERIFIED wire shape,
`acp4…log:1`) and is exactly:

- `session.error`, `session.warning`, `session.info`;
- `session.mcp_servers_loaded`, `session.mcp_server_status_changed`;
- `session.model_change`, `session.auto_mode_resolved`, `session.tools_updated`;
- `permission.requested`.

The list is the module constant `copilot_acp.COPILOT_RAW_EVENTS: tuple[str, ...]` (R2: named, because
slices 4 and 5 both write "slice 2's list"). Slices extend it by concatenation and it is sent
de-duplicated in first-seen order, so slice 4's `assistant.usage`, `session.usage_checkpoint` and
`session.compaction_complete` and slice 5's overlapping additions cannot double-subscribe.

**Raw events for later slices (R2).** Slice 4 needs every subscribed raw event and the prompt
result's `usage` at the executor (its D2). `run_turn` therefore takes an optional
`on_raw_event(type: str, data: dict)` callback, called for every armed raw event after the mapper
has seen it, and the Copilot `TurnOutcome` carries `prompt_usage: Optional[dict]` (the last
`session/prompt` result's `usage`, unprocessed) and `session_was_new: bool`. This slice passes no
`on_raw_event` and reads neither field; they exist so slice 4 extends the executor instead of
re-opening the transport.

### D11 — Context meter and accounting

**Context meter.** `usage_update {used, size}` → `ContextUsageSample(status="measured",
source="copilot_acp", basis="provider_context", context_tokens=used, limit_tokens=size,
model=<resolved model or requested>, breakdown=None)`. `size` ≤ 0 or missing → `status="unavailable"`,
as for Codex (`codex_appserver.py:333-342`). The last reading of a turn wins, per *Latest observation
replaces rather than accumulates*. The context window therefore comes from the provider report, and
the catalog's `None` windows (D13) are never consulted for a reading that carries `size`.

**Accounting.** Each turn records `record_turn_usage(runner="copilot", sample=None)`, which is a turn
counted with no measured usage. It is **not** fed from the prompt result's `usage`: that is
cumulative per session (VERIFIED), and turning it into a per-turn figure means differencing across
processes. That is slice 4's work, together with `assistant.usage`.
`an-estimate-that-misses-turns-says-so` **landed** (archived 2026-09-28) and R2 re-read it:
`record_turn_usage(db, *, run_id, project_id, agent, runner, sample)` is unchanged
(`usage_accounting.py:15-26`); `sample=None` records `status="unavailable"` with no cost (`:36-54`),
and such a turn now counts in the summary's `unpriced_turns` (`:96-98`), which the UI states as
"…excludes N turns with no reported cost". A Copilot turn is therefore disclosed, not silently
zero, with no further work here. In the executor the call is `runner=adapter.name`, never the
`"codex"` literal (`agent_trigger.py:3261`, `:3350`, `:3445`).

### D12 — Version gate

The minimum is **1.0.81**. Raw event subscription and `session_info`/plan updates land in 1.0.81, and
`usage_update` and `session/close` in 1.0.78 (appendix A §K). Without raw events D8's MCP server
identification, D10's `Error:` classification and the model-substitution notice all fail.

**1.0.88 is not required by this slice.** It only makes managed policy (MCP allowlists, permission
policy) apply to ACP sessions, which matters to slice 3 and the operator's work PC, not to parity.

The client compares `initialize.result.agentInfo.version` (dotted integers) with
`COPILOT_MIN_VERSION`. When it is lower, the process is closed and the turn fails *before any
session exists* with `CopilotACPError("Copilot CLI <v> is older than the supported 1.0.81. Update it
with `copilot update` or npm.")`. A missing version is treated as too old.

**R2: `CopilotACPError` subclasses `codex_appserver.AppServerError`**, and every failure `run_turn`
raises is one (or `FileNotFoundError`/`OSError`/`asyncio.TimeoutError`). The executor's pre-spawn
`except` names exactly `(FileNotFoundError, AppServerError, asyncio.TimeoutError, OSError)`
(`agent_trigger.py:3244`), and slice 1's D15 makes that the `run_turn` contract. A bare
`RuntimeError` would miss it and land in the generic handler (`:3425`), the path for *unexpected*
crashes. `_record_run_failure_tail` still fails the run and returns its entries, but
`_log_abnormal_run_end` logs it as an abnormal end with its traceback, so an expected "update your
CLI" or "sign in" outcome would read in the logs as a Hub defect. The same class carries a JSON-RPC
error response: `ACPProcess.request` raises `CopilotACPError(code=<error.code>)` for a response
holding `error`, so D7's `-32002` is read from `.code`, never parsed out of text. (Codex's
`request()` returns an error response as a value and its callers index `["result"]`, which raises
`KeyError` outside the pre-spawn tuple; the Copilot client does not copy that.)

### D13 — Model catalog for `copilot`

A `CATALOG["copilot"]` `ProviderDescriptor` has `label="GitHub Copilot"`.

- **Models.** `auto` comes first (label "Auto", `default=True`, `context_window=None`), then the list
  printed by `copilot help config` under `model` (a command with no model call; VERIFIED output, 26
  ids today). The list is **embedded** as a static tuple, with labels derived from the id, and
  `context_window=None` for every entry: Copilot reports the window per turn (D11), and the
  requirement *Every model the catalog offers declares a context window or is stated as unknown*
  permits `None`.
- **No runtime parse.** A runtime parse of `help config` at catalog load was considered and rejected:
  `GET /model-catalog` would then spawn a process on a read route. **R2, against what landed:**
  `the-codex-models-offered-are-the-ones-its-cli-lists` went the *other* way for Codex — the offered
  list is read at runtime from `$CODEX_HOME/models_cache.json` (`model_catalog.py:303-421`), memoised
  on the file's mtime and size, with `CATALOG["codex"]` kept only as the fallback. R1's sentence
  ("fixed by editing the tuple, as that change does") was wrong. The reason still separates the two
  cases: Codex's CLI leaves a model file to read, and Copilot's list is only printed by a command,
  so reading it costs a spawn. `_CACHE_BACKED_PROVIDER` stays the single string `"codex"`, and the
  Copilot entry is a plain `CATALOG` literal whose source reports `built_in` automatically
  (`api/v1/model_catalog.py:26`, `schemas/model_catalog.py:56`). A file Copilot keeps in its home
  that lists models would change this; none is known, and R2 did not find one.
- **Drift is checked by the script, not a test (R2).** R1's task 2.4 added a pytest that runs `copilot
  help config` and skips without the binary. `scripts/check_model_catalog.py` states why this repo
  does not do that: a check that can only skip in CI blesses a drifted catalog exactly where nobody
  looks (its docstring, "Why a script and not a test"). The Copilot comparison is added to that
  script instead, as a `--provider copilot` section that runs `copilot help config` (no model call)
  and diffs the ids.
- **Controls.**
  - `effort` has values `low`, `medium`, `high`, `xhigh`, `max` and is applied as
    `ApplySpec("flag", "--reasoning-effort {value}")`. `none` and `minimal` are omitted to match the
    other providers' vocabulary.
  - `permission_mode` has the same four values and labels as Codex, applied as `ApplySpec("none")`
    (read at trigger time, D8), with **`default="workspace"`** (R2; D8's posture table), not
    Codex's `"acceptEdits"`.
  - R2: the effort control is rendered to argv by `render_control_args("copilot", overrides)`
    inside the Copilot `run_turn` (D3), since the trigger builds no Copilot argv.
- **Validation.** `validate_overrides` refuses an undeclared model (`model_catalog.py:532-576`,
  line re-read in R2). R2 traced *where* it runs: `POST /agent/trigger` validates the operator's
  overrides (`agent_trigger.py:1618`), `POST/PATCH /runners` validate a runner's model
  (`_reject_undeclared_model`, `runners.py:54`, `:154`), and `create_operator_agent` refuses an undeclared
  provider/model pair (`agents.py:692-700`). The per-turn trigger then trusts what was stored
  (`agent_trigger.py:796-799`). So the spec's "refused before a Copilot process starts" holds at
  those three entry points and needs no per-turn check. That backstop matters more here, because
  `session/set_model` accepts `bogus-model` (VERIFIED, appendix A) and `--model` on Free is
  silently replaced.
- **`_CATALOG_PROVIDER_BY_RUNNER`** (`runner_commands.py:110`, not `model_catalog.py`) gains
  `"copilot": "copilot"`. Slice 1 deletes that table for the adapter's `catalog_provider` ClassVar
  (its D5); whichever exists at IMPL is the one extended.
- **`context_window_for_model`** searches every provider by id, then alias, then longest id prefix
  (`model_catalog.py:465-497`, re-read in R2 after `a-model-alias-is-a-model-choice` landed).
  `gpt-5.5` and `gpt-5.6-*` exist in both the Codex and Copilot catalogs, so a Copilot reading
  **without** a `size` would borrow Codex's window. D11 always has `size` from `usage_update`, so
  the path is not reached. R2 found the converse too: `_context_window_in` returns on the first
  *exact* match even when that match's window is `None` (`:469-470`), and `CATALOG["copilot"]` is
  iterated after Claude's and Codex's, so an id only Copilot declares stops the search at `None`
  rather than falling through to a prefix match. Harmless while every consumer of a Copilot reading
  has `size`; Open question 7 records both. `auto` is declared as an **id**, not an alias, so the
  landed alias rule (`ProviderDescriptor.model`, `:149-155`; the runner name's "(latest)" suffix,
  `agents.py:710-713`) never applies to it.

### D14 — One-shot calls

`worker.build_worker_command` and `conversation_titles.build_title_command` each gain a `copilot`
branch, and `copilot` joins `worker.SUPPORTED_CLIS` (`worker.py:71`) and `_SUPPORTED_CLIS`
(`conversation_titles.py:68`).

```
<copilot.exe> -p <neutralised prompt> --output-format json --no-auto-update
  --disable-builtin-mcps --no-custom-instructions --no-ask-user
  --excluded-tools=builtin:*,mcp:*,custom:* --allow-all-tools [--model <m>]
```

- **R2 correction, Open question 4: `--available-tools=` (empty) grants every tool.** `app.js`'s
  filter parser `Y0` returns `undefined`, meaning *no filter*, for an empty string, an empty list or
  the bare flag (CODE: `Y0=e=>{if(e===void 0||e===!0)return;let t=FH(…filter(n=>typeof
  n=="string"&&n.length>0));return t.length>0?t:void 0}`), and the prompt-mode path uses the same
  `Y0` (`let ag=Y0(e.availableTools)`). R1's argv, combined with `--allow-all-tools`, would have run
  every one-shot call — whose prompts are untrusted transcript text (F420) — with every built-in
  tool approved. Tools are removed instead through `--excluded-tools`, which "always takes
  precedence", with the source-qualified patterns the SDK documents (`builtin:*`, `mcp:*`,
  `custom:*`; `types.d.ts:2002`, CODE for the SDK's filter; INFERRED that the CLI flag reaches the
  same filter, since both go through `Y0` into the session's tool filters). Task 1.2's capture
  checks it: the run must offer the model no tool (read from `session.tools_updated` or the
  envelope), and if a pattern is not honoured the fallback is the explicit list of built-in names
  from the command reference (`ref.md:670-690`), never an empty allow-list.
- It runs with `COPILOT_HOME=<the worker home>` and without the GitHub-token variables. **R2:
  neither spawn helper passes an environment today** — `worker._run_worker_process`
  (`worker.py:341-363`) and `conversation_titles._run_titler` (`conversation_titles.py:113-128`)
  call `subprocess.run` with no `env`, so both inherit the Hub's. Each gains an `env` parameter,
  which is `None` (inherit, today's behaviour) for Claude and Codex and the Copilot one-shot
  environment for Copilot.
- `cmd[0]` is the absolute path `resolve_copilot_executable` returned (D2), never the bare name
  `copilot`: both helpers pass `cmd` through `pty_runner.resolve_executable`, which keeps an absolute
  path as-is (`pty_runner.py:123-124`) but would resolve a bare `copilot` to the npm shim.
- `--allow-all-tools` is required for non-interactive mode (DOCUMENTED); with every tool excluded
  it grants nothing.
- `--no-custom-instructions` works under `-p` (appendix A §E).

**Where titles run.** The titler deliberately runs in the project's directory so the project's
memory applies (`conversation_titles.py:81-93`). For Copilot that memory is `CLAUDE.md`/`AGENTS.md`,
which `--no-custom-instructions` would drop. So the **title** branch omits
`--no-custom-instructions`, keeping the titler's intent, and the **worker** branch keeps it.

**R2: the titler reads plain text, and this argv prints JSON.** `generate_conversation_title` hands
the titler's stdout to `title_from_output` (`conversation_titles.py:277`), which takes the *last
non-empty line* (`:99-110`). With `--output-format json` that line is the envelope's final JSONL
record, so every Copilot conversation would be titled with a fragment of JSON. The title path for
`copilot` therefore passes stdout through `parse_copilot_envelope` first and titles from the answer
it returns (an unparseable envelope titles nothing, the titler's existing "" floor). Task 1.14
asserts it on the 1.2 fixture.

**The envelope parser.** `parse_copilot_envelope(stdout)` reads the JSONL:

- the answer is the last `assistant.message` content;
- a failure is a `session.error`;
- the `result` line carries `sessionId`. Premium requests are ignored here (slice 4).

Its event names are fixed by the capture in task 1.2, not guessed. Usage stays `WorkerUsage()` (all
`None`) until slice 4.

**The cost is stated.** Every one-shot call on Copilot spends the plan's allowance. Titles are
generated per conversation by the conversation's runner (`conversation_titles._resolve_runner`).
Slice 5 may use Copilot's own `session_info_update` title instead (Open question 8).

### D15 — Launchability read from Copilot

`probe_agent` (`launchability.py:54`) is synchronous and runs on list routes, so it cannot spawn.
`copilot_probe.CopilotProbe` therefore keeps a process-wide cached verdict keyed by the resolved
executable path and its mtime, with a TTL of 10 minutes. It is refreshed asynchronously by two
things:

- `GET /runners/launchability-by-provider` and the agent-launchability route, which schedule a
  refresh when the verdict is stale and return the cached one;
- every Copilot turn, which writes what it learned (version, auth).

A refresh:

1. resolves the executable (D2);
2. spawns it with `--acp --stdio --no-auto-update` under the worker home;
3. sends `initialize` and reads the version;
4. sends `session/new` (cwd = the worker home) and reads auth. `authRequired` means not authorized;
5. sends `session/close` and ends the process.

No model call is made.

| State | `present` | `authorized` | `reason` |
|---|---|---|---|
| executable not resolvable | False | — | "GitHub Copilot CLI was not found: install it with npm (`@github/copilot`) or the standalone installer." When a shim was found without its platform binary, the reason names the path it looked for |
| version < 1.0.81 | True | False | "Copilot CLI <v> is older than the supported 1.0.81. Update it." |
| `session/new` raised `authRequired` | True | False | "Copilot CLI is not signed in. Run `copilot login`." |
| verdict not yet computed | True | True | None, and `verdict_pending: True` in the probe dict |
| ok | True | True | None |

The "not yet computed" row is deliberately permissive. Refusing agent creation because a background
probe had not finished would make the first Copilot agent on a fresh Hub uncreatable for no reason.
The binding gate is the run's own `initialize` (D12) and `session/new`, which fail the turn with the
same sentences. The dead env-token branch (`launchability.py:116-126`) is deleted, and
`RUNNER_CLI["copilot"]` stays `"copilot"` for the name.

The collaboration verdict (`agents.py:238-266`) needs no Copilot arm. Copilot's approvals never
depend on the tool surface, so it falls to `collaboration_ready = True` in the `else` branch.
R2: `a-runner-that-cannot-collaborate-says-so-where-it-is-bound` (**unbuilt at R2**) turned out to be
UI-only — `RunnerPicker` shows `runnable && collaboration_ready === false`, and the runner hooks
invalidate the launchability query (its design `:53-110`). It leaves this route and block
unchanged, so R1's "reshapes this block" was wrong and nothing here needs rebasing.

**R2, where the refresh is scheduled.** `probe_agent` is called from six places —
`GET /agents/launchability` (`agents.py:234`), `GET /runners` (`runners.py:96`), `GET /runners/launchability-by-provider`
(`runners.py:118`), `create_operator_agent` (`agents.py:728`), the inbound queue (`inbound_queue.py:223`) and the trigger (`agent_trigger.py:731`, `:766`).
Scheduling the refresh only from the two list routes would leave a Hub whose operator goes straight
to "Add agent" with a verdict that stays pending until a list route is hit. `CopilotProbe.verdict()`
itself schedules the refresh (`asyncio.get_running_loop().create_task`, when a loop is running and no
refresh is in flight) whenever the cached verdict is stale, so every caller keeps it fresh and the
list routes need no Copilot code. The route docstring's "never spawns anything (task 6.2)"
(`agents.py:181-182`) becomes "never spawns an agent run"; the requirement it serves, *Readiness does
not spawn agents* (`runtime-diagnostics`), says "no agent run is started", and a probe that makes no
model call and creates no conversation is not one.

### D16 — Tool names in the tool surface

On Copilot, the model-facing name of an MCP tool is `<server>-<tool>`, sanitised to `[A-Za-z0-9_-]`
with at most 64 characters (VERIFIED: `hubprobe-ping`). Every AgentWeave tool name is already inside
that alphabet and short. The tool-surface prefix for a Copilot run is therefore `agentweave-`.

Tonight's `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` introduces a `tool_prefix`
decided from the runner (its design D2). This change adds `copilot → "agentweave-"` to that decision.
It also adds a Copilot preamble sentence: *"Copilot has its own tools with similar purposes (such as
its task tool); these AgentWeave tools are the only way to reach AgentWeave agents or the operator."*
The access-path notice (`launchability.py:409-413`) names them the same way.

If that change has not landed when this is built, this task waits for it; it does not build a
second prefix mechanism. `test_tool_surface_matches_server.py` gains a Copilot rendering case.

R2 (**that change is unbuilt at R2**; rebase at IMPL): its design threads `tool_prefix` into
`_tool_surface_lines(..., tool_prefix="")` and `launchability.access_path_notice`, passes
`runner=` to `_render_hub_agent_context`, and decides the prefix from a `CLAUDE_FAMILY_RUNNERS` set
in `runner_commands.py`, keyed on `described_path == "mcp"` (its design `:59-110`). Slice 1 then
replaces the set with the adapter ClassVar `mcp_tool_prefix: Optional[str]` (its D3). The Copilot
value is `"agentweave-"` in whichever of the two exists. Today's `access_path_notice` names bare
tools ("call send_message / create_task …", `launchability.py:409-413`), which a Copilot model
cannot call by those names, so this is not cosmetic. Note that a Copilot agent's first turn is told
the HTTP form anyway: `described_access_path` asserts the MCP form only after this agent's harness
has been seen to start the server (`launchability.py:283-315`), which is unchanged here.

### D17 — Stop

A stop sets `_stop_requested`. The client polls it as Codex does (`codex_appserver.py:1022-1029`).
When it is set:

1. It sends `session/cancel {sessionId}`, a notification that also cancels the session's shells
   (appendix A §A).
2. It waits up to 10 s for the pending `session/prompt` to return `stopReason:"cancelled"`.
3. It then ends the process with `terminate_process_tree(pid, force=True)` (`pty_runner.py:184`),
   **not** `proc.kill()`. `copilot.exe` runs its shells as children, and `AppServerProcess.close`'s
   single-process kill (`codex_appserver.py:874-883`) would orphan them.

A cancelled stop reason → `TurnOutcome.status == "interrupted"` → `stopped`, as for Codex
(`agent_trigger.py:3310`).

Registration uses the set slice 1 names for RPC runs (today `run_liveness.active_app_server_runs`,
`run_liveness.py:53`), so that `stop_agent_run` (`agent_trigger.py:1778`) and
`terminate_all_active_runs` (`:1823`) reach Copilot runs with no new branch. R2: slice 1 keeps that
name and documents it as holding every RPC run (its D9), and makes stop a clause of the `run_turn`
contract ("honour `should_interrupt` and leave no process behind") rather than an adapter member.
`ACPProcess.close()` therefore uses `terminate_process_tree` on **every** exit, not only after a
stop: a turn that fails or times out with a shell still running would otherwise leave
`powershell.exe` behind exactly as a stop would. `terminate_all_active_runs` only *signals* an RPC
run (`:1823-1825`), so on a Hub shutdown the tree kill happens only if `run_turn`'s `finally` runs
before the process exits — the same limit Codex has today, recorded rather than fixed here.

### D18 — The executor

`_execute_codex_appserver_run` (`agent_trigger.py:3040-3459`) hard-codes `runner="codex"` at four
sites (`:3089`, `:3261`, `:3350`, `:3445`) and calls `codex_run_turn`. Slice 1 is expected to turn it
into one RPC-transport executor that takes the adapter. This change passes the Copilot adapter,
whose `run_turn` is `copilot_acp.run_turn` with the same callbacks:

- `on_event`, `on_usage`, `on_accounting` (never called; D11), `on_thread_started` (→
  `_bind_session_id`), `should_interrupt`, `on_refusal`, `request_approval`;
- plus `on_session_missing` for D7's rebinding.

If slice 1 has not generalised the executor, task 7.1 does it here, by exactly that
parameterisation, before adding Copilot.

**R2, against slice 1's design as it stands (slice 1 is unbuilt and at its own R2).** Slice 1 names
the executor `_execute_rpc_run(adapter, transport, …)` and the transport call
`run_turn(req: RpcTurnRequest, cb: RpcCallbacks) -> TurnOutcome` (its D3 `:127-131`, D9 `:264`):

- `RpcTurnRequest` = `cli, cwd, env, prompt, model, resume_session_id, yolo, mcp_command,
  config_overrides, permission_mode, workspace`. The Copilot `run_turn` reads the posture from
  `permission_mode` through its own `posture_for` (D8), the resume id from `resume_session_id`, and
  additionally needs the per-turn block, the stable context and the spec-turn flag. Those three are
  not in slice 1's request: this change adds `per_turn_context: Optional[str]`,
  `stable_context: Optional[str]` and `restrict_spec_writes: bool` to `RpcTurnRequest` (ignored by
  Codex), rather than folding the per-turn block into `prompt`, which is the durable record of what
  the operator said.
- `RpcCallbacks` = `on_event, on_usage, on_accounting, on_session, should_interrupt,
  request_approval, on_refusal` (plus `on_decision` from the allow-recording change). R1's
  `on_thread_started` is slice 1's `on_session`. This change adds `on_session_missing` (D7) and
  `on_raw_event` (D10, for slice 4).
- The executor's four `runner="codex"` literals are now at `agent_trigger.py:3089`, `:3261`,
  `:3350` and `:3445` on master `ef55e6f` (unchanged from R1; slice 1 quotes them from `97b86ed`).
- The executor catches `(FileNotFoundError, AppServerError, asyncio.TimeoutError, OSError)` before
  a turn starts (`:3244`), which is why D12's error subclasses `AppServerError`.

### D19 — UI

- `RunnerCli = 'claude' | 'codex' | 'copilot'` (`hub/ui/src/api/runners.ts:5`).
- `CLI_OPTIONS` gains `'copilot'` (`RunnersPage.tsx:19`).
- `providerForRunner` gains `copilot → 'copilot'` (`api/modelCatalog.ts:75-80`). Without it, the
  composer's model controls resolve no provider for a Copilot agent.
- `PROVIDER_MARKS.copilot` is the `simple-icons` `siGithubcopilot` path rendered in `currentColor`,
  as OpenAI's mark is (`Icon.tsx:233-237`). This follows the sanctioned `simple-icons` exception
  (`.claude/rules/hub-ui.md`): the mark is published (`simple-icons` ships `githubcopilot.svg`) and
  imported by name only.
- The model picker needs no code. It renders the catalog, and Auto is the Copilot default.
- R2: `AgentTimeline.tsx`'s `WRITING_TOOLS` (`:654`) is `Edit, MultiEdit, Write, NotebookEdit,
  apply_patch` and `TOOL_ICON` (`:635-649`) is keyed on Claude's tool names, so D10's `edit`,
  `delete` and `move` rows would render as unmarked generic tools — a Copilot file change would not
  read as a write in the timeline. Both gain the three names (icons `edit`, `delete`,
  `drive_file_move`, which `Icon.tsx` must already carry or gain). No diff is rendered, which is
  Codex's `apply_patch` parity: `lib/editDiff.ts` renders only a top-level `old_string`/`new_string`
  pair.
- `modelCatalogFixture.ts` gains the Copilot provider.
- The bundle is rebuilt and refreshed (`scripts/refresh_ui_bundle.py`), and `hub/ui/src` and
  `hub/hub/static/ui` are committed together.

## What each route returns when what it calls raises

- **`POST /agents` (create).**
  - `ensure_copilot_home` raising `OSError` is logged. The route still returns 201, because the
    agent row is committed and the next spawn retries (D4 (c)).
  - Launchability with a pending verdict returns runnable (D15).
  - A known "not signed in" or "too old" verdict returns today's 409 with that reason
    (`agents.py:728-733`).
- **`PATCH /agents/{name}`**: as for create, logged, and the route's own response is unchanged.
- **`POST /runners` with `cli: "copilot"`**: 201. Before the migration it would be an
  `IntegrityError`, which the migration removes.
- **`POST /agent/trigger` for a Copilot agent** (`trigger_agent_directly`):
  - R2, **on today's master, before any of this change**: **501**, from the `SUPPORTED_RUNNERS` gate
    (`agent_trigger.py:773`); past it, `build_command` would raise `UnsupportedRunnerError` → 501
    (`:1230`). Task 7.2 removes both for `copilot` (D1). A test that patches the Copilot `run_turn`
    must enter through `trigger_agent_directly`, or it passes while the route still answers 501;
  - executable not found → `TriggerAgentError(409)`, the probe's sentence;
  - `ensure_copilot_home` fails → 409 (D4);
  - the version gate or auth fails → the run is created and then fails, through the executor's
    pre-spawn `except` path (`agent_trigger.py:3244-3288`), with the sentence in `Run.error` and the
    entries returned to the queue — **only because** `CopilotACPError` subclasses `AppServerError`
    (D12, R2);
  - `copilot_home_path` refuses an unsafe project id or agent name (`ValueError`, D4) → 409, the
    same as a failed write;
  - `session/load` `-32002` → a new session (D7);
  - any other ACP error → a failed run, with `stderr_tail` carried as for Codex.
- **`GET /runners/launchability-by-provider`**: never raises for Copilot. A failing refresh is
  logged and the verdict records the failure as `reason`.
- **`GET /model-catalog`**: cannot raise. R2: not "static" — its Codex half is read from a file at
  runtime since `the-codex-models-offered-are-the-ones-its-cli-lists`, whose reader never raises
  (`model_catalog.py:320-326`); the Copilot half is a literal.
- **Worker and titles**: a missing executable → `spawn_failed`; unparseable JSONL → `unparseable`.
  These are the existing outcomes (`worker.py:74-83`). R2: `resolve_copilot_executable` *raises*
  when it finds nothing (D2), and it runs inside `build_worker_command`/`build_title_command`,
  which `run_worker` (`worker.py:454`) and `generate_conversation_title` (`conversation_titles.py:268`)
  call **outside** their spawn helpers' `try`. `run_worker`'s contract is "returns an outcome; never
  raises" (`:435`). So the Copilot builders catch the resolution failure and return the existing
  outcome — `run_worker` records `spawn_failed` with the probe's sentence, the titler titles
  nothing — rather than letting it escape. Task 1.14 covers both.

## Sites touched by open changes (re-verified in R2, 2026-09-28, master `ef55e6f`)

R1 wrote this table expecting the whole 2026-09-27 night queue to have landed before R2. It did
not: of that queue only five changes are on master (archived under
`openspec/changes/archive/2026-09-28-*`), three of which meet this change. Every other row is
**unbuilt at R2**, and its "expected site" is read from that change's own design; each is marked
*(rebase at IMPL)* and must be re-read against the code when task 7 starts. Migration head is
`0110` (`hub/hub/migrations/versions/0110_loop_pending_agent.py`, `test_migrations.py:40`); no
unbuilt change claims `0111` or later by number.

| Change | State at R2 | Where it meets this change |
|---|---|---|
| `the-codex-models-offered-are-the-ones-its-cli-lists` | **landed** | D13: Codex's offered list is read at runtime from `$CODEX_HOME/models_cache.json` (`model_catalog.py:303-421`), literal kept as fallback. Copilot stays a literal (no file to read); drift goes to `scripts/check_model_catalog.py`, not a test. R1's "as that change does" corrected |
| `an-estimate-that-misses-turns-says-so` | **landed** | D11: `record_turn_usage(..., runner, sample=None)` unchanged (`usage_accounting.py:15-26`); the turn counts in `unpriced_turns` and is disclosed |
| `a-model-alias-is-a-model-choice` | **landed** | D13: `ProviderDescriptor.model` matches id or alias (`model_catalog.py:149-155`); aliases exist only on Claude; `auto` is an id, so the "(latest)" runner-name rule (`agents.py:710-713`) never applies |
| `a-runner-choice-names-its-model`, `a-firing-is-counted-once-however-many-agents-it-starts` | **landed** | no site in this change |
| `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` | unbuilt *(rebase at IMPL)* | D16: `_tool_surface_lines(tool_prefix=)`, `access_path_notice(tool_prefix)`, `_render_hub_agent_context(runner=)`, `CLAUDE_FAMILY_RUNNERS` (its design `:59-110`); slice 1 renames to `mcp_tool_prefix`. Task 1.18/8.3 wait for it |
| `the-permissions-pill-shows-the-posture-the-run-gets` | unbuilt *(rebase at IMPL)* | `posture_at_rest(provider, access_path, yolo)` in `runner_commands.py` and a list field `permission_mode_at_rest` (its design `:44-64`); slice 1 moves it to the adapter as `posture_at_rest(axes, *, yolo)`. Copilot's answer is `workspace` whether or not MCP is injected (D8's posture table), and D13's control default says the same |
| `an-ask-me-card-says-what-workspace-only-would-decide` | unbuilt *(rebase at IMPL)* | D8: `_await_operator_permission(workspace=)`, `permission_requests.workspace_verdict`, `codex_appserver.workspace_verdict` (its design `:42-66`). Copilot passes its own D8 verdict. Its migration is named `0106` (stale) |
| `a-run-records-that-its-calls-were-allowed` | unbuilt *(rebase at IMPL)* | D8: `permission_tally.note/write_counts/flush`, `on_decision(method, subject, allowed)`, column `Run.permission_decisions` by "next free revision" (its design `:67-118`, tasks `:22`) |
| `a-runner-that-cannot-collaborate-says-so-where-it-is-bound` | unbuilt | none: UI-only (`RunnerPicker`, launchability-query invalidation); the `agents.py:238-266` block is unchanged. R1's row was wrong |
| `agents-no-longer-register-themselves` (parked, but in the night queue) | unbuilt *(rebase at IMPL)* | drops four `Agent` columns in one migration (number unassigned) and the self-registered exemption in `launchability.get_agent_config`; this change's migration number follows whichever lands first |
| `the-shell-judge-reads-a-word-whole` (parked) | unbuilt | does **not** change `_decide`'s signature (R1's row was wrong): it wraps `approve_tool_call`'s `_decide` call in a deny-on-exception `try` (its design `:510-527`). Copilot's `decide_permission` needs the same guard of its own — D8's "a client error while deciding answers `reject_once`" |
| `stop-clears-a-run-an-earlier-hub-left-running` (parked) | unbuilt | D17: `run_liveness.PROCESS_STARTED_AT` and a stop route that tree-kills `run.pid` for a run from an earlier Hub. A Copilot run records no `Run.pid` today (Codex's does not either), so that path cannot reach it; recorded, not solved |
| slice 1 `each-runner-cli-is-one-adapter` | unbuilt, at its own R2 *(rebase at IMPL)* | D1, D3, D7, D8, D13, D17, D18: see § "Slice 1 member names" below |
| slice 3 `a-run-reaches-the-hub-without-mcp` | unbuilt | D10: consumes `session.mcp_server_status_changed`; duplicate-diagnostic risk noted in D10; its `include_tool_surface=False` premise is already met by D5 |

### Slice 1 member names (R2)

`proposal.md` listed fifteen members; slice 1's design (as of 2026-09-28) defines them as follows.
The proposal now uses slice 1's names.

| R1's name | Slice 1 | Mismatch and resolution |
|---|---|---|
| `build_launch`, `map_events`, `usage_from` | `StreamTransport` only | Copilot is an `RpcTransport`: argv, mapping and usage live inside its `run_turn` (slice 1 D6: argv only for stream). Not members here |
| `transport` | `RunnerAdapter.transport(flags)` | same |
| `inject_mcp` | `RpcTransport.inject_mcp(mcp_command) -> dict` | Copilot's is the `agentweave-mcp.json` content (D4) |
| `instruction_channel` | `RpcTransport.instruction_channel` ClassVar | Copilot's value is the agent file (D6); slice 1 D11 asks slice 2 to define it |
| `decide_posture` | `RunnerAdapter.posture_at_rest(axes, *, yolo)` + `RpcTransport.posture_for(permission_mode)` | split in two; D8's posture table is `posture_for` |
| `context_window` | `context_window_source` | Copilot's is `"reported"` (slice 1 D13) |
| `stop` | none | a clause of the `run_turn` contract (D17) |
| `one_shot`, `write_tool_kinds`, `catalog_provider`, `launchability` | same names | `launchability` must not raise (D15's verdict is cached) |
| `resume_id` | `RpcTurnRequest.resume_session_id` | a request field, not a member |
| `tool_prefix` | `mcp_tool_prefix` ClassVar | `"agentweave-"` |
| (not in R1's list) | `parse_one_shot`, `guard_env`, `collaboration`, `permission_card_label`, `refusal_label`, `mcp_env_names`, `transport_sentinels`, `host_tool_note` | Copilot implements them: `parse_copilot_envelope`, the GitHub-token strip (D3), `(True, None)`, D8's labels, `()` (no sentinel), `None` |
| (slice 1 D16, deferred to this slice) | `write_native_files`, `agent_home`, `version_gate`, `models(live)` | `ensure_copilot_home`, `copilot_home_path`, D12's gate; `models` is the static tuple (D13), no live source |
| `on_thread_started` (D18) | `RpcCallbacks.on_session` | renamed; this change adds `on_session_missing` and `on_raw_event` |
| (D18) | `RpcTurnRequest` lacks the per-turn block, stable context and spec-turn flag | this change adds `per_turn_context`, `stable_context`, `restrict_spec_writes` (D18) |

## Risks / Trade-offs

- **[Copilot ships weekly; ACP shapes may move]** → Pin with `--no-auto-update`; gate the version;
  build the fixtures from captured transcripts; keep every decision total (unknown → reject or
  drop); and tag CODE-derived shapes so R2 can check them against the capture.
- **[The per-turn block accumulates in session history (D5)]** → Keep it as small as the split
  allows; report it; slice 5 may move it to a hook.
- **[The custom agent file is shadowed by a same-named repository agent]** → The D6 marker check and
  the embedded fallback, with a diagnostic.
- **[Plan mode interferes with specification interviews]** → Task 11.3's drive check, and the
  `SPEC_TURN_USES_PLAN_MODE` switch.
- **[Free-plan allowance is spent by drives and one-shot calls]** → Captures and drive turns are
  counted in `tasks.md` (6 model prompts in total); titles and checkpoints on Copilot are the
  operator's choice of runner.
- **[`_decide`'s signature changes]** → Keyword-only defaults keep every existing call unchanged.
  (R2: `the-shell-judge-reads-a-word-whole` does not touch the signature; see § Sites.)
- **[A gate outside the transport keeps refusing `copilot` (R2)]** → D1 names the three
  (`SUPPORTED_RUNNERS`, `build_command`, `MCP_INJECTABLE_RUNNERS`); task 7.2's trigger-level test
  enters through `trigger_agent_directly` and asserts a non-`None` `mcp_command`, so a transport that
  works in isolation cannot pass while production never reaches it.
- **[An empty tool filter grants everything (R2)]** → D14 never passes `--available-tools=`; task
  1.2's capture confirms the one-shot call is offered no tool.
- **[A migration reaches `:8000`]** → It only widens a check constraint. Downgrade refuses rather
  than deletes.

## Migration Plan

1. Deploy the migration with the code. Rollback is a downgrade, refused while a `copilot` runner
   exists.
2. `~/.agentweave/hub/copilot-home/` (`projects/…` and `worker/`) is created on the first Copilot
   agent or one-shot call. Removing it loses only
   Copilot session history; each agent's next turn starts a new session (D7).

## Open questions for R2/R3

1. **Does the agent file's body reach the model?** Selection is VERIFIED; delivery needs a model
   call. Task 1.1's capture asks the model to quote a marker from the agent file. If the marker does
   not come back, D6's fallback becomes the primary channel.
2. ~~**User-level versus project-level custom agents of the same id: which wins?**~~ **Answered in
   R2:** the project-level one (DOCUMENTED, command reference `ref.md:1228`; the loader is in the
   native runtime, so not CODE). D6's fallback is therefore a documented path. See D6.
3. **Frontmatter `model` versus spawn `--model` for a session agent.** D4 (c) removes the conflict
   by writing both identically. Confirm nothing else reads the frontmatter model differently, for
   example subagents under Auto.
4. ~~**The exact write-tool names for `--excluded-tools`** (D9), and whether `--available-tools=`
   empty means no tools for `-p` (D14).~~ **Answered in R2 (CODE):** `apply_patch, create, edit,
   str_replace` (`app.js` `UDo`) plus `str_replace_editor`; and an empty `--available-tools=` means
   **no filter** (`Y0`), so R1's one-shot argv would have granted every tool. D9 and D14 corrected;
   task 1.2 still confirms the one-shot call sees no tool.
5. **The per-turn block's cost over a long conversation** (D5). Measure `used` growth across three
   resumed turns in the drive.
6. **Should `tool.execution_start` be subscribed** to learn the real shell tool name (D8), or is the
   platform rule enough? On this machine it is `powershell` (VERIFIED). R2 adds: the runtime knows a
   third shell tool, `local_shell` (CODE: `_N="local_shell"`, and "expected one of
   bash/powershell/local_shell"), whose dialect the platform rule does not decide. Carried to R3.
7. **`context_window_for_model` is provider-blind** (D13). Should it take a provider? It is not
   reached by D11, but a later path could hit it.
8. **Title cost on the Free plan** (D14). Should a Copilot conversation take Copilot's own
   `session_info_update` title instead of a one-shot call? Deferred to slice 5 unless R2 finds the
   one-shot titler spending the allowance in the drive.
9. ~~**Where `_worker` sits.**~~ **Answered in R2: a project id *can* be `_worker`**, or anything
   else. Minted ids are `proj-<12 hex>` (`project_lifecycle.py:129`), but adoption takes the id a
   folder's `.agentweave/project.json` names (`:95-96`), checked only as a string (`:419-425`). D4
   now puts agent homes under `projects/` and the worker home beside it at `worker/`, and validates
   every path component.
10. ~~**The exact field names of `session.error|warning|info` raw event data**~~ **Answered in R2
    (CODE, SDK `session-events.d.ts`):** `message` on all three, beside `errorType`/`warningType`/
    `infoType`. Task 1.1 still records one captured event.

## Round log

- **R1 — 2026-09-27** (this document; no git commands; files only under this change directory).
  - **Read:**
    - the exploration and appendices A, B and C;
    - `2026-09-20-the-approval-transport-is-not-the-tool-surface.md`;
    - `DECISIONS.md` `ghcp-d1`–`d6`;
    - `CLAUDE.md` and `.claude/rules/{mcp-server,db-migrations,hub-ui}.md`;
    - DEAD-ENDS 2026-09-27;
    - the house style in `a-runner-choice-names-its-model/`;
    - `codex_appserver.py` in full;
    - `agent_trigger.py:800-1360`, `:1760-1830`, `:2275-2370`, `:2920-3459`;
    - `runner_commands.py` in full;
    - `launchability.py` in full;
    - `model_catalog.py:60-487`;
    - `mcp_server.py:1-70`, `:960-1110`, `:1179-1280`, `:1500-1720`, `:2060-2108`;
    - `workspace_writes.py:1-120`;
    - `runner_events.py:1-245`;
    - `worker.py:60-160`, `:300-340`, `:430-470`;
    - `conversation_titles.py:60-100`, `:240-260`;
    - `pty_runner.py:50-135`;
    - `tool_server.py:1-60`;
    - `db/models.py:300-345`, `db/engine.py:236-262`, `project_lifecycle.py:290-315`,
      `schemas/runners.py`, `api/v1/runners.py:105-125`;
    - `api/v1/agents.py:225-270`, `:545-575`, `:654-760`, `:1605-1720`, and the section headers;
    - the UI's `runners.ts`, `RunnersPage.tsx:19`, `Icon.tsx:222-290`, `modelCatalog.ts:65-80` and
      `brandMarks.ts`;
    - fastmcp/mcp `shared/session.py:355-400`;
    - the specs `runner-registry`, `agent-run-sandboxing` (`:1-41`, `:854-900`),
      `agent-stream-events` (`:75-100`, `:224-236`), `agent-context-usage` (`:65-106`,
      `:355-372`) and `model-catalog` (`:1-31`);
    - the proposal of `a-claude-run-is-told-its-agentweave-tools-by-their-full-names`;
    - Copilot's `app.js` permission-request functions.
  - **Probed** (no model call; `evidence/r1_probe.py`, under `%TEMP%\ghcp-r1s2-home`):
    - the agent option and its selection;
    - `--agent` under ACP;
    - the Hub's `mcp_server.py` connecting under Copilot;
    - environment inheritance into the stdio MCP child;
    - `session/load` of an unprompted session;
    - plan mode and `allow_all`.
  - **Corrections to the appendices:**
    - `--no-auto-update` runs 1.0.88 here, not 1.0.75 (appendix C);
    - `~/.agents/skills` does load under a custom home (appendix A §E);
    - Copilot's MCP tool-call timeout is 30 s by default, which the parity map missed.

- **R2 — 2026-09-28** (task 0.1; files only under this change directory; read-only git; no
  `copilot`/`codex` process spawned).
  - **Drift, stated first.** Task 0.1 asked for a derivation "after tonight's queue and slice 1".
    Neither happened: master is `ef55e6f`, and only 5 of the 2026-09-27 night queue's changes
    landed (`a-runner-choice-names-its-model`, `an-estimate-that-misses-turns-says-so`,
    `a-model-alias-is-a-model-choice`, `the-codex-models-offered-are-the-ones-its-cli-lists`,
    `a-firing-is-counted-once-however-many-agents-it-starts`). Slice 1
    (`each-runner-cli-is-one-adapter`) is unbuilt and was at its own concurrent R2. There is no
    ORDER file; the queue is `.claude/autonomous/STATE-night.json`. This round therefore derived
    against today's master; verified the three landed changes that meet this one against their real
    code; and, for every unbuilt change, read its design and wrote the expected site, marked
    *(rebase at IMPL)* in § Sites. Migration head is still `0110`.
  - **Read, fresh, from the code (not from this design):**
    - `codex_appserver.py:79-300`, `:303-345`, `:390-440`, `:540-570`, `:597-1205`;
    - `agent_trigger.py:760-860`, `:1060-1320`, `:1612-1622`, `:1741-1830`, `:2049-2142`,
      `:2915-3300`, `:3300-3460`;
    - `runner_commands.py` in full; `launchability.py` in full; `model_catalog.py:20-72`,
      `:143-165`, `:270-646`;
    - `mcp_server.py:960-1110`, `:1148-1294`, `:1508-1600`, `:1698-1740`, and its imports;
      `.claude/rules/mcp-server.md`;
    - `workspace_writes.py:1-120`; `worker.py:60-160`, `:341-470`;
      `conversation_titles.py:60-135`, `:223-300`;
    - `api/v1/agents.py:171-275`, `:654-770`, `:1609-1730`, `:2080-2166`, `:2562-2740` (fields
      and commit), section headers; `api/v1/runners.py:100-175`; `schemas/runners.py`;
      `db/models.py:300-345`; `db/engine.py:236-262`; `project_lifecycle.py:85-135`, `:298-310`,
      `:411-440`; `utils.py:20-22`; `usage_accounting.py:15-26`; `run_liveness.py`;
      `runner_events.py` (builders); `tool_server.py:40-50`; `pty_runner.py:107-131`, `:184`;
    - `hub/tests/test_model_catalog.py:10-25`, `test_migrations.py:40`,
      `scripts/check_model_catalog.py:1-40`;
    - UI: `AgentTimeline.tsx:630-660`, `lib/editDiff.ts:1-60`;
    - `openspec/specs/runtime-diagnostics/spec.md:130-165`,
      `conversation-checkpoint/spec.md:30-75`;
    - evidence: `acp4-turn-mcp-shell-1.0.88.log` message by message, `r1-probe-agent.log:5-11`;
    - by delegated read-only research: slice 1's proposal/design/tasks/specs; slices 3-5's
      proposal/design/tasks; the eleven sibling changes in § Sites; Copilot 1.0.88's `app.js`,
      SDK `types.d.ts`/`rpc.d.ts`/`session-events.d.ts`, and the command reference
      `scratchpad/ghcp/ref.md` (Open questions 2, 4, 9, 10).
  - **What was wrong, and what changed** (design section → fix):
    1. **D1: three gates outside `RUNNER_CLIS` refuse `copilot`.** `SUPPORTED_RUNNERS` → 501
       (`agent_trigger.py:773`); `build_command` → 501 (`:1214`/`:1230`);
       `MCP_INJECTABLE_RUNNERS` lacks `copilot` (`launchability.py:230`), so **no Copilot run
       would ever be given the MCP server** — a transport that passes every unit test and cannot
       fire in production. Added to D1, tasks 2.4/3.3/7.2, a registry scenario and the risks;
       task 7.2's test now enters through `trigger_agent_directly`.
    2. **D14: `--available-tools=` (empty) is *no filter*** (`app.js` `Y0`, CODE). With
       `--allow-all-tools`, R1's one-shot argv approved every tool on untrusted transcript text.
       Replaced by `--excluded-tools=builtin:*,mcp:*,custom:*`; new `conversation-checkpoint`
       requirement; task 1.2's capture argv changed.
    3. **D14: titles.** `title_from_output` takes stdout's last line (`conversation_titles.py:99-110`,
       `:277`), which under `--output-format json` is a JSON record. The title path now parses
       the envelope first.
    4. **D14: neither one-shot spawn passes `env`** (`worker.py:341-363`,
       `conversation_titles.py:113-128`), so `COPILOT_HOME` and the token strip could not apply;
       both gain an `env` parameter. `cmd[0]` must be the absolute `.exe`, which
       `resolve_executable` passes through (`pty_runner.py:123`). A resolution failure inside the
       builders would escape `run_worker`'s "never raises" contract; the builders now catch it.
    5. **D8: MCP-server identification.** `acp4…log` has **no** `session/request_permission`
       (`resolvedByHook: true`, `:23-26`), so the raw-event-before-request order R1 relied on is
       unmeasured; and a Hub tool's `toolTitle` exists (`"ping"`, `:25`), so R1's
       `agentweave/<tool>` title fallback could never fire. Replaced by: raw event if already
       read, else the preceding `tool_call` update's `agentweave-<tool>` title (VERIFIED to
       precede, `:20`) restricted to the Hub's own tool names, else foreign.
    6. **D8: no posture for an unset `permission_mode`** — the ordinary case
       (`agent_trigger.py:800-809`). Added a posture table: unset → `workspace`; D13's
       Permissions default is `workspace`, not Codex's `acceptEdits`. Spec scenarios added.
    7. **D8: `hub_url` must be threaded through five functions**, not three: `_read_command` and
       `_judge_url` sit between `_decide` and `_is_own_hub` (`mcp_server.py:1508`, `:1208`).
       The Hub imports `mcp_server` function-locally (`agents.py:1020`), not at `:1016`.
    8. **D8: an `edit` request naming no path** would be allowed by an empty per-path loop;
       now refused (`app.js` maps `write_powershell` to the edit kind).
    9. **D12: `CopilotACPError` must subclass `AppServerError`**, the pre-spawn `except` tuple
       (`agent_trigger.py:3244`) and slice 1's `run_turn` contract; JSON-RPC errors raise it
       with `.code` (Codex's `request()` returns them as values).
    10. **D4: project ids are not always `proj-<hex>`** — adoption takes the folder marker's
        string verbatim (`project_lifecycle.py:95-96`, `:419-425`). Homes moved to
        `copilot-home/projects/<pid>/<agent>`, the worker to `copilot-home/worker`, every
        component validated; spec scenario added. (D4(b): an `Agent` has no default model or
        effort; the spec's "default model changes" trigger was wrong and is now "runner binding
        or charter", with the per-turn refresh covering model edits.)
    11. **D13: the Codex catalog change went runtime**, not "edit the tuple"; drift is checked
        in `scripts/check_model_catalog.py`, not a skip-in-CI test (task 2.4); the catalog's
        exact-match-returns-`None` behaviour recorded under Open question 7.
    12. **D15:** `probe_agent` has six callers, so `CopilotProbe.verdict()` schedules its own
        refresh; the collaboration change is UI-only (R1 said it reshapes the block).
    13. **D19:** `AgentTimeline`'s `WRITING_TOOLS`/`TOOL_ICON` gain `edit`/`delete`/`move`.
    14. **D10:** the resolved model also comes from `session.tools_updated` (VERIFIED), now
        subscribed; the subscription constant is named `COPILOT_RAW_EVENTS`;
        `diagnostic_event` ships slice 5's keyword-only signature.
    15. **D18:** slice 1's `RpcTurnRequest` lacks the per-turn block, stable context and
        spec-turn flag; added as fields. Callback renamed `on_session`.
    16. Line numbers re-read throughout (`agents.py` context sections, create/PATCH commits,
        `_render_hub_agent_context` at `:1609`, validation sites, `tool_server.py:48-50`, the
        executor's `except` lines).
  - **Held after re-derivation:** D2 (shim resolution; `resolve_executable` unwraps only a
    `.cmd`/`.bat` and keeps an absolute path as given, `pty_runner.py:123-130`), D3's timeout constant (`MAX_WAITING_SECONDS = 600` in
    both `agents.py:2368` and `mcp_server.py:967`), D7's first-writer binding
    (`agent_trigger.py:3102-3140`), D9's unconditional-restriction rule, D11's meter shape
    (Codex's `unavailable` branch at `codex_appserver.py:332-341`), D17's stop signalling
    (`agent_trigger.py:1778-1784`, `:1823-1825`) — which also showed Copilot needs the tree kill on
    *every* exit, now stated.
  - **Open questions answered:** 2 (project-level agents win; DOCUMENTED), 4 (write-tool names
    and empty-filter semantics; CODE), 9 (a project id can be anything a marker names), 10
    (`message` on all three raw events; CODE). **Carried to R3:** 1, 3, 5, 6 (now also
    `local_shell`), 7, 8.
  - **Cross-slice gaps found** (this change now provides, or records, each):
    - slices 4/5 write "slice 2's list" → named `COPILOT_RAW_EVENTS`, de-duplicated on send;
    - slice 5 adds `diagnostic_event` with another signature → this slice ships the superset;
    - slice 5 re-maps `session.error` to a diagnostic and uses dotted codes → recorded in D10 as
      slice 5's change;
    - slice 5 assumes an MCP `env` allow-list; this slice relies on inheritance, which would pass
      BYOK keys → recorded in D3 for slice 5;
    - slice 4 needs raw events, the prompt result's `usage` and `session_was_new` at the
      executor → `on_raw_event` and two `TurnOutcome` fields;
    - slice 4's allowance-hold branch (its D8) has no hook here → **gap, left to slice 4**;
    - slice 5's BYOK launchability (a key instead of a sign-in) contradicts D15's "not signed in"
      verdict → **gap, left to slice 5**;
    - slice 5's rule that `github-mcp-server` asks the operator under `workspace` needs a special
      case in D8's foreign-MCP row → **gap, left to slice 5**;
    - slice 3 wants a bare `/mcp list` prompt, but D5 always prepends the per-turn block →
      **gap, left to slice 3**; slice 3's `include_tool_surface=False` premise is already met by
      D5's split; slice 3's MCP-status diagnostic duplicates D10's → recorded;
    - slice 5's design says slice 2 writes hook files; it writes none (slice 5's text is wrong).
  - **Validate:** `openspec validate a-copilot-agent-runs-over-acp --strict` passes.

- **Pending:**
  - R3: an independent re-derivation (task 0.2), which should also re-read slice 1 once its R2
    lands and re-check § "Slice 1 member names".
  - Opus adversarial review.

## Cross-slice consistency (orchestrator, 2026-09-27, after all five R1s; reconciled in R2)

For R2 to reconcile against `each-runner-cli-is-one-adapter`'s design:
- This design says `resume_id`. Slice 1 carries the resume id as `RpcTurnRequest.resume_session_id`, and has no `resume_id` member.
- This design says `tool_prefix`. Slice 1 names it `mcp_tool_prefix`, which replaces tonight's `tool_prefix` and `CLAUDE_FAMILY_RUNNERS`.
- Slice 3 adds `tests_mcp_before_first_prompt` and slice 4 needs `compaction_percent`, which slice 1 lists as a deferred contract. Whichever change lands first adds the member.
- Migrations: slices 2, 3, 4 and 5 each add one, and slice 1 none. Numbers are assigned in build order after tonight's queue, which takes numbers from `0111`.
- R2: the first two bullets are applied (§ "Slice 1 member names"; the proposal uses slice 1's names). The third stands. On the fourth: head is still `0110` at R2 and no unbuilt change claims `0111`+ by number; `an-ask-me-card-says-what-workspace-only-would-decide` and two others still name a stale `0106`.
