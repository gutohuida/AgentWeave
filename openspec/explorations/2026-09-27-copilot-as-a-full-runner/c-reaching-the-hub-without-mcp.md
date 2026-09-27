# A GHCP runner on a machine that blocks MCP: the fallback channel

Research, read-only, 2026-09-27. Repo at `8627adf`. Copilot CLI installed: 1.0.88. Note that
`--no-auto-update` runs the **bundled 1.0.75**, as the probes under `%TEMP%\ghcp-probe` show
(`agentInfo.version` / `copilotVersion` = 1.0.75). That version predates the 1.0.88 fix that applies
managed settings in ACP mode.

Legend: **[M]** measured (by me, or read from an existing probe transcript on disk).
**[S]** read from source. **[D]** vendor docs. **[U]** unverified, needs a probe.

---

## 1. What exists today for a run that cannot take MCP

### The shipped change `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` (archived, all tasks [x])

- **The notice tells the truth [S].** `access_path_notice` (`hub/hub/launchability.py:402`) has two
  branches. The MCP branch names the tools. The non-MCP branch names `HUB_URL`, the route prefix
  `/api/v1/agent-actions`, and `Authorization: Bearer $AW_RUN_TOKEN`. It never interpolates the
  token's value (D4: the turn prompt is stored).
- **An HTTP rendering of the tool surface exists [S].** `_tool_surface_lines(access_path=...)`
  (`hub/hub/api/v1/agents.py:1504`) gives method, path and body fields for each operation.
- **Two rules that lived only in the adapter moved into the contract [S].**
  - `POST /jobs/{id}/archive` now refuses with `409` and a `permission_request_id` until the operator
    confirms (`agent_actions.py:~904`).
  - `wait_expires_at` is on the question response (`schemas/questions.py:92`). The wait is a
    documented poll-and-report protocol, closed by `POST /questions/wait-ended`.
- **Given versus told are split [S].**
  - `resolve_access_path(runner, hub_client)` (`launchability.py:233`) decides what a run is
    *given*: whether the MCP server is injected, and through that the posture. Only
    `hub_client: "cli"` or a runner outside `MCP_INJECTABLE_RUNNERS` moves it.
  - `described_access_path` decides what the run is *told*. It says MCP only on grounds: an operator
    `hub_client: "mcp"`, or `harness_has_honoured_mcp`, meaning any earlier run of this agent has
    `mcp_adapter_online_at`, stamped by the adapter's `POST /mcp-adapter-online` before it serves.
- `MCP_INJECTABLE_RUNNERS = {"claude","claude_proxy","native","codex"}` (`:230`). It is annotated
  DEAD for its non-injectable arm, because `RUNNER_CLIS = ("claude","codex")` and both are
  injectable.
- **`hub_client` [S]:**
  - It is read from `session.json` or `Agent.config` (`launchability.py:495`) and is a
    `ROSTER_CONFIG_KEYS` entry (`agents.py:651`).
  - It is documented in `src/agentweave/config.py:725` as *"uncomment if MCP is blocked by company
    policy"*.
  - No UI control sets it.
  - On `claude`, `cli` means no `--mcp-config`, no `--permission-prompt-tool`, and the posture falls
    to `acceptEdits`.

### What the findings say is broken (all Status: open, DEFERRED 2026-09-21, "reopen when GHCP")

- **F299 (A).** `claude` with MCP blocked by policy still receives `--permission-prompt-tool
  mcp__agentweave__approve_tool_call`, which nothing answers.
  - On 2.1.269 the harness prints `MCP server blocked by enterprise policy: agentweave`. The run
    dies with exit 1 at its first approval-needing call. Earlier builds instead made the model blame
    the operator's machine.
  - Every remedy moves containment, which is the operator's call.
- **F300 (fixed `612b9c9`).** The workspace approver `_decide` read a URL path as a filesystem path
  and denied `curl $HUB_URL/...`. It now recognises the run's own Hub.
