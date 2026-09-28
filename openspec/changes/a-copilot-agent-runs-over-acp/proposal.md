# Proposal — a Copilot agent runs over ACP

**Depends on:** the `RunnerAdapter` of `each-runner-cli-is-one-adapter` (slice 1, unbuilt at R2).
This change implements that adapter for `copilot` as an **RPC** transport, so it uses slice 1's
names (R2, against slice 1's design of 2026-09-28; the full mapping is in `design.md` § "Slice 1
member names"):

- on the adapter: `transport`, `posture_at_rest`, `one_shot`, `parse_one_shot`, `guard_env`,
  `collaboration`, `launchability`, and the ClassVars `catalog_provider`, `write_tool_kinds`,
  `mcp_tool_prefix`, `transport_sentinels`, `mcp_env_names`;
- on the RPC transport: `inject_mcp`, `instruction_channel`, `posture_for`,
  `permission_card_label`, `refusal_label`, `context_window_source`, and
  `run_turn(req: RpcTurnRequest, cb: RpcCallbacks)`;
- slice 1's deferred D16 members, which this slice defines: `write_native_files`, `agent_home`,
  `version_gate`, `models`.

R1's `build_launch`, `map_events` and `usage_from` are stream-transport members and do not apply;
`resume_id` is `RpcTurnRequest.resume_session_id`; `stop` is a clause of `run_turn`'s contract.
This change adds `per_turn_context`, `tool_surface_context`, `stable_context`, `control_overrides`
and `told_access_path` to `RpcTurnRequest` (`restrict_spec_writes` and `extra_flags` are slice 1's
own), and `on_session_missing` to `RpcCallbacks` (R3: R2's `on_raw_event` is removed, since slice 4
does not use it). What slices 3–5 get from this change is listed in `design.md` § "Provided to
slices 3–5".

**Round 3, 2026-09-28** changed four behaviours:

- an MCP call's server is taken only from Copilot's own raw report of the call, never from a tool
  call's title, which the model writes;
- failures after the prompt are returned as a failed turn, not raised as a failure to start;
- a Copilot session error fails the turn;
- refusals about the agent's Copilot home or executable hold the input rather than count against
  it.

It also meets eight changes of the 2026-09-27 night queue and three parked ones. At R2 (master
`ef55e6f`) three of those have landed and the rest are unbuilt; `design.md` § "Sites touched by open
changes" gives each one's state and marks the unbuilt sites "rebase at IMPL".

**Round 1, 2026-09-27; Round 2, 2026-09-28.** Slice 2 of five from
`openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. Operator decisions `ghcp-d1`–`ghcp-d6`
(`spec-queue/DECISIONS.md`, `### 2026-09-27`) bind it. **Nothing here is implemented yet.**

## Why

The operator wants GitHub Copilot CLI (`copilot`) as a full runner, at parity with Claude and Codex:
*"Mapping everything that we have today, the functionalities that we use with claude code and codex
to be used with ghcp as well."* Today the Hub cannot run a Copilot agent at all:

- `RUNNER_CLIS = ("claude", "codex")` (`hub/hub/db/models.py:311`), and `runners.cli` carries a
  database check constraint `cli IN ('claude', 'codex')` (`models.py:340`, created by migration
  `0023_add_runner_charter.py:32`). A `copilot` runner cannot be created.
- `build_command` raises `UnsupportedRunnerError` for anything but Claude and Codex
  (`hub/hub/runner_commands.py:193`). The trigger turns that into HTTP 501
  (`hub/hub/api/v1/agent_trigger.py:1230`).
- `launchability.py:116-126` still holds a dead Copilot branch. It calls a Copilot agent authorized
  only when `GH_TOKEN`, `GITHUB_TOKEN` or `COPILOT_GITHUB_TOKEN` is set. That test is wrong in both
  directions: the operator's Copilot login lives in the Windows Credential Manager, and a token in
  the environment silently *overrides* that login (appendix A §E).

The exploration settled the transport. `copilot -p` cannot ask anybody (`--allow-all-tools` is
"required for non-interactive mode"), so an agent on it could collaborate only under yolo. That is
the reason `codex exec` stopped being Codex's default. **ACP** (`copilot --acp`) is Copilot's
counterpart of `codex app-server`: a JSON-RPC peer over stdio in which the Hub answers every
`session/request_permission` itself. That answer does not depend on MCP, which is what makes Copilot
the first runner whose approval axis is independent of its tool surface.

## What Changes

- **`copilot` becomes a runner CLI.** `RUNNER_CLIS` gains `copilot`. A migration widens
  `ck_runners_cli`. A project with no runners is seeded with a default `copilot` runner beside the
  other two. The three gates that do not follow `RUNNER_CLIS` also admit it (R2):
  `SUPPORTED_RUNNERS` (today a 501 at `agent_trigger.py:773`), the trigger's `build_command` call
  (a 501 at `:1230`), and `MCP_INJECTABLE_RUNNERS` (`launchability.py:230`), without which the Hub's
  MCP server would never be injected into a Copilot run.
- **An ACP client transport** (`hub/hub/copilot_acp.py`), modelled on `codex_appserver.py`. It uses
  one `copilot.exe` process per turn, spawned **directly** and never through the npm shim. The
  process is started with `--acp --stdio --no-auto-update --disable-builtin-mcps --additional-mcp-config
  @<file>`, plus `--model`/`--reasoning-effort` and `--excluded-tools` on specification turns. Each
  turn runs:
  1. `initialize`, subscribing to Copilot's raw session events;
  2. a version gate at **1.0.81**;
  3. `session/new`, or `session/load` of `Conversation.provider_session_id`, whose history replay is
     discarded;
  4. selection of the agent's custom agent;
  5. `session/prompt`.

  The turn is stopped with `session/cancel` and then a kill of the process tree.
- **A Hub-owned `COPILOT_HOME` per agent** (`ghcp-d2`), at
  `~/.agentweave/hub/copilot-home/projects/<project_id>/<agent>/`, each component validated (a
  project id comes from a folder's marker on adoption, so it is not always `proj-<hex>`). It holds
  two files:
  - `agents/<agent>.agent.md` carries the agent's **stable context** (`ghcp-d1`): identity, project
    instructions, charter and a precedence statement over the repository's `CLAUDE.md`/`.claude/`.
    Its frontmatter carries `tools`, `model` and `reasoningEffort`.
  - `agentweave-mcp.json` is the stdio `agentweave` server entry. Its `timeout` covers the Hub's
    longest wait, because Copilot's own default of 30 s would end every `ask_user` early.

  Both files are written when a Copilot agent is created and when its settings change. They are
  re-ensured before every spawn, so an edited charter reaches the next turn as it does today.
  Per-turn material (workspace, specification, team, history, turn notices) stays in the prompt.
- **R1 probe, no model call (VERIFIED on 1.0.88):**
  - With a file in `$COPILOT_HOME/agents`, `session/new` offers an `agent` config option, and
    `session/set_config_option` selects it.
  - `--agent` at spawn does **not** reach an ACP session.
  - The Hub's fastmcp server answers Copilot's `server/discover` with a JSON-RPC error, and Copilot
    then connects it (`agentweave (connected)`).
  - A stdio MCP child inherits `copilot.exe`'s environment, so the run token needs no config file.

  The fallback channel (an embedded resource on the prompt) is kept only for the case where a
  same-named repository agent shadows the Hub's.
- **Posture over ACP.**
  - `workspace` sends each `session/request_permission` to the same shell and path judge as
    `_decide`, with no MCP dependency. Copilot's `powershell` tool is judged in the PowerShell
    dialect.
  - `manual` ("Ask me") opens an operator card while the request is held open.
  - Full access sets the `allow_all` config option. When an organisation's policy has removed that
    option, the run falls back to `workspace` and says why.
  - `acceptEdits` is emulated: an edit inside the workspace is allowed and everything else is
    refused.
  - A run with no posture chosen is judged as `workspace`, and the catalog's Permissions default for
    `copilot` is `workspace` to match (Copilot has no sandbox of its own to fall back on).
  - A specification turn gets `--excluded-tools` over Copilot's write tools. Plan mode (the
    full-URI `session/set_mode`) ships **off** until a drive shows it cannot hang on
    `exit_plan_mode` (review 2026-09-28).
  - The Hub's own `agentweave` tools are always allowed, when Copilot reports them from the Hub's
    own server config (not a workspace or plugin source). Every request is answered.
  - (Review 2026-09-28.) The Hub judges only what Copilot asks: Copilot runs commands it classes
    read-only without a request, and the spec says so. A `url` request is allowed only from
    Copilot's `web_fetch` without a sandbox bypass; a shell's is judged as shell text. The session
    mode is set on every turn and allow-all is verified off before the prompt under every posture
    but full access. Runner flags that widen Copilot's own approvals are removed, and the agent's
    Copilot home is swept of hooks and settings the Hub did not write. The judge runs off the event
    loop.
- **An ACP event mapper** into the closed `runner_events` kinds:
  - message and thought chunks are accumulated per block;
  - `tool_call`/`tool_call_update` carry locations and diffs;
  - `plan` becomes a plan status;
  - `Error:`/`Warning:`/`Info:` text that matches a raw `session.error|warning|info` event becomes
    an error or diagnostic event, and a `session.error` fails the turn;
  - an MCP call is labelled by the server Copilot reports for it, not by the kind Copilot guesses
    from its name;
  - a failed `agentweave` MCP server is reported, as an error for a run told the MCP form and as a
    diagnostic otherwise.
- **Context meter** from `usage_update {used, size}`. **Accounting** records the turn as unmeasured;
  per-call usage and credits are slice 4.
- **One-shot calls** (`worker.py`, `conversation_titles.py`) use `copilot -p --output-format json`,
  with every tool excluded (`--excluded-tools=builtin:*,mcp:*,custom:*`; an empty
  `--available-tools=` would grant them all), under a Hub-owned worker home. Titles parse the JSON
  envelope before titling.
- **Model catalog** for `copilot`: `auto` (label "Auto", the default) plus the models listed by
  `copilot help config`, with Effort and Permissions controls. The Hub validates the model, because
  `session/set_model` accepts anything. When Copilot runs a different model than the one requested
  (the Free plan forces Auto), the run says so.
- **Launchability** checks that `copilot.exe` resolves, reads its version, and checks authorization
  through ACP (`initialize`, then `session/new` on a Hub-owned probe home, cached). This replaces
  the dead env-token branch.
- **Tool names** in the tool surface are `agentweave-<tool>` for Copilot runs, using the prefix
  mechanism that `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` introduces.
- **The run environment** never carries `GH_TOKEN`, `GITHUB_TOKEN` or `COPILOT_GITHUB_TOKEN` unless
  the agent's own `env_vars` name them, and never carries `COPILOT_ALLOW_ALL` or Copilot's other
  allow/trust variables, even when `env_vars` name them (review 2026-09-28; every Copilot spawn).
- **UI changes:**
  - `RunnerCli` gains `'copilot'`, and so do `CLI_OPTIONS` and `providerForRunner`;
  - the timeline marks Copilot's `edit`/`delete`/`move` rows as writes;
  - a Copilot provider mark (`simple-icons` `githubcopilot`);
  - the picker offers Auto;
  - the catalog test fixture covers Copilot.

  The bundle is refreshed per `.claude/rules/hub-ui.md`.

## Out of scope (other slices)

- Reaching the Hub when policy blocks MCP (shim, per-run MCP detection, F299/F301/F340): **slice 3**,
  `a-run-reaches-the-hub-without-mcp`.
- AI credits, premium requests, per-call usage from `assistant.usage`, differencing the cumulative
  prompt usage, quota holds and per-runner compaction thresholds: **slice 4**,
  `a-copilot-run-shows-its-credits`.
- Hooks in `COPILOT_HOME`, built-in Copilot agents as flow steps, BYOK: **slice 5**,
  `a-copilot-agent-uses-hooks-and-its-own-agents`.
- The Copilot MXC sandbox, `/delegate`, `--remote`, autopilot and fleet.

## Capabilities

### New Capabilities

None. Every behaviour lands in an existing capability.

### Modified Capabilities

- `runner-registry`: two MODIFIED requirements.
  - *Runners are project-scoped Hub records*: the supported set becomes `claude`, `codex`, `copilot`.
  - *Built-in runners are seeded on first use*: the seed includes `copilot`.

  Four ADDED requirements:
  - *A Copilot runner is spawned as its own executable*;
  - *A Copilot runner below the supported version is refused*;
  - (R3) *A Copilot turn that fails after its prompt ends as a failed turn, not a failed start*;
  - *Copilot launchability is read from Copilot itself*.
- `agent-run-sandboxing`: ADDED *A Copilot run's posture is decided by the Hub over ACP* and *A
  Copilot run receives no GitHub token or permission override it was not given*.
- `agent-stream-events`: MODIFIED *Supported runner normalization* and *Stream contract conformance
  tests*, which add Copilot ACP. ADDED *A resumed Copilot session's history is not rendered again*.
- `agent-context-usage`: ADDED *Copilot context mapping*.
- `model-catalog`: ADDED *The Copilot catalog offers Auto and validates what Copilot would not*.
- `operator-agent-creation`: ADDED *A Copilot agent's native files are written into a Hub-owned
  home*.
- `agent-tool-surface`: ADDED *A Copilot run's MCP tool calls outlast the Hub's longest wait*.
- `conversation-checkpoint` (R2): ADDED *A Copilot worker invocation is offered no tool*.

## Impact

- **Backend.**
  - New: `hub/hub/copilot_acp.py`, `hub/hub/copilot_home.py`, `hub/hub/copilot_probe.py`.
  - Changed: `db/models.py`, `db/engine.py`, `project_lifecycle.py`, `schemas/runners.py`
    (derived), `api/v1/runners.py`, `runner_commands.py` (`SUPPORTED_RUNNERS`,
    `_CATALOG_PROVIDER_BY_RUNNER`; or slice 1's adapter registry), `launchability.py`
    (`MCP_INJECTABLE_RUNNERS`, the probe, the token strip), `model_catalog.py`, `workspace_writes.py`, `runner_events.py` (a
    `diagnostic_event` builder), `worker.py`, `conversation_titles.py`, `api/v1/agent_trigger.py`
    (executor), `api/v1/agents.py` (context split, `_display_model`, file writes on create and on
    PATCH).
  - `mcp_server.py`: `_decide` gains keyword arguments for the workspace and Hub URL, so the Hub can
    call it in-process. The import restriction is unchanged.
- **Migration.** One revision (the next free number after tonight's queue) recreates `runners` with
  `ck_runners_cli IN ('claude','codex','copilot')`. The head assertions in `test_migrations.py` and
  `test_project_persistence.py` are bumped. It reaches `:8000` on the operator's next restart; it
  only widens a constraint.
- **Scripts.** `scripts/check_model_catalog.py` gains a Copilot comparison (drift is checked there,
  not by a test that can only skip in CI).
- **UI.** `hub/ui/src` and the committed bundle `hub/hub/static/ui` are committed together. They reach
  `:8000` on the operator's next reload.
- **Files outside the repo.** `~/.agentweave/hub/copilot-home/{projects,worker}/…`, Hub-owned, with the same standing as
  `~/.agentweave/hub/tool-server/`.
