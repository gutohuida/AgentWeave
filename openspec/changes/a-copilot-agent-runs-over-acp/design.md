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
  [--excluded-tools create edit apply_patch]    # spec turns (D9); R2: confirm Copilot's write-tool names
  [<runner flags>]                      # after transport sentinels are stripped, as for Codex
```

Why each flag is there:

- `--no-auto-update` pins the bundled version, so the version the gate reads is the version that
  runs (VERIFIED: 1.0.88).
- `--disable-builtin-mcps` removes `github-mcp-server` for hermetic runs (VERIFIED honoured). Its
  exposure as an option belongs to slice 5.
- `--model` and `--reasoning-effort` are spawn flags because `session/new` cannot carry them
  (appendix A §A).
- `--excluded-tools` is a spawn flag for the same reason.
- `--agent` is **not** passed, because it does not reach ACP (VERIFIED, `r1-probe-flag.log`).

**Environment.** The run environment the trigger already builds (`agent_trigger.py:1243-1304`,
covering `AW_*`, `HUB_URL`, and the strips) is passed to `copilot.exe`. The stdio MCP child inherits
it (VERIFIED), so `agentweave-mcp.json` carries **no secret and no `env` block**. It holds exactly
what Claude's `--mcp-config` holds (`runner_commands.py:251-259`), plus `tools: ["*"]` and `timeout`.

Two additions to that environment:

- `COPILOT_HOME=<the agent's Hub-owned home>` (D4).
- `GH_TOKEN`, `GITHUB_TOKEN` and `COPILOT_GITHUB_TOKEN` are removed unless the agent's `env_vars` name
  them. An ambient token silently overrides the operator's stored Copilot login (appendix A §E).
  This mirrors the ambient-`ANTHROPIC_BASE_URL` rule for Claude (`launchability.py:190-194`) and
  lives beside it in `resolve_agent_env`.

**The MCP `timeout`.** Copilot's MCP default is 30 s (DOCUMENTED). The Hub's `ask_user` blocks up to
`AW_QUESTION_TIMEOUT` (default 240 s, configurable to `MAX_WAITING_SECONDS` = 600,
`mcp_server.py:966-1005`). `archive_job` waits up to `AW_DECISION_TIMEOUT` on the operator. Every
such Copilot call would be cut at 30 s. The file therefore sets
`"timeout": (MAX_WAITING_SECONDS + 60) * 1000` = **660000**, a constant rather than the agent's own
setting, so that the file does not have to change when that setting does. `test_copilot_home.py`
binds the constant to `agents.MAX_WAITING_SECONDS`.

### D4 — The Hub-owned `COPILOT_HOME` and what is written into it (`ghcp-d1`, `ghcp-d2`)

**Where.** The home is `~/.agentweave/hub/copilot-home/<project_id>/<agent>/`, created with mode
0700 as `tool_server.py` creates its pin root (`tool_server.py:43-47`).

It is keyed by project id, not by Hub instance. The trial Hub and `:8000` have different databases
and so different project ids, so one agent's session store is never shared between them. An agent
name is unique per project (`ix_agents_project_name`), so the path is unique. Copilot's session
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
  (`agents.py:731-733`).
- **(b)** After `PATCH /agents/{name}` commits a change to the runner binding, the charter or the
  default model or effort of an agent whose resulting runner is `copilot` (`agents.py:2558`).
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

**Worker home.** A second home, `~/.agentweave/hub/copilot-home/_worker/`, is used by one-shot calls
(D14). `_worker` is not a valid agent name (`AGENT_NAME_RE` allows `_`, but the leading-underscore
directory sits beside project ids, never inside one), so it cannot collide.

### D5 — The stable context and the per-turn context (`ghcp-d1`)

`_render_hub_agent_context` (`agents.py:1605`) builds one `lines` list in one order and returns
`{"context": …}`. It gains two more keys and leaves `context` byte-identical (Claude and Codex keep
reading it):

- **`stable`**:
  - the title line (`agents.py:1703-1706`);
  - `## Project Instructions` (`:2109`);
  - `## Communication Mode` (`:2115`);
  - `## Charter…` (`:2132`/`:2137`);
  - the project name.

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
  run (`agent_trigger.py:1107-1112`), and `agents.py:1653-1665` requires the notice and the
  description of one turn to agree.

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
otherwise stand in for the Hub's file. Which one wins is not measured (Open question 2). The marker
check detects the substitution without having to know the answer.

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
- `_bind_session_id` takes an explicit `replace_missing=True` for exactly this call.
- Any other load error fails the turn, as `thread/resume` failures do for Codex.