- **F301 (A).** On the `cli` path a `claude` run made zero requests to the plane in 15 attempts:
  - Claude Code's own command analyser refuses `$AW_RUN_TOKEN` / `$env:AW_RUN_TOKEN` interpolation,
    `$()`, .NET calls and heredoc brace forms.
  - `acceptEdits` with no approver then auto-denies the rest.
  - The plane is "reachable", but not by the agent's own tools. The finding suggests an untested
    alternative: a program that reads `os.environ` itself.
- **F339 (B).** `acceptEdits` is in fact path-confined by Claude Code (2.1.269), so the reason 1b
  rejected it ("removes the path check") is false. The Hub still sees and records none of those
  refusals.
- **F340 (B).** Grounds are positive-only and permanent: one old `mcp_adapter_online_at` makes them
  true forever. Meanwhile the harness reports the server's state on every run and the Hub parses
  none of it:
  - `claude`'s `system/init.mcp_servers` shows `connected`, `failed`, or **absent** when
    policy-blocked.
  - The stderr policy sentence becomes a plain text event.
- **DECISIONS 2026-09-13 afternoon (OPEN):** F299/F301/F339/F340 are one question, with shapes
  (i) Hub-authored message plus today's behaviour, (ii) `acceptEdits` with no approver plus
  recording `permission_denials`, and (iii) 1b plus option (a)'s flag.
- **DECISIONS 2026-09-21 `f299-f301`:** won't build now; reopen with GHCP.
- **`openspec/explorations/2026-09-20-the-approval-transport-is-not-the-tool-surface.md`:**
  `resolve_access_path` is one boolean answering three questions: tool-surface delivery, approval
  transport, and plane access. It says the parked (i)/(ii)/(iii) question only exists because
  "MCP or nothing" was assumed.
- `spec-queue/research/2026-09-21.md` §2 argued the three co-vary for GHCP too. **That is true only
  where MCP is permitted.** On the operator's company PC they split (see §6).

---

## 2. The agent-facing HTTP surface

- **Every MCP tool goes through one helper [S].** `mcp_server._hub_request`
  (`hub/hub/mcp_server.py:164`) calls `urllib` → `$HUB_URL/api/v1/agent-actions{path}`, with
  `Authorization: Bearer <AW_RUN_TOKEN>` (`_bound_token`, `:70`).
- The module imports only the stdlib plus fastmcp. It is spawned as a standalone script and pinned at
  Hub start under `~/.agentweave/hub/tool-server/<digest>/` (F354).
- **Routes** (`hub/hub/api/v1/agent_actions.py`):
  - messages: `POST /messages`
  - tasks: `POST|GET /tasks`, `GET|PATCH /tasks/{id}`, `/tasks/{id}/transitions`,
    `/integrations`, `/integrations/retry`
  - checkpoints: `POST /checkpoint-notes`, `GET /checkpoints`, `/checkpoints/{id}`, `/recall/{id}`
  - questions: `POST /questions`, `/questions/batch`, `/questions/wait-ended`, `GET /questions/{id}`
  - agents: `POST /agents/request`
  - jobs: `POST /jobs`, `PATCH|DELETE /jobs/{id}`, `/jobs/{id}/archive`, `/jobs/{id}/run`
  - permissions: `POST /permission-decisions`, `/permission-requests`,
    `GET /permission-requests/{id}`, `/permission-requests/{id}/expire`
  - spec: `POST|GET /spec/evidence`, `/spec/evidence/{id}/decision`, `GET /spec/documents`,
    `/spec/documents/create`, `/spec/documents/rename`, `POST /spec/documents`
  - adapter: `POST /mcp-adapter-online`
- **Auth [S]** (`hub/hub/agent_auth.py`, 80 lines). `get_agent_actor`:
  - requires a bearer credential starting with `aw_run_`;
  - hashes it with SHA-256 and matches `Run.capability_token_hash` where `Run.status == "running"`;
  - checks the recorded `instance_id` against this Hub;
  - returns `AgentActor(project_id, agent, run_id)`.
  Identity is derived entirely server-side. No body field or header names the agent.
