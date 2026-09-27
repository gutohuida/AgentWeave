# Design — each runner CLI is one adapter

Line numbers are from master `97b86ed` as read on 2026-09-27, before the night ORDER. Where a site is
edited by a change in that ORDER, the change is named and the line is marked **(re-verify in R2)**.

## What is verified, and about what

This change touches no Copilot code, and its proof is about Claude and Codex only.
- **VERIFIED (read today):** every statement below about AgentWeave code, with its `file:line`.
- **Not measured:** Codex runs. Codex is undrivable because the plan was cancelled on 2026-08-29, so Codex equivalence is
  proved by golden files and unit tests, never by a run.
- **Copilot facts** appear only where they shape the contract (D3, D4, D16). They come from appendix A of the
  exploration and keep its tags: ACP `session/request_permission` is a Hub-answered approval channel independent of
  MCP (VERIFIED-LOCAL); stdio MCP reaches an ACP session only through `--additional-mcp-config` (VERIFIED-LOCAL); ACP
  prompt usage is cumulative per session (VERIFIED-LOCAL); `GH_TOKEN`/`GITHUB_TOKEN`/`COPILOT_GITHUB_TOKEN` override
  the stored login (DOCUMENTED). Nothing in this change depends on any of them being true.

## D1 — An abstract base class per runner, and one per transport

`hub/hub/runner_adapters/` (new package):