### D8 — Approvals: `session/request_permission` → the Hub's judge (axis 2, no MCP dependency)

A pure `copilot_acp.decide_permission(params, *, posture, workspace, hub_url, mcp_server_names) ->
Decision` returns `ALLOW`, `REJECT` or `ASK_OPERATOR`, plus a reason. It maps each request onto
`mcp_server._decide`.

**Change to `_decide`.** `_decide` (`mcp_server.py:1543`) reads `AW_WORKSPACE_DIR` (`:1560`) and
`HUB_URL` (`:1191`, `:1241`) from `os.environ`. That is right in the spawned MCP process and wrong in
the Hub process, whose environment is not the run's. So `_decide`, `_is_own_hub` and `_judge_word`
gain keyword-only `workspace=None, hub_url=None`, which default to the environment. The Hub process
imports `mcp_server` already (`agents.py:1016`), and `mcp_server.py`'s stdlib-plus-fastmcp import
restriction is untouched. `test_permission_approver.py` gains a case asserting that the keyword
arguments override the environment.

**The mapping.** `decide_permission` matches `toolCall.kind` and `rawInput` (shapes are CODE,
§ VERIFIED). The judged tool name is `_decide`'s dialect key, from `_TOOL_DIALECTS`
(`mcp_server.py:1072`).