- **Injected env [S]** (`agent_trigger.py:1239-1291`): `AW_AGENT_IDENTITY`, `AW_RUN_TOKEN`,
  `AW_WORKSPACE_DIR`, `AW_QUESTION_TIMEOUT` (only when configured), and `HUB_URL` (explicit, or the
  observed port).
- **Can an agent call these with curl or `Invoke-RestMethod`?** Yes, protocol-wise. The credential is
  a bearer token and the "identity never from body/header" rule is not violated, because the header
  carries a credential that the server resolves to identity, exactly as the MCP adapter does.
  **What refuses it is the harness, not the Hub:**
  - Copilot's shell tool applies `url(...)` permission rules to URLs in shell commands [D]
    (`copilot help permissions`), so each request is a permission prompt, which in ACP reaches the
    Hub.
  - The model must interpolate the token into the command. That puts the credential into the
    tool-call record, which the Hub stores as an event (`rawInput` of every ACP `tool_call`), the very
    leak D4 was written to avoid, one layer down.
  - PowerShell quoting on Windows is fragile. F301's lesson is that the harness decides which shapes
    of command run, and the Copilot analyser's equivalent is **[U]**.
- **`--secret-env-vars` conflicts [D].** Copilot's flag *"stripped from shell and MCP server
  environments and redacted from output"*. Marking `AW_RUN_TOKEN` secret would hide it from the model
  and remove it from the shell as well, so there is no redact-only mode. See §4 for how a channel can
  avoid needing the token in the shell at all.

---

## 3. The CLI package

- **`src/agentweave/cli.py` has exactly five `cmd_*` [S]:** `status`, `doctor`, `stop`, `hub_start`,
  `reset`. No subcommand reaches the agent-actions plane.
- `src/agentweave/tool_surface.py` has zero importers.
- `constants.py`'s `copilot` profile (with `mcp_add_cmd`) is legacy and wired to nothing (F393).
- The old non-MCP adapter (`agentweave msg send`, `task create`, `question ask`, `agent request`)
  was deleted by `2026-08-03-single-runtime`, "because the CLI was reduced to instance management,
  not because a second adapter was judged wrong" (`agent-capability-plane/spec.md:7-11`).
- **An `agentweave tool <name> --json` subcommand** would be a sixth `cmd_*`:
  - `.claude/rules/cli.md` says to read `openspec/explorations/2026-08-02-product-direction.md`
    first.
  - It cuts against "the CLI does only what cannot be done from the app". It is arguably a fit,
    since an agent without MCP cannot do this from the app, but it re-creates the CLI-as-agent-adapter
    that was deliberately retired.
  - It is stdlib-compatible (`urllib`, the same as `_hub_request`).
  - Its practical defects:
    - it depends on `agentweave` being on the agent's PATH at the right version;
    - it would duplicate `ask_user`'s wait loop and `archive_job` handling that already live in
      `mcp_server.py`;
    - in this repo, running `agentweave` from the root is shadowed by `hub/`.
- **Better home: the Hub's own tool-server artefact [S].** `mcp_server.py` is already the one
  stdlib-only, standalone, version-pinned script that owns the adapter's semantics:
  - the `ask_user` batch, poll and wait-ended protocol;
  - `HubAPIError` / `HubUnreachableError` typing;
  - `_readable_detail`.

  Give it a second entry point, for example `python <pinned>/mcp_server.py --call <tool> --args
  @file.json`, or a sibling `aw_call.py` in the same pinned directory importing the same functions.
  A per-run shim `aw.cmd` / `aw` is put first on the run's PATH. Then:
  - both adapters share one implementation, so parity is structural rather than tested;
  - the CLI rule is untouched, because this is Hub-owned run tooling and not an `agentweave`
    subcommand;
  - the token is read by the program from its own environment and **never appears in command text**.
    That closes F301's interpolation class and the D4 leak-in-`rawInput` class at once.