| Module | Holds |
|---|---|
| `base.py` | `RunnerAdapter`, `StreamTransport`, `RpcTransport` (all `abc.ABC`), and the value types `LaunchRequest`, `AccessAxes`, `LaunchVerdict` (a `TypedDict` with today's `probe_agent` keys), `RpcTurnRequest`, `RpcCallbacks` |
| `claude.py` | `ClaudeAdapter`, `ClaudeStreamTransport` |
| `codex.py` | `CodexAdapter`, `CodexExecTransport` (stream), `CodexAppServerTransport` (rpc) |
| `one_shot.py` | `WorkerUsage`, `extract_json_object`, `_int_or_none`, moved from `worker.py` (D8) |
| `__init__.py` | `ADAPTERS: Mapping[str, RunnerAdapter]` (`{"claude": ClaudeAdapter(), "codex": CodexAdapter()}`, in that order), `get_adapter(cli) -> Optional[RunnerAdapter]`, `build_command(...)` (D6), `resolve_access_axes(...)` (D4) |

**Why an ABC and not a `typing.Protocol`.** An adapter that leaves out a member has to fail when the table is built,
not when a run reaches the missing branch. An ABC refuses to instantiate with an abstract member unimplemented, so a
slice-2 `CopilotAdapter` missing `one_shot` fails at import. A Protocol is only checked by mypy, and `mypy` runs
over `src/` only (CLAUDE.md, *Code quality*). So a Protocol gives the Hub no check at all.

**Why the transport is its own object.** Codex has two transports, `exec` (a stream) and `app-server` (an RPC peer).
A runner's flags pick between them (`codex_appserver.uses_app_server`, `:79-89`). Copilot will have one RPC transport,
ACP. The members that differ by transport sit on the transport: argv, parsing, spawn kind, post-run accounting,
approval channel and instruction channel. The members that differ by runner sit on the adapter. `adapter.transport(flags)`
returns the transport that runs. The spec requirement *A runner's flags may select a transport*
(`runner-registry` `:162`) is unchanged.

**Why the existing modules stay.** `runner_commands.py`, `runner_parsing.py` and `codex_appserver.py` keep their
builders, parsers and protocol code, with their bodies unchanged except for two mechanical edits. First, each
builder's MCP fragment is extracted into a function it calls at the same position, `_claude_mcp_args` (from `:250-273`)
and `_codex_exec_mcp_args` (from `:317-329`), and `inject_mcp` returns that function's result. Second,
`_build_claude_command` takes `approvals` (D4). The golden argv tests prove both edits changed nothing. The adapters
call these modules. Moving those bodies would
be a large diff through code that seven of the night's changes edit, and it buys nothing: the thing being removed is
the *dispatch*, not the code it dispatches to.

**Import direction (no cycles).** `runner_adapters` imports `runner_commands`, `runner_parsing`, `codex_appserver`,
`model_catalog`, `pty_runner`, `workspace_writes` and `file_mentions`. It imports nothing that reaches the database.
`launchability`, `worker`, `conversation_titles`, `api/v1/agent_trigger`, `api/v1/agents` and `api/v1/runners` import
`runner_adapters`. Nothing `runner_adapters` imports may import it back. Task 2.1 adds a test for that.

## D2 — The table is `ADAPTERS`; `RUNNER_CLIS` and the database constraint stay, bound to it by a test

`RUNNER_CLIS = ("claude", "codex")` (`db/models.py:311`) stays where it is. The runners table carries
`CheckConstraint("cli IN ('claude', 'codex')", name="ck_runners_cli")` (`db/models.py:340`, created by migration
`0023_add_runner_charter.py`). Moving the tuple would not move the constraint, and this change adds no migration.

A conformance test (task 1.5) asserts that four sets are equal, in order where order is observable:
`tuple(ADAPTERS)`, `RUNNER_CLIS`, the values parsed from `ck_runners_cli`'s SQL text, and `tuple(CATALOG)`
(`model_catalog.py:163-276`). `GET /runners/launchability-by-provider` iterates `RUNNER_CLIS` today
(`api/v1/runners.py:116-118`) and iterates `ADAPTERS` after this change. The test asserts the response's key order
is the same.

**For slice 2:** adding `copilot` is one adapter, one `ADAPTERS` row, one `RUNNER_CLIS` entry, one `CATALOG` entry,
and **a migration that rebuilds `runners` to widen `ck_runners_cli`**. Without that migration, SQLite refuses the
insert even though the schema validator (`schemas/runners.py:22-23`) accepts it. The conformance test fails until all
four are done.

## D3 — The members, and the names the other slices use

The brief names twelve members. Each maps to concrete members below. Signatures are Python and abridged. Each
docstring states its contract.

### On `RunnerAdapter`

| Member | Signature | Contract | Claude | Codex |
|---|---|---|---|---|
| `name` | `ClassVar[str]` | The `Runner.cli` value. It is the `ADAPTERS` key. | `"claude"` | `"codex"` |
| `binary` | `ClassVar[str]` | The executable looked up on PATH when no `cli` override is configured. | `"claude"` | `"codex"` |
| `display_name` | `ClassVar[str]` | The model fallback in the agents list when a runner records no model (`agents.py:557-564`). | `"Claude"` | `"Codex"` |
| **`catalog_provider`** | `ClassVar[str]` | The `CATALOG` key whose models and controls this runner renders. It replaces `catalog_provider_for_runner`. | `"claude"` | `"codex"` |
| **`launchability`** | `(agent: str, config: Mapping) -> LaunchVerdict` | Is the binary present, and is the harness authorised? Same keys as `probe_agent` returns today (`launchability.py:135-142`). It must not raise. | `probe_binary` only (today's non-proxy path, `:91-99`) | same |
| `collaboration` | `(flags: Sequence[str], *, yolo: bool) -> tuple[bool, Optional[str]]` | Can a triggered run collaborate? It is called only for a bound, runnable agent whose Hub address is known (`agents.py:239-262`). **(re-verify in R2**: `a-runner-that-cannot-collaborate-says-so-where-it-is-bound` moves where the reason is shown.) | `(True, None)` | today's `agents.py:249-261` branch, text unchanged |
| `guard_env` | `(proc_env: Optional[dict], env_vars: Mapping) -> Optional[dict]` | Strips ambient variables that would silently redirect this harness's auth or endpoint. It runs last in `resolve_agent_env`. | today's `ANTHROPIC_BASE_URL` guard (`launchability.py:190-194`) | identity |
| `transport_sentinels` | `ClassVar[tuple[str, ...]]` | Flags that select this runner's transport. The trigger strips the **union over every adapter** from argv, whichever runner is spawned. Today the Codex sentinels are stripped from every runner's flags, a Claude runner's included (`agent_trigger.py:1209-1211`), and a per-adapter strip would stop doing that for Claude. | `()` | `TRANSPORT_SENTINELS` (`codex_appserver.py:76`) |
| `transport` | `(flags: Sequence[str]) -> StreamTransport \| RpcTransport` | The transport a run with these flags uses. | `ClaudeStreamTransport` | `CodexAppServerTransport` unless `--no-app-server` (`uses_app_server` logic, `:79-89`) |
| **`decide_posture`** (at rest) | `posture_at_rest(axes: AccessAxes, *, yolo: bool) -> str` | The posture a run gets when no override states one. It reads `axes.approvals`, not the tool surface (D4). **(re-verify in R2**: it replaces `runner_commands.posture_at_rest(provider, access_path, yolo)` from `the-permissions-pill-shows-the-posture-the-run-gets`, design D1.) | `workspace` if `approvals != "none"`, else `acceptEdits`; `bypassPermissions` if `yolo` | per that change's D4(c): Codex's displayed default, unchanged |
| `mcp_tool_prefix` | `ClassVar[Optional[str]]` | How this harness addresses the Hub's MCP tools, when known. **(re-verify in R2**: it replaces `CLAUDE_FAMILY_RUNNERS` + `tool_prefix` from `a-claude-run-is-told-its-agentweave-tools-by-their-full-names`.) | `"mcp__agentweave__"` | `None` |
| `host_tool_note` | `ClassVar[Optional[str]]` | That change's sentence about the host's own similar-named tool. | its `SendMessage` sentence | `None` |
| `mcp_env_names` | `ClassVar[Optional[tuple[str, ...]]]` | Which run variables reach the MCP child. `None` means the child inherits the whole run environment. | `None` (`runner_commands.py:250-262` sets no `env`) | the five names at `runner_commands.py:322-328` and `codex_appserver.py:969-980`, declared once (D12) |
| **`write_tool_kinds`** | `ClassVar[Mapping[str, str]]` | Tool name → the input key naming the file it writes, or `"changes[].path"`. It must be a subset of `workspace_writes.WRITE_TOOLS`, and disjoint from every other adapter's keys (D7). | `CLAUDE_WRITE_TOOLS` (`workspace_writes.py:39-44`) | `{CODEX_WRITE_TOOL: "changes[].path"}` (`:49`) |
| **`one_shot`** | `(purpose: Literal["worker", "title"], *, model: Optional[str], prompt: str, output_schema_path: Optional[str] = None) -> list[str]` | A no-tools, one-prompt invocation. The prompt is already neutralised for `@`. | today's `worker.py:142-146`, `conversation_titles.py:86-90` | `worker.py:147-153`, `conversation_titles.py:91-95` |
| `one_shot_takes_schema` | `ClassVar[bool]` | The worker must write an output-schema file first (`worker.py:450-453`). | `False` | `True` |
| `parse_one_shot` | `(stdout: str) -> tuple[Optional[str], WorkerUsage, Optional[str]]` | The worker envelope. | `parse_claude_envelope` (`worker.py:238`) | `parse_codex_envelope` (`:271`) |

### On `StreamTransport` (a process whose stdout is parsed line by line)

| Member | Signature | Contract | Claude | Codex `exec` |
|---|---|---|---|---|
| `kind` | `"stream"` | | | |
| `spawn_kind` | `ClassVar[Literal["pty", "pipe"]]` | Which `pty_runner` session class spawns the process. | `"pty"` | `"pipe"` (`agent_trigger.py:2345-2359`) |
| **`build_launch`** | `(req: LaunchRequest) -> list[str]` | The full argv. `LaunchRequest` has today's `build_command` parameters plus `axes`. **It includes `inject_mcp` and `instruction_channel`**, in today's argv positions. Raises only `UnsupportedRunnerError`. | `_build_claude_command` (`runner_commands.py:199-288`) | `_build_codex_command` (`:291-357`) |
| **`inject_mcp`** | `(mcp_command: list[str], *, yolo: bool) -> list[str]` | The argv fragment that makes the harness start the Hub's tool server with `mcp_env_names` reaching it. `build_launch` calls it. | `--mcp-config …` plus `--allowedTools` (`:250-262`) | the three `-c mcp_servers.agentweave.*` (`:317-329`) |
| **`instruction_channel`** | `ClassVar[Optional[str]]` | How the rendered context file reaches the model. `None` means it does not. | `"--append-system-prompt-file"` (`:248-249`) | `"-c model_instructions_file"` (`:330-331`) |
| `approval_channel` | `(tool_surface: str) -> Literal["mcp_permission_tool", "rpc", "none"]` | Axis 2 for this transport (D4). | `"mcp_permission_tool"` if `tool_surface == "mcp"`, else `"none"` | `"none"` (no live approvals; `runner_commands.py:14-17`) |
| **`map_events`** | `(line: str, *, model: Optional[str]) -> ParsedLine` | One line of stdout (ANSI already stripped) to events, usage, accounting and session id. It must not raise. | `parse_claude_line(line)` | `parse_codex_line(line, model=model)` |
| **`usage_from`** | `(*, session_id: str, env: Optional[dict], model: Optional[str]) -> Optional[AccountingSample]` | Accounting read after the process exits, merged over per-line accounting. It is called only when a session id is known. | `None` | `read_codex_rollout_accounting` with `CODEX_HOME` from `env` (`agent_trigger.py:2574-2587`) |
| **`context_window`** | `context_window_source: ClassVar[Literal["reported", "catalog"]]` | Where this transport's usage samples take their window from. A conformance test pins it to the parser's behaviour (D13). | `"reported"` (`runner_parsing.py:11-17`) | `"catalog"` (`runner_parsing.py:402`) |
| **`stop`** | (no member) | A stream is stopped by killing its process tree. That is generic (`stop_agent_run`, `agent_trigger.py:1773-1776`; `terminate_all_active_runs`, `:1820-1822`), so no adapter code exists for it. | | |

### On `RpcTransport` (a JSON-RPC peer the Hub drives)

| Member | Signature | Contract | Codex `app-server` |
|---|---|---|---|
| `kind` | `"rpc"` | | |
| `approval_channel` | `(tool_surface: str) -> "rpc"` | The Hub answers every server→client request. This does not depend on the tool surface. | `"rpc"` |
| **`instruction_channel`** | `ClassVar[Optional[str]]` | As above. | `None`. F325 is open, and D11 covers it |
| **`decide_posture`** (per run) | `posture_for(permission_mode: Optional[str]) -> Optional[str]` | Maps the operator's posture onto what the transport's decision function reads. | `_codex_posture` (`agent_trigger.py:2926-2952`), moved unchanged |
| `permission_card_label` | `(method: str) -> str` | The `tool_name` an ask-me card shows. | `_CODEX_APPROVAL_LABELS.get(method, method)` (`agent_trigger.py:2920-2923`) |
| `refusal_label` | `(method: str) -> str` | The `tool_name` a `permission_denied` event carries. | `codex_appserver.approval_label` (`:194-196`) |
| **`context_window`** | `context_window_source` | As on `StreamTransport`. | `"reported"`: app-server sends `modelContextWindow` itself (`codex_appserver.py:303-311`) |
| **`inject_mcp`** | `(mcp_command: list[str]) -> dict` | The config entry that starts the Hub's tool server in this peer. | `mcp_server_config(mcp_command, env_vars=list(mcp_env_names))` (`codex_appserver.py:652-662`) |
| `run_turn` | `async (req: RpcTurnRequest, cb: RpcCallbacks) -> TurnOutcome` | Spawn the peer, start or resume, send the prompt, answer every request, and map every notification to `cb.on_event` / `on_usage` / `on_accounting` (**`map_events`**, **`usage_from`**). Call `cb.on_session(id)` before the first `on_event`. **`stop`: honour `cb.should_interrupt()` within one poll interval and leave no process behind.** Raise only `FileNotFoundError`, `OSError`, `asyncio.TimeoutError` or `AppServerError` (the tuple `agent_trigger.py:3244` catches). | wraps `codex_appserver.run_turn` (`:904`) with today's arguments (`agent_trigger.py:3217-3243`) |

`RpcTurnRequest` carries `cli, cwd, env, prompt, model, resume_session_id, yolo, mcp_command, config_overrides,
permission_mode, workspace`. `RpcCallbacks` carries `on_event, on_usage, on_accounting, on_session, should_interrupt,
request_approval, on_refusal`. **(re-verify in R2:** `a-run-records-that-its-calls-were-allowed` adds `on_decision`,
and `an-ask-me-card-says-what-workspace-only-would-decide` adds `workspace=` to `_await_operator_permission` plus
`codex_appserver.workspace_verdict`. Both become fields or members here.)

## D4 — Three axes, resolved separately

```python
@dataclass(frozen=True)
class AccessAxes:
    tool_surface: Literal["mcp", "none"]                       # axis 1: is the Hub's MCP server injected
    approvals: Literal["mcp_permission_tool", "rpc", "none"]   # axis 2: how the Hub answers tool calls
    plane: Literal["mcp", "cli"]                               # axis 3: what the run is *given* to reach the plane

def resolve_access_axes(adapter, *, hub_client: Optional[str], flags: Sequence[str]) -> AccessAxes:
    tool_surface = "none" if hub_client == "cli" else "mcp"
    transport = adapter.transport(flags)
    return AccessAxes(tool_surface, transport.approval_channel(tool_surface),
                      "mcp" if tool_surface == "mcp" else "cli")
```

`plane` keeps today's string values (`"mcp"`/`"cli"`), because `described_access_path`, `access_path_notice` and
`_render_hub_agent_context(access_path=…)` take them (`launchability.py:283-315`, `:402`; `agent_trigger.py:1131`).
What the run is *told* stays `described_access_path(axes.plane, …)`. It is unchanged, and it is still separate from
what the run is *given*.

**Today's values, reproduced:**

| Runner, transport | `hub_client` | Today | `tool_surface` | `approvals` | `plane` |
|---|---|---|---|---|---|
| claude | unset / `mcp` | `"mcp"`, `--permission-prompt-tool` when defaulted (`runner_commands.py:243-273`) | `mcp` | `mcp_permission_tool` | `mcp` |
| claude | `cli` | `"cli"`, no server, default `acceptEdits` (`:238-242`) | `none` | `none` | `cli` |
| codex app-server | unset / `mcp` | `"mcp"`, server in thread config; the Hub answers requests | `mcp` | `rpc` | `mcp` |
| codex app-server | `cli` | `"cli"`, no server; **the Hub still answers requests** (`agent_trigger.py:3217-3243` passes `posture` and `request_approval` whatever `mcp_command` is) | `none` | `rpc` | `cli` |
| codex exec | any | no live approvals (`runner_commands.py:14-17`) | as `hub_client` | `none` | as `hub_client` |

The fourth row is the one fact this makes visible: **for Codex app-server, axis 2 already does not follow axis 1.**
Copilot over ACP has the same shape (exploration, "The 09-20 question, answered"). So splitting the axes adds no new
behaviour. It names a distinction that already exists.

**Consumers after the change:**
- `mcp_command` is materialised iff `axes.tool_surface == "mcp"`. Today that is `access_path == "mcp"`
  (`agent_trigger.py:1195-1203`).
- Claude's default posture reads `axes.approvals != "none"` instead of `if mcp_command` (`runner_commands.py:238-242`).
  These are the same, because `approvals` is `mcp_permission_tool` exactly when `tool_surface` is `mcp`, and a
  `tool_surface` of `mcp` without an `mcp_command` cannot reach the builder: `pinned_server_path` raising is a 409
  first (`agent_trigger.py:1197-1203`). `build_command`'s compatibility signature (D6) derives `axes` from
  `mcp_command`, so tests that pass only `mcp_command` keep their meaning.
- `posture_at_rest` reads `axes.approvals` (D3).
- `described_access_path` and the context renderer read `axes.plane`.

`resolve_access_path` and `MCP_INJECTABLE_RUNNERS` are deleted (D5). `harness_has_honoured_mcp` is unchanged. Its
permanent latch is F340, which belongs to slice 3.

**Why `tool_surface` is not an adapter member in this slice.** Every adapter injects today, and slice 3 turns axis 1
into a per-run detection (F340). An adapter-level `mcp_injectable` would be a boolean that is `True` everywhere now
and wrong in shape later. Slice 3 owns axis 1's resolution. This slice only gives it a name and a place.

## D5 — Which registries are deleted, and which are kept

| Registry | Fate | Reason |
|---|---|---|
| `SUPPORTED_RUNNERS` (`runner_commands.py:60`) | **deleted** | Its DEAD block (`:52-59`). The 501 gate at `agent_trigger.py:773-780` becomes `get_adapter(runner) is None`, and its message lists `ADAPTERS`. The branch is unreachable (`runner` is `Runner.cli`, `:764`), so the changed text is unobservable. |
| `_CATALOG_PROVIDER_BY_RUNNER`, `catalog_provider_for_runner` (`:110-119`) | **deleted** | `adapter.catalog_provider`. Callers: `agent_trigger.py:1412` and `build_command` (`:160`). **(re-verify in R2:** `the-permissions-pill…` D2 adds a caller in the agents list.) |
| `MCP_INJECTABLE_RUNNERS` (`launchability.py:230`) | **deleted** | D4. Its test, `test_launchability.py:537` (`"kimi"`), is deleted with it, as the DEAD block says (`:228-229`). |
| the `claude_proxy`/`native` arms: `build_command` `:179`, parser selection `agent_trigger.py:2451` | **deleted** | Unreachable, for the same reason. `test_runner_parsing.py:104-116` is deleted. |
| `worker.SUPPORTED_CLIS` (`:71`), `conversation_titles._SUPPORTED_CLIS` (`:68`) | **deleted** | `get_adapter(cli) is None` is the refusal. `test_title_generation.py:217` changes to assert `get_adapter("kimi") is None`. |
| `CLAUDE_FAMILY_RUNNERS` (created tonight in `runner_commands.py`) | **deleted** | `adapter.mcp_tool_prefix` / `host_tool_note`. **(re-verify in R2.)** |
| `RUNNER_CLI` (`launchability.py:33-43`) | **renamed `LEGACY_RUNNER_CLI`, kept whole** | `probe_agent` asks `get_adapter(runner)` first, and falls to this table only for a runner string with no adapter. Only a session-configured agent can carry one (`/session/sync`), and its DEAD block (`:21-30`) says `native` and `manual` are still live there. For `claude`/`codex` the adapter's verdict is byte-identical to today's (the `claude_proxy`/`copilot` auth branches never matched them). |
| the `copilot` row and its env-token auth branch (`:42`, `:116-126`) | **kept in this slice; slice 2 deletes them** | Deleting them here, with no Copilot adapter, would send a session-configured `runner: copilot` agent to the name fallback. That names a binary after the agent, which is the masking `RUNNER_UNBOUND` was created to end (`:45-51`). Slice 2's adapter shadows the row (the adapter is asked first), and slice 2 deletes it, together with `test_launchability.py:124-140`. Its auth rule is also wrong: appendix A §E (DOCUMENTED) says the env tokens *override* a stored login, and are not required. |
| `_display_model`'s legacy rows (`agents.py:558-564`) | **kept for non-adapter strings** | For `claude`/`codex` the value comes from `adapter.display_name`. The `claude_proxy`/`kimi`/`manual`/`opencode`/`codex_mcp` rows still render session-configured agents, and removing them would change their text. |
| `parse_opencode_line` (`runner_parsing.py:615`) | **kept** | `usage-accounting` requires OpenCode step normalisation (`openspec/specs/usage-accounting/spec.md:31,41`). It is a parser, not a registry. |
| `RUNNER_CONFIGS` (`src/agentweave/constants.py`) | **kept, untouched** | It is the CLI's table, read by `doctor`. F393 annotated it (`f228962`). The Hub never imports it. |

After this change, `grep -rnE '== "(claude|codex)"|in \("claude"' hub/hub --include=*.py` outside `runner_adapters/`
finds nothing (task 4.4).

## D6 — `build_command` moves to `runner_adapters`

`build_command(*, runner, cli, prompt, model, context_file, session_id, yolo, mcp_command, extra_flags,
control_overrides, restrict_spec_writes)` keeps its signature and moves from `runner_commands.py` to
`runner_adapters/__init__.py`. It does three things: look up the adapter (`UnsupportedRunnerError` if there is none),
take its **stream** transport for these flags (Codex: `exec`), and call `build_launch` with `axes` derived from
`mcp_command`. `runner_commands` keeps the two builders, the posture constants and `UnsupportedRunnerError`, so
`runner_adapters → runner_commands` is the only direction. R1 counted 11 test files that name both `build_command` and
`runner_commands` (`grep -l build_command hub/tests/*.py | xargs grep -l runner_commands`). Their import line changes,
and nothing else in them does.

**Two test seams are kept by name.** First, `agent_trigger` imports `build_command` by name from `runner_adapters` and
calls it as today. Five tests patch `hub.api.v1.agent_trigger.build_command` to capture its kwargs
(`test_agent_trigger.py:463`, `:505`, `:696`, `:830`, `:2960`, all on `claude`). Second, `probe_binary` calls
`shutil.which` and `os.path.isfile` through the module attribute (`import shutil`, never `from shutil import which`).
218 test sites patch `hub.launchability.shutil.which`, and that patches the attribute on the `shutil` module object
itself, so it keeps working from `runner_adapters/base.py`. A `from`-import would silently fall through to the real
PATH: green locally, where `claude` is installed, and red on CI.

**The trigger builds argv only for a stream transport.** Today `cmd` is built for every run, and on Codex app-server
it is passed along unused (`agent_trigger.py:1213-1229`, `:2304-2309`). After the change it is built only when
`transport.kind == "stream"`. Nobody reads the unused argv, and `build_command` has no side effect (`context_file.exists()`
is a read), so the difference cannot be observed. It matters for slice 2: an ACP-only adapter has no argv to build.

## D7 — `workspace_writes.py` is not changed

The module is pure and stdlib-only on purpose (`workspace_writes.py:1-26`), and it is on the path of every tool
call. So it must not import the adapter table. It keeps `CLAUDE_WRITE_TOOLS`, `CODEX_WRITE_TOOL`, `WRITE_TOOLS` and
`written_paths` exactly. The adapters *reference* those constants in `write_tool_kinds`. A conformance test asserts
three things:
1. The union of every adapter's `write_tool_kinds` equals `WRITE_TOOLS`.
2. No tool name appears in two adapters. `written_paths(tool, input)` dispatches on the tool name alone
   (`runner_events.py:176`), so a shared name would be ambiguous.
3. `written_paths` returns non-empty for a well-formed input of every declared kind.

Slice 2 adds Copilot's table to `workspace_writes.py` and its adapter together, or the test fails.

## D8 — One-shot calls go through the adapter

`worker.build_worker_command(cli=…)` and `conversation_titles.build_title_command(cli=…)` keep their names and
signatures. Tests and `test_worker_at_mention.py` call them. Each becomes `get_adapter(cli)` then `one_shot(purpose,
…)`, returning `None` when there is no adapter. `worker.parse_envelope` becomes `adapter.parse_one_shot`.
`run_worker`'s schema-file step (`worker.py:450-453`) reads `adapter.one_shot_takes_schema`.

`parse_claude_envelope` and `parse_codex_envelope` move into the adapter modules. `WorkerUsage`, `extract_json_object`
and `_int_or_none` move to `runner_adapters/one_shot.py`. `worker.py` re-exports all five, so its callers and
`test_worker.py:25-29` are unchanged. This is needed because `worker.py` imports the database (`:47-48`) and the
adapters must not (D1).

The argv stays byte-identical: `worker` spells `"claude"`/`"codex"` literally (`:142`, `:147`) and the titler uses
`cli` (`conversation_titles.py:87`, `:92`). Both are `adapter.binary`.

## D9 — The two executors become runner-generic

- `_execute_run` (stream): `PipeSession` if `transport.spawn_kind == "pipe"`, else `PtySession`
  (`agent_trigger.py:2345-2359`). `parse = transport.map_events` (`:2451`, `:2468-2470`). After exit, `transport.usage_from(…)`
  when `session_id` is known (`:2574-2587`).
- `_execute_codex_appserver_run` → `_execute_rpc_run(adapter, transport, …)`. The literal `runner="codex"` (`:3089`,
  `:3261`, `:3350`, `:3445`) becomes `adapter.name`. `_codex_posture` moves to `CodexAppServerTransport.posture_for`.
  `_CODEX_APPROVAL_LABELS` and `codex_approval_label` become `permission_card_label` and `refusal_label`.
  `_codex_decision_timeout` is renamed `_decision_timeout`, because it reads only `AW_DECISION_TIMEOUT` and is not
  Codex-specific (`:2955-2974`).
- The patch seam moves. 17 test call sites patch `hub.api.v1.agent_trigger.codex_run_turn`
  (`test_agent_trigger.py` 9, `test_a_turn_says_how_it_ended.py` 3, `test_failed_run_returns_input.py` 3,
  `test_agent_trigger_overrides.py` 1, `test_outside_write_record.py` 1). They patch `hub.codex_appserver.run_turn`
  instead, and `CodexAppServerTransport.run_turn` looks it up on the module at call time. A test that is missed fails
  loudly: `patch` raises `AttributeError` on the removed name. It cannot silently start a real `codex`.
  `test_codex_posture_ordering.py`, `test_permission_approver.py` and `test_agent_waiting_settings.py` import
  `_codex_posture`/`_codex_decision_timeout` and change their import.
- `run_liveness.active_app_server_runs` keeps its name. It is already transport-generic in use (`run_liveness.py:53`,
  `:113-118`), and renaming it would touch lifecycle code for no gain. Its comment says it holds every RPC run.

## D10 — Environment

`resolve_agent_env(runner, config)` (`launchability.py:145-196`) keeps its `env_vars` resolution, which is generic,
and ends with `adapter.guard_env(proc_env, env_vars)` when there is an adapter. The Claude guard is today's `:190-194`
moved unchanged. Codex's guard is the identity. The per-run keys (`AW_*`, `HUB_URL`) and the strip list
(`agent_trigger.py:1243-1304`) stay generic.

## D11 — F325 becomes a declared value

`CodexAppServerTransport.instruction_channel = None`. A test pins every transport's `instruction_channel` and checks
the argv agrees with it: the flag is present iff the value is not `None` and the context file exists. Fixing F325 is
then a change to one value plus the code behind it, in a change of its own. Slice 2's contract (exploration D1: a
custom agent file) is the `instruction_channel` of the ACP transport. Its value and its application are slice 2's to
define.

## D12 — The Codex MCP env allow-list is declared once

Today it is two literals with identical contents (`runner_commands.py:322-328`, `codex_appserver.py:973-979`). After
this change it is one constant, `CODEX_MCP_ENV_NAMES`, in `codex_appserver.py`. `_build_codex_command` and `run_turn`
both read it, and `CodexAdapter.mcp_env_names` points at it. The constant sits there rather than on the adapter
because `runner_adapters` imports `codex_appserver`, and the reverse import would be a cycle (D1). It is the same list,
so nothing changes. The omission of
`AW_QUESTION_TIMEOUT`, `AW_DECISION_TIMEOUT`, `AW_WORKSPACE_DIR` and `AW_PERMISSION_POSTURE` (appendix B §12) is not
fixed. It is listed in the open questions, because a declared list makes the gap visible in one line.

## D13 — Context window: declared, and pinned to the parsers

The parsers already decide the window, and they decide it per **transport**, not per runner:
- Claude reports its own window (`runner_parsing.py:11-17`).
- Codex `exec` looks the window up in the catalog (`runner_parsing.py:402`).
- Codex `app-server` reports its own `modelContextWindow` (`codex_appserver.py:303-311`).

That is why `context_window_source` is on the transport. Routing the lookup through the adapter would make
`runner_parsing` import `runner_adapters`, a cycle, for no behavioural gain. So the member is a declaration, and a
conformance test holds each transport to it:
- It feeds each transport's recorded usage lines (stream) or `thread/tokenUsage/updated` payloads (RPC) through its
  mapper.
- For `"reported"`, it asserts the sample's `limit_tokens` equals the payload's own window.
- For `"catalog"`, it asserts `limit_tokens` equals `model_context_window(catalog_provider, model)`, and that an
  unknown model is `unavailable`.

Slice 2's ACP transport declares `"reported"` (`usage_update.size`, VERIFIED-LOCAL), and the same test covers it.

## D14 — Launchability through the adapter

`probe_agent(name, config)` (`launchability.py:54-142`) keeps the `manual` and `RUNNER_UNBOUND` early returns and the
return shape. It then calls `get_adapter(runner).launchability(name, config)` when there is an adapter, and today's
legacy path over `LEGACY_RUNNER_CLI` otherwise. The shared binary check (`:91-99`, including the pinned `cli` override)
becomes `base.probe_binary(binary, cli_override, name)`, and both paths call it, so the two cannot drift.

## D15 — What each route returns when the function it calls raises

- `POST /agent/trigger`: `get_adapter` returns `None` and does not raise. The unchanged 501 (`agent_trigger.py:773`)
  answers. `build_launch` raising `UnsupportedRunnerError` still becomes 501 (`:1230-1233`). `resolve_access_axes` is
  pure over strings. `pinned_server_path` raising `OSError` is still the 409 at `:1199-1203`.
- `GET /agents/launchability`, `GET /runners/launchability`, `GET /runners/launchability-by-provider`: `launchability`
  must not raise, a contract member that the conformance test exercises with a missing binary and with a pinned
  non-file override. An adapter that raised would make these routes answer 500 where today they answer a verdict.
  That is why "must not raise" is part of the contract.
- The worker and the titler: `one_shot` returns argv and cannot raise on well-typed input. The worker's `OUTCOMES`
  (`worker.py:76-85`) are unchanged: no adapter is `unsupported_cli`.
- The RPC executor: `run_turn`'s allowed exceptions are exactly the tuple `agent_trigger.py:3244` catches. Anything
  else escapes, as it does today.

## D16 — Members reserved for later slices (contract only, not added here)

These are added by the slice that first reads them, so that no member exists without a caller:

| Member | Slice | Contract |
|---|---|---|
| `write_native_files(agent, home) -> None` | 2 (`ghcp-d2-native-files`) | At agent creation, write the runner's own files into a Hub-owned home: a custom agent file, MCP config, and hooks for slice 5. |
| `agent_home(agent) -> Optional[Path]` plus the env it sets (`COPILOT_HOME`) | 2 | A per-agent, Hub-owned configuration root. `None` for Claude and Codex. |
| `version_gate(initialize_result) -> Optional[str]` | 2 | A refusal reason when the harness is older than the supported minimum. |
| `models(live: Optional[Mapping]) -> Sequence[ModelDescriptor]` | 2 | Catalog models discovered at run time (Copilot's `availableModels`, Auto). |
| per-run `tool_surface` detection | 3 | Axis 1 resolved from evidence of *this* run (F340). It replaces D4's `hub_client`-only rule. |
| `shim_allowed(command) -> bool` | 3 | `_decide` auto-approves the Hub's own shim. |
| `spend_from(event) -> Optional[CreditSample]` | 4 (`ghcp-d3-credits`) | Credits and premium requests as information. Tokens stay the unit. |
| `compaction_percent` | 4 | The point where the harness compacts by itself (Claude ~95, `checkpoint_policy.py:24-28`; Copilot ~80, DOCUMENTED). Checkpoint thresholds are placed below it. |
| `quota_hold_from(event) -> Optional[AllowanceHold]` | 4 | A quota refusal becomes an allowance hold (`provider_allowance.py`). |
| `hooks` | 5 | Hub-owned hook definitions written by `write_native_files`. |

## Tests that can fail

- **Golden argv** (tasks 1.1, 1.2): about 100 `build_command` cases. For each runner, the cross product of
  `permission_mode` ∈ {none, acceptEdits, workspace, manual, bypassPermissions} × `mcp_command` ∈ {None, set} ×
  `yolo` × `restrict_spec_writes`, plus one-axis variations of `model`, `session_id`, `context_file` (present and
  missing), `extra_flags` and `effort`. They are captured from today's code into
  `hub/tests/fixtures/runner_adapters/argv_golden.json`, with the context path written as `<CTX>`. After the change,
  `get_adapter(r).transport(flags)` builds each case and it must be byte-equal. This fails today: there is no module.
- **Golden events** (task 1.3): the JSONL lines already inline in `test_runner_parsing.py` (live-shaped Claude
  `stream-json` and Codex `exec --json`) go into `claude_stream.jsonl` and `codex_exec.jsonl`. Today's selection
  (`parse_claude_line`, and `parse_codex_line(model=…)`) produces `stream_events_golden.json`, the sequence of
  `(kind, content, payload, usage, accounting, session_id)`. `transport.map_events` must reproduce it.
- **Golden one-shot** (task 1.3): worker and title argv for each CLI × model/no model × schema path.
- **Golden RPC wiring** (task 1.4): the keyword arguments `_execute_codex_appserver_run` passes to
  `codex_appserver.run_turn`, for each `permission_mode` and with/without `mcp_command`, with callables recorded by name.
  They are compared with what `CodexAppServerTransport.run_turn` passes.
- **Conformance** (task 1.5): D2's four-way set equality and order; D7's write-tool union and disjointness; D11's
  instruction channel against argv; D13's window source; `launchability` not raising; `ADAPTERS` instantiating (an
  ABC with a missing member fails here).
- **Axes** (task 1.6): the five rows of D4's table.
- **No literal** (task 4.4): the grep in D5, as a test over `hub/hub/**/*.py` excluding `runner_adapters/`,
  `migrations/`, `db/models.py` and `model_catalog.py`'s `CATALOG` keys.

## Round log

- **R1 (2026-09-27):** written. Read the exploration, its appendices A–C, the 2026-09-20 note, DECISIONS
  `ghcp-d1`..`d6`, F393's full entry, and F325's header. Read today's code:
  - `runner_commands.py` (whole), `launchability.py` (whole), `model_catalog.py:140-487`, `workspace_writes.py:1-140`.
  - `worker.py:60-160`, `:300-340`, `:430-470`; `conversation_titles.py:55-110`, `:240-275`; `codex_appserver.py:1-120`,
    `:185-300`, `:640-700`, `:880-1060`; `runner_parsing.py` (header, index, `:610-707`).
  - `agent_trigger.py:675-875`, `:1090-1462`, `:1741-1826`, `:2275-2614`, `:2920-3300`; `agents.py:225-275`, `:545-575`,
    `:690-720`.
  - `db/models.py:300-342`, `schemas/runners.py`, `api/v1/runners.py:95-135`, `db/engine.py:240-262`,
    `project_lifecycle.py:290-305`, `checkpoint_policy.py:1-60`.
  - The tests that pin the deleted registries (`test_runner_parsing.py:95-125`, `test_model_catalog.py:10-30`,
    `test_launchability.py:405-440`, `:537`), and the proposals and designs of the seven night changes named in the
    proposal's "Depends on" line.

  Found three facts the exploration does not state. The database constraint `ck_runners_cli` means slice 2 needs a
  migration (D2). Codex app-server's approvals already do not follow MCP (D4). And deleting the legacy `copilot` row
  before slice 2 would reintroduce the agent-named-binary masking (D5).

## Open questions for R2/R3

1. **Rebase onto the night.** Seven changes edit the sites here (proposal, "Depends on"). Re-derive every line marked
   *(re-verify in R2)* from the post-night tree: `posture_at_rest`'s final signature and home, `CLAUDE_FAMILY_RUNNERS`
   and the tool-prefix plumbing, the collaboration verdict's new location, the Codex catalog's cache read (does
   `CATALOG["codex"]` stay a key D2's test can read?), `on_decision`, and `workspace_verdict`.
2. **Is `hub_client` the only thing that moves axis 1 today?** R1 found `resolve_access_path`'s only caller at
   `agent_trigger.py:1107`, and the approved `request-agent-models…` design (`:130`) drops `hub_client` from copies.
   Confirm there is no second writer or reader.
3. **Claude with `hub_client: "cli"` reports `collaboration_ready: True`** (`agents.py:264-265`) although its axis 2 is
   `none`. It is pre-existing and not changed here, and it is F299's territory. Should `collaboration` read the axes in
   slice 3? Record it as a finding if R2 agrees.
4. **The Codex MCP env allow-list gap** (D12): file it as a finding, or leave it with slice 3, which decides what
   reaches the tool server?
5. **Is D6's move worth its churn?** About eleven test files change one import line. The alternative is keeping
   `runner_commands.build_command` with a function-local import of `runner_adapters`. The repo accepts that pattern
   (`agent_trigger.py:2962`), but it leaves the cycle in place. R1 chose the move.
6. **The golden fixture size.** About 100 argv cases of about 15 strings each is roughly 40 KB. Confirm it is small
   enough to commit, or cut the cross product.
7. **Ordering rule.** `GET /runners/launchability-by-provider` returns a dict keyed in `ADAPTERS` order. Task 1.5
   asserts the order the route returns. Check no UI test fixes a different order
   (`hub/ui/src/__tests__/support/modelCatalogFixture.ts`).