| Copilot request | Judged as | `workspace` | `acceptEdits` (emulated) |
|---|---|---|---|
| `kind:"execute"`, `rawInput.command` | `_decide("PowerShell" if Windows else "Bash", {"command": command})` | the judge | REJECT (Claude's `acceptEdits` prompts for `Bash`, which headless means refused) |
| `kind:"edit"`, `locations[].path` / `rawInput.fileName` | `_decide("Write", {"path": p})` for **each** path; REJECT if any refuses | the judge | the same judge (edits inside the workspace only) |
| `kind:"read"` (outside trusted dirs), `rawInput.path` split on `", "` | `_decide("Read", {"path": p})` each | the judge | the judge |
| `kind:"fetch"`, `rawInput.url` | ALLOW, as Claude's `WebFetch` is today: `_decide` reads no fetch URL (`mcp_server.py:1554-1555`) | ALLOW | REJECT |
| MCP whose server is `agentweave` | ALLOW, "the Hub's own tools" (`mcp_server.py:1557`) | ALLOW | ALLOW |
| MCP of another server | `_decide("mcp__<server>__<tool>", args)`, as Claude's approver judges foreign MCP tools today | the judge | REJECT |
| `memory`, `custom-tool`, `extension-*`, `factory`, anything unrecognised | REJECT, "not a request this Hub decides" | REJECT | REJECT |

**Identifying the MCP server.** The `toolCall` carries no server name; `title` is `toolTitle`, else
`server/tool` (CODE). The client therefore keeps a per-turn map `toolCallId → (serverName, toolName)`
from the raw `permission.requested` event (`permissionRequest{kind:"mcp", serverName, toolName}`,
VERIFIED in `acp4…log`), which is subscribed. When the event has not arrived, it falls back to
`title` split on `/` when it is exactly `agentweave/<tool>`. A request whose server cannot be
established is judged as foreign. Server name `agentweave` is the name the Hub registers (D4).

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
  Tonight's `an-ask-me-card-says-what-workspace-only-would-decide` changes what that card carries.
  This path calls whatever helper that change introduces, with the judged `_decide` inputs. Re-verify
  in R2.

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
- An **allow** is recorded as tonight's `a-run-records-that-its-calls-were-allowed` requires. That
  change reshapes both approval paths; this path calls its recorder in-process rather than over
  `POST /permission-decisions`. Re-verify in R2.

**Every request is answered.** `decide_permission` is total, and the loop answers each request
before reading the next message. A client error while deciding answers `reject_once`, never silence.
An unanswered request would hang the turn (`codex_appserver.py:255-258`).

### D9 — Specification and review turns

- **Specification turn** (`restrict_spec_writes=True`, `agent_trigger.py:1227`). It gets two things:
  1. **`--excluded-tools` over Copilot's write tools.** The tools are listed in the command reference
     (`create`, `edit`, `apply_patch`; R2 confirms the exact list against `copilot help` or the
     reference). It applies unconditionally, including under full access, which is the rule
     `_build_claude_command` states for `--disallowedTools` (`runner_commands.py:218-229`).
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
field; R2 confirms the field name against a captured event (task 1.1).

- An `Error:` match → `error_event(code="copilot_session_error", message=…)`.
- A `Warning:`/`Info:` match → a new `diagnostic_event(code, message)` builder in `runner_events.py`.
  That kind is in the closed set (`schemas/agents.py:19`) and has no builder today.
- An unmatched block stays `text`.

The version gate (D12) guarantees raw events exist.

**The Hub's own server failing.** A raw `session.mcp_servers_loaded` or
`session.mcp_server_status_changed` naming `agentweave` with a status that is not connected emits,
once per turn, the same message `map_mcp_server_failure` builds for Codex (`codex_appserver.py:547`),
under the code `copilot_mcp_server_failed`. Deciding the run's tool surface from that status is
slice 3's.

**Model substitution.** The raw `session.model_change` and `session.auto_mode_resolved` events name
the model Copilot actually runs. When the requested model was not `auto` and differs from the
resolved one, the mapper emits one `diagnostic`, for example: *"Copilot ran mai-code-1.1-flash
(Auto) instead of the requested claude-haiku-4.5; this plan allows: [mai-code-1.1-flash]."* The
list comes from `availableModels`. This is the Free plan's behaviour (VERIFIED), and without it an
operator would believe the requested model ran.

**Subscribed raw events.** The subscription is exactly:

- `session.error`, `session.warning`, `session.info`;
- `session.mcp_servers_loaded`, `session.mcp_server_status_changed`;
- `session.model_change`, `session.auto_mode_resolved`;
- `permission.requested`.

Slice 4 adds its own (`assistant.usage`, `session.usage_checkpoint`). The list is a module constant
so that slices extend it rather than re-declaring it.

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
processes. That is slice 4's work, together with `assistant.usage`. Tonight's
`an-estimate-that-misses-turns-says-so` decides how an unmeasured turn is presented. Re-verify in R2.

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

### D13 — Model catalog for `copilot`

A `CATALOG["copilot"]` `ProviderDescriptor` has `label="GitHub Copilot"`.

- **Models.** `auto` comes first (label "Auto", `default=True`, `context_window=None`), then the list
  printed by `copilot help config` under `model` (a command with no model call; VERIFIED output, 26
  ids today). The list is **embedded** as a static tuple, with labels derived from the id, and
  `context_window=None` for every entry: Copilot reports the window per turn (D11), and the
  requirement *Every model the catalog offers declares a context window or is stated as unknown*
  permits `None`.
- **No runtime parse.** A runtime parse of `help config` at catalog load was considered and rejected.
  `GET /model-catalog` would then spawn a process, and the catalog would change under a Hub that
  never restarted. A test (task 2.4) compares the tuple with a live `copilot help config` when the
  binary is present, and skips otherwise. A drift is fixed by editing the tuple, as
  `the-codex-models-offered-are-the-ones-its-cli-lists` does for Codex (re-verify in R2 which way
  that change went).
- **Controls.**
  - `effort` has values `low`, `medium`, `high`, `xhigh`, `max` and is applied as
    `ApplySpec("flag", "--reasoning-effort {value}")`. `none` and `minimal` are omitted to match the
    other providers' vocabulary.
  - `permission_mode` has the same four values and labels as Codex, applied as `ApplySpec("none")`
    (read at trigger time, D8).
- **Validation.** `validate_overrides` already refuses an undeclared model (`model_catalog.py:431`).
  That backstop matters more here, because `session/set_model` accepts `bogus-model` (VERIFIED,
  appendix A) and `--model` on Free is silently replaced.
- **`_CATALOG_PROVIDER_BY_RUNNER`** gains `"copilot": "copilot"` (or slice 1's
  `catalog_provider`).
- **`context_window_for_model`** searches every provider by id (`model_catalog.py:320`). `gpt-5.5`
  and `gpt-5.6-*` exist in both the Codex and Copilot catalogs, so a Copilot reading **without** a
  `size` would borrow Codex's window. D11 always has `size` from `usage_update`, so the path is not
  reached. Open question 7 records it.

### D14 — One-shot calls

`worker.build_worker_command` and `conversation_titles.build_title_command` each gain a `copilot`
branch, and `copilot` joins `worker.SUPPORTED_CLIS` (`worker.py:71`) and `_SUPPORTED_CLIS`
(`conversation_titles.py:68`).

```
<copilot.exe> -p <neutralised prompt> --output-format json --no-auto-update
  --disable-builtin-mcps --no-custom-instructions --no-ask-user
  --available-tools= --allow-all-tools [--model <m>]
```

- It runs with `COPILOT_HOME=<the _worker home>` and without the GitHub-token variables.
- `--allow-all-tools` is required for non-interactive mode (DOCUMENTED); with no tool available it
  grants nothing.
- Whether `--available-tools=` (empty) means "no tools" is **not verified**. Task 1.2 captures it,
  and falls back to `--excluded-tools` over the built-in tool list if not.
- `--no-custom-instructions` works under `-p` (appendix A §E).

**Where titles run.** The titler deliberately runs in the project's directory so the project's
memory applies (`conversation_titles.py:81-93`). For Copilot that memory is `CLAUDE.md`/`AGENTS.md`,
which `--no-custom-instructions` would drop. So the **title** branch omits
`--no-custom-instructions`, keeping the titler's intent, and the **worker** branch keeps it.

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
2. spawns it with `--acp --stdio --no-auto-update` under the `_worker` home;
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

The collaboration verdict (`agents.py:249-262`) needs no Copilot arm. Copilot's approvals never
depend on the tool surface, so it falls to `collaboration_ready = True` in the `else` branch.
Tonight's `a-runner-that-cannot-collaborate-says-so-where-it-is-bound` reshapes this block.
Re-verify in R2.

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
`terminate_all_active_runs` (`:1823`) reach Copilot runs with no new branch.

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
- `modelCatalogFixture.ts` gains the Copilot provider.
- The bundle is rebuilt and refreshed (`scripts/refresh_ui_bundle.py`), and `hub/ui/src` and
  `hub/hub/static/ui` are committed together.

## What each route returns when what it calls raises

- **`POST /agents` (create).**
  - `ensure_copilot_home` raising `OSError` is logged. The route still returns 201, because the
    agent row is committed and the next spawn retries (D4 (c)).
  - Launchability with a pending verdict returns runnable (D15).
  - A known "not signed in" or "too old" verdict returns today's 409 with that reason
    (`agents.py:718-723`).
- **`PATCH /agents/{name}`**: as for create, logged, and the route's own response is unchanged.
- **`POST /runners` with `cli: "copilot"`**: 201. Before the migration it would be an
  `IntegrityError`, which the migration removes.
- **`POST /agent/trigger` for a Copilot agent** (`trigger_agent_directly`):
  - executable not found → `TriggerAgentError(409)`, the probe's sentence;
  - `ensure_copilot_home` fails → 409 (D4);
  - the version gate or auth fails → the run is created and then fails, through the executor's
    pre-spawn `except` path (`agent_trigger.py:3244-3288`), with the sentence in `Run.error` and the
    entries returned to the queue;
  - `session/load` `-32002` → a new session (D7);
  - any other ACP error → a failed run, with `stderr_tail` carried as for Codex.
- **`GET /runners/launchability-by-provider`**: never raises for Copilot. A failing refresh is
  logged and the verdict records the failure as `reason`.
- **`GET /model-catalog`**: static, and cannot raise.
- **Worker and titles**: a missing executable → `spawn_failed`; unparseable JSONL → `unparseable`.
  These are the existing outcomes (`worker.py:74-83`).

## Sites touched by open changes (re-verify in R2)

| Open change (tonight's queue unless noted) | Where it meets this change |
|---|---|
| `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` | D16: the `tool_prefix` mechanism and the preamble |
| `the-permissions-pill-shows-the-posture-the-run-gets` | the `posture_at_rest` helper and the Claude default moving to `workspace`. Copilot's posture at rest is `workspace` whether or not MCP is injected, because its approver is the Hub over ACP |
| `an-ask-me-card-says-what-workspace-only-would-decide` | D8: the operator card's contents, and `codex_appserver`/`mcp_server` edits |
| `a-run-records-that-its-calls-were-allowed` | D8: recording allows (a migration) |
| `the-codex-models-offered-are-the-ones-its-cli-lists` | D13: the catalog shape and the provider source |
| `a-runner-that-cannot-collaborate-says-so-where-it-is-bound` | D15: launchability and the collaboration verdict |
| `an-estimate-that-misses-turns-says-so` | D11: how an unmeasured turn is shown |
| `agents-no-longer-register-themselves` (parked) | `launchability.py` and the migration numbering |
| `the-shell-judge-reads-a-word-whole` (parked) | D8: `_decide`'s signature change |
| `stop-clears-a-run-an-earlier-hub-left-running` (parked) | D17: the stop path per transport |
| `a-model-alias-is-a-model-choice` | D13: `auto` is a model id, not an alias |
| slice 1 `each-runner-cli-is-one-adapter` | D3, D17, D18: the adapter members, the RPC executor, the run-liveness set |
| slice 3 `a-run-reaches-the-hub-without-mcp` | D10: the MCP-server status events it will consume |

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
- **[`_decide`'s signature changes while `the-shell-judge-reads-a-word-whole` is parked]** →
  Keyword-only defaults keep every existing call unchanged.
- **[A migration reaches `:8000`]** → It only widens a check constraint. Downgrade refuses rather
  than deletes.

## Migration Plan

1. Deploy the migration with the code. Rollback is a downgrade, refused while a `copilot` runner
   exists.
2. `~/.agentweave/hub/copilot-home/` is created on the first Copilot agent. Removing it loses only
   Copilot session history; each agent's next turn starts a new session (D7).

## Open questions for R2/R3

1. **Does the agent file's body reach the model?** Selection is VERIFIED; delivery needs a model
   call. Task 1.1's capture asks the model to quote a marker from the agent file. If the marker does
   not come back, D6's fallback becomes the primary channel.
2. **User-level versus project-level custom agents of the same id: which wins?** D6 detects either
   outcome. R2 may find the rule in `app.js` (search the agent loader's merge order).
3. **Frontmatter `model` versus spawn `--model` for a session agent.** D4 (c) removes the conflict
   by writing both identically. Confirm nothing else reads the frontmatter model differently, for
   example subagents under Auto.
4. **The exact write-tool names for `--excluded-tools`** (D9), and whether `--available-tools=`
   empty means no tools for `-p` (D14). Both come from the command reference and task 1.2.
5. **The per-turn block's cost over a long conversation** (D5). Measure `used` growth across three
   resumed turns in the drive.
6. **Should `tool.execution_start` be subscribed** to learn the real shell tool name (D8), or is the
   platform rule enough? On this machine it is `powershell` (VERIFIED).
7. **`context_window_for_model` is provider-blind** (D13). Should it take a provider? It is not
   reached by D11, but a later path could hit it.
8. **Title cost on the Free plan** (D14). Should a Copilot conversation take Copilot's own
   `session_info_update` title instead of a one-shot call? Deferred to slice 5 unless R2 finds the
   one-shot titler spending the allowance in the drive.
9. **Where `_worker` sits.** Confirm no project id can be `_worker`. Project ids are `proj-<hex>`
   today.
10. **The exact field names of `session.error|warning|info` raw event data** (D10), from the task
    1.1 capture.

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

- **Pending:**
  - R2: an independent re-derivation.
  - R3: an independent re-derivation.
  - Opus adversarial review.

## Cross-slice consistency (orchestrator, 2026-09-27, after all five R1s)

For R2 to reconcile against `each-runner-cli-is-one-adapter`'s design:
- This design says `resume_id`. Slice 1 carries the resume id as `RpcTurnRequest.resume_session_id`, and has no `resume_id` member.
- This design says `tool_prefix`. Slice 1 names it `mcp_tool_prefix`, which replaces tonight's `tool_prefix` and `CLAUDE_FAMILY_RUNNERS`.
- Slice 3 adds `tests_mcp_before_first_prompt` and slice 4 needs `compaction_percent`, which slice 1 lists as a deferred contract. Whichever change lands first adds the member.
- Migrations: slices 2, 3, 4 and 5 each add one, and slice 1 none. Numbers are assigned in build order after tonight's queue, which takes numbers from `0111`.