- **Open [S/U]:** fastmcp is imported at module top (`mcp_server.py:19`, inside a try). A `--call`
  mode must not need it. Check that the import is guarded, or split the shared helpers into a
  fastmcp-free module the adapter imports (import restrictions are in `.claude/rules/`).

---

## 4. Channels that bypass MCP for a Copilot run

### (b) ACP itself: the Hub is the client. This is the foundation, not a fallback

Measured in `%TEMP%\ghcp-probe\acp_perm.jsonl` (1.0.75 bundled) **[M]**:

- `initialize` → `agentCapabilities.mcpCapabilities {http:true, sse:true}` and `loadSession:true`.
- `session/new` → session id, modes (agent / plan / autopilot), and a config option `allow_all`
  (on/off).
- A tool call arrives as `session/update` `tool_call`, with kind `edit`, `rawInput`, `locations` and a
  diff. The agent then sends **`session/request_permission`** with options `allow_once`,
  `allow_always` and `reject_once`. After the Hub picked reject, a `tool_call_update` came back as
  `failed` with `"The user rejected this tool call."`

Carried **without MCP**:

| Function | Via ACP |
|---|---|
| Permissions / approvals | **Yes.** Hub answers `session/request_permission` in-process with `_decide`-style policy (like `codex_appserver.decide_approval`), records via the same path as `/permission-decisions`, can park on an operator prompt. No `--permission-prompt-tool` analogue needed, so **F299's failure mode cannot occur** (no absent approver tool). |
| Observability (tool calls, diffs, thoughts, messages, plan) | **Yes**, typed `session/update`. |
| Cancel | **Yes**, `session/cancel`. |
| Turn boundaries / resume | Yes (`session/prompt` result, `session/load`). |
| Inbound delivery (messages, answers, task context to the agent) | **Yes**, the Hub composes the prompt; `session/prompt` on a live session. |
| Canonical context | Prompt text, or `AGENTS.md`/custom instructions **[U] whether a per-run instruction dir via `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` works in ACP.** |
| `ask_user` (operator question) | **Partly [U].** Copilot has its own built-in `ask_user` tool (`--no-ask-user` disables it). ACP elicitation (`elicitation/create`) went stable 2026-07-24. If Copilot routes its native `ask_user` to the ACP client as elicitation, the Hub can map it onto an AgentWeave question natively. Needs a probe advertising `clientCapabilities.elicitation`. |
| send_message, create/update_task, record_evidence, submit_spec_document, jobs, checkpoints, recall | **No.** These are model-initiated semantic calls; ACP has no client-provided tools. They need an agent→Hub channel. |

### (a) Copilot CLI hooks [D]

- **Events:** `sessionStart`, `sessionEnd`, `userPromptSubmitted`, `userPromptTransformed`,
  `preToolUse`, `postToolUse`, `postToolUseFailure`, `agentStop`, `subagentStart`, `subagentStop`,
  `errorOccurred`, `preCompact`, `notification`.
- **Types:**
  - `command`: `bash` / `powershell` / `exec`, plus `env` and `cwd`; receives JSON on stdin.
  - **`http`**: POSTs JSON to a `url`, with `headers` and **`allowedEnvVars`** that may be expanded
    inside the headers.

  So an `Authorization: Bearer $AW_RUN_TOKEN` header can be built from the run's own environment and
  POSTed straight to the Hub, with no script and no token in any command text.
- **Outputs:**
  - `preToolUse` can return `permissionDecision` allow / deny / ask, a reason, and `modifiedArgs`.
  - `postToolUse` can return `modifiedResult` and `additionalContext` (10 KB cap).
  - `sessionStart` and `notification` can inject `additionalContext`.
  - `agentStop` can block (force another turn; the CLI overrides after 8).
- **Defaults and loading:**
  - Default timeout is 30 s, and **timeouts fail open**. A crash or non-zero exit on a command hook
    denies.
  - Hooks load from policy dirs, `.github/hooks/*.json`, `~/.copilot/hooks`, settings `hooks`
    blocks, and **plugins** (`--plugin-dir` per run).
  - **Policy hooks** (`C:\ProgramData\GitHub\Copilot\policy.d\`) cannot be disabled.
  - `disableAllHooks` in repo or user settings disables non-policy hooks.
- **Unknowns [U]:**
  - whether hooks fire in `--acp` mode (the docs are silent);
  - whether an enterprise "customization lockdown" also blocks plugin hooks;
  - whether `COPILOT_ALLOW_ALL`-style folder trust is needed for repo hooks. It is not needed for
    `--plugin-dir`, which the docs describe as trusted configuration for `--add-dir`.

**What hooks can carry:**
- **Permissions**, as a second transport: `preToolUse` HTTP hook → Hub `_decide`. This is the only
  approval transport in `-p` mode. The fail-open timeout is dangerous for a wait on the operator, so
  set `timeoutSec` high, or never wait inside a hook.
- **Observability** (`pre`/`postToolUse`, `errorOccurred`, `agentStop`).
- **Context injection.**
- **A model-to-Hub call channel by interception.** The model runs a reserved shell command
  (e.g. `aw send_message ...`). A `preToolUse` HTTP hook forwards `toolArgs` to the Hub, which
  executes the action under the run's identity. A `postToolUse` hook replaces the result with the
  Hub's answer.

  It works without any executable on disk, but it is hacky and hard to test: the semantics hide in a
  rewrite, and `modifiedArgs` / `modifiedResult` shapes are **[U]**. It is not recommended as the
  primary channel.

### (c) Custom agents / skills teaching shell calls

- Copilot loads `.github/agents`, `.github/skills`, plugins and `AGENTS.md`.
- A skill or instruction that teaches `curl` / `Invoke-RestMethod` is just (§2) with better prompting.
  It inherits the token-in-command-text leak, URL permission prompts and quoting fragility.
- A skill that teaches **the shim** (`aw <tool> --json @file`) is the right use of this channel. It is
  documentation for §3's shim, not a channel of its own.
- `_tool_surface_lines` already has an HTTP rendering. It would get a third rendering for the shim.

### (c') Copilot CLI extensions [D, U]

Extensions are Node modules loaded from `.github/extensions`, `~/.copilot/extensions` or **a
plugin**. Over JSON-RPC they can register **native tools** (not MCP) and hooks.

- In principle this is an MCP-free tool surface with real tool schemas, the closest thing to parity.
- But they are **experimental** (`--experimental` is required), documented for interactive sessions
  only, and their behaviour under enterprise policy is undocumented.
- It is worth one probe. Don't build on it yet.

### (d) ACP client `fs` / `terminal` capabilities

- If the Hub advertises `fs.readTextFile` / `writeTextFile` and `terminal`, a conforming agent routes
  file I/O and command execution through the client.
- The probe advertised both as false. **Whether Copilot actually delegates to them is [U].**
- If it does, the Hub gains containment and execution (it runs the command itself, so it can enforce
  the workspace). It could also answer a **reserved command name** (`aw ...`) in-process, with no
  token in the child's environment at all.
- This is elegant but depends on vendor behaviour. Treat it as an upgrade path, not the base.

### Also relevant

- **Plugin-packaged MCP server [D, U].** Issue #4957 quotes the lockdown message: *"Skipping MCP
  server "<server>": blocked by enterprise customization lockdown (only plugin/managed MCP servers
  are permitted)"*.
  - Under that lockdown mode, the same `agentweave` server shipped inside a per-run `--plugin-dir`
    plugin may be permitted, keeping the MCP primary.
  - It will not pass a `deniedMcpServers` entry or registry-only matching on name or command.
  - Cheap to try first.
- **The enterprise may disable bypass-permissions [D].** #4957 quotes *"bypass-permissions mode
  DISABLED by enterprise policy"*. So `--allow-all-tools` / `--yolo` / `allow_all` may be refused on
  the company PC, and **every write and shell call will need an answer**. That makes ACP's
  `request_permission`, answered by the Hub, a necessity rather than a nicety. `-p` mode without
  allow-all would be undrivable.

---

## 5. How policy blocks MCP in Copilot CLI, and detection

- **Mechanisms [D]:**
  - The "MCP servers in Copilot" org/enterprise policy.
  - The registry-only allowlist (public preview). It matches local servers by registry server ID and
    is admittedly bypassable: *"Enforcement is based only on server name/ID matching, which can be
    bypassed by editing configuration files"*.
  - **`managed-settings.json` `allowedMcpServers` / `deniedMcpServers`** (recommended). Entries
    match by `serverName`, `serverCommand` (argv array) or `serverUrl`.
  - The "customization lockdown" mode (only plugin/managed servers).
- **Scope:**
  - These apply to stdio servers launched locally from any config source.
  - **Since 1.0.88 they also apply to `--acp` sessions**; before that, ACP ran with *"no managed MCP,
    permission, or plugin policy"* (research 2026-09-22). So servers passed in ACP `session/new
    mcpServers` must be assumed blocked on the company PC.
  - **Pin a minimum of 1.0.88 and never pass `--no-auto-update` blindly**, which on this machine runs
    the bundled 1.0.75.
  - Known 1.0.88 bug #4957: policy resolved before auth → fail-closed → workspace MCP blocked
    spuriously for about 3 s.
- **Detection signals:**
  1. **`-p --output-format json` [M]** (`%TEMP%\ghcp-probe\out.jsonl`) emits
     `session.mcp_server_status_changed {serverName, status: pending|connected|...}` and
     `session.mcp_servers_loaded {servers:[{name,status,source,transport}]}`.
     - Both are `ephemeral: true`. They are **not** written to `~/.copilot/session-state/*/events.jsonl`
       [M].
     - The status string for a policy-blocked server (`blocked`? `failed`? absent, as on `claude`?)
       is **[U]**. Treat any status other than `connected`, and absence, as "no grounds".
  2. **ACP mode:** these events are not in `session/update` [M: absent from `acp_perm.jsonl`]. Copilot
     may emit them as a `_`-prefixed extension notification **[U]**.
  3. **Harness-agnostic, already built [S]:** the adapter's `POST /mcp-adapter-online` announce,
     which happens before it serves.
     - With ACP the Hub controls when the first `session/prompt` is sent, so it can do `session/new`
       with `mcpServers:[agentweave]`, then wait for the announce for this `run_id` (bounded, e.g.
       10–15 s).
     - On announce, describe MCP. On timeout, switch the run's described channel to the fallback and
       compose the first prompt accordingly.
     - This is a **per-run, latest-test** signal. It resolves F340's "positive-only, permanent"
       defect for this runner.
  4. **`--log-dir <run-private dir>` [D/M]:** the process log carries the `Skipping MCP server ...
     blocked by ...` sentence. It is diagnostic text only (a vendor string), to be shown, not keyed
     on.
- **Recommendation:** key on (3), corroborate with (1) or (2) where present, and show (4) verbatim.
  Record the result per run (`harness_mcp_status`), not a permanent latch.

---

## 6. Recommended design (ranked)

The key reframe: **for a Copilot runner driven over ACP, approval transport is the Hub itself, not
MCP.** So of `resolve_access_path`'s three coupled questions, only *plane access* depends on MCP.
Split it:

- **approval:** `acp`
- **surface delivery:** prompt + skill
- **plane access:** `mcp | shim`

This retires the parked (i)/(ii)/(iii) question for this runner. It does not retire it for `claude`.

1. **ACP runner as the base (required regardless).**
   - Hub-answered `request_permission`, observability, cancel, prompt-composed inbound, and possibly
     `ask_user` via elicitation.
   - Works whether or not MCP is allowed. It also handles an enterprise that disables allow-all.
2. **Plane access: MCP first, shim fallback, chosen per run by the announce.**
   - Always offer `agentweave` in `session/new`, and optionally also as a `--plugin-dir` plugin to
     survive "customization lockdown".
   - If no announce arrives in time, the run is told the **shim** form: `aw <tool> --json
     @args.json`. The shim is the pinned tool-server script in call mode, sharing `_hub_request` and
     the `ask_user` protocol, and reading `AW_RUN_TOKEN` from its own environment.
   - The Hub auto-allows `shell(aw:*)` in its own `request_permission` policy, so the operator is not
     asked for plane calls.
   - Trade-offs:
     - Pro: one implementation, token never in command text or stored events, no URL prompts,
       deterministic, testable without a model.
     - Con: needs Python available to the run (it already is for the MCP server). Model tool-schema
       fidelity is lower than MCP; mitigated by the skill plus the rendered surface.
3. **Raw HTTP (`curl` / `Invoke-RestMethod`)**: keep only as the documented last resort
   (today's notice). It leaks the token into `rawInput`, meets URL prompts, and is fragile on
   PowerShell.
4. **Hooks**: add only for `-p` mode, or if hooks prove to fire under ACP.
   - Use: a `preToolUse` HTTP hook as a secondary approval transport, telemetry, context injection.
   - Don't use them as the model→Hub call channel.
5. **Extensions / ACP terminal delegation**: probe, then consider them as upgrades. Extensions would
   give native-tool parity; terminal delegation would give Hub-executed commands with no token in
   the child. Both are vendor-experimental.

### Findings this would close or change

- **F299:** closed for GHCP by construction, because no MCP-named approver exists. It stays open for
  `claude`, where the same split (a `PermissionRequest` / `PreToolUse` hook as approval transport,
  per the 2026-09-20 exploration) is the analogue.
- **F301:** closed for GHCP. The shim removes both walls: no `$TOKEN` in command text, and the Hub
  answers the permission itself. The `claude` half is unchanged unless the shim is also offered on
  `claude`'s `cli` path (the analyser's handling of `aw ...` is [U]).
- **F340:** closed for GHCP by a per-run announce-with-timeout signal, recorded per run, not a
  permanent latch. The same mechanism would fix `claude` if it is adopted there.
- **F339:** not closed. It is a `claude` posture fact. It becomes moot for GHCP, where the Hub is the
  checker, and the docs row is still owed (B11).
- **F300:** stays fixed. `_decide` recognising the run's own Hub is reused if raw HTTP remains a
  fallback.

### Probes owed before R1 leans on anything

1. `copilot --acp` (≥ 1.0.88) with `session/new mcpServers:[agentweave stdio]`, under a
   managed-settings `deniedMcpServers` entry. Check: does `session/new` error, is there any ACP
   notification, and does the announce arrive?
2. The same with the server in a `--plugin-dir` plugin.
3. The `-p` json `mcp_servers_loaded` status string for a denied server.
4. Do hooks fire in ACP? Does an HTTP hook's `allowedEnvVars` header expansion work?
5. Advertise `elicitation` and check whether the native `ask_user` arrives as `elicitation/create`.
6. Advertise `terminal` / `fs` and check whether Copilot delegates.
7. Can Copilot's shell run the shim on Windows without triggering its own static refusals (F301's
   Claude-side class)?
8. Does the company's enterprise policy disable allow-all or ACP itself? Ask the operator to run
   `/env` on the company PC.

Sources: [hooks reference](https://docs.github.com/en/copilot/reference/hooks-configuration),
[MCP allowlist enforcement](https://docs.github.com/en/copilot/reference/mcp-allowlist-enforcement),
[enterprise allowlist](https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/administer-copilot/manage-mcp-usage/configure-enterprise-allowlist),
[configure MCP access](https://docs.github.com/en/copilot/how-tos/administer-copilot/configure-mcp-server-access),
[ACP server](https://docs.github.com/en/copilot/reference/copilot-cli-reference/acp-server),
[CLI extensions](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-cli-extensions),
[issue #4957](https://github.com/github/copilot-cli/issues/4957),
[ACP elicitation RFD](https://agentclientprotocol.com/rfds/elicitation).
