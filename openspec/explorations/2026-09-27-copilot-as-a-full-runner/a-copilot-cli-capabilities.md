# GitHub Copilot CLI (`copilot`) — capability map for an AgentWeave runner

Researched 2026-09-27. Machine: Windows 11, npm global install. Account: `gutohuida`, **Copilot Free**
(`access_type_sku: free_limited_copilot`, `premium_interactions.entitlement: 0`), no org or enterprise.

Tags: **VERIFIED-LOCAL** means observed on this machine (command output, probe transcript, or the shipped JS
source at `%LOCALAPPDATA%\copilot\pkg\win32-x64\1.0.88\app.js`). **DOCUMENTED** means taken from docs.github.com or
the shipped `changelog.json`. **INFERRED** means reasoned from code or strings, not exercised.

**Version note (important):** the npm package was upgraded to **1.0.88** at 18:03 today (the npm dir timestamps say so). Every
probe below ran on 1.0.88 (`agentInfo.version: "1.0.88"`). The earlier probe's "1.0.75" came from a run whose log reads
`Starting Copilot CLI: 1.0.75`. Several gaps it saw (no ACP usage, no raw events) are fixed in 1.0.78 and 1.0.81
(see A). A per-feature table of the changelog is in section K.

Evidence files (scratch): `...\scratchpad\ghcp\` holds `help*.txt`, `ref.md` (the full command reference as markdown),
`docs\*.md` (37 docs pages fetched through `docs.github.com/api/article/body`), `acp1.log` to `acp5.log` (ACP transcripts)
and `acp_probe.py`. Probe workspace: `%TEMP%\ghcp-probe2` (hooklog.py, mcpsrv.py, addmcp.json, hooks.log, mcp.log).
Custom-home probe: `%TEMP%\ghcp-probe2-home`.

**Model-calling prompts run: 2 of the 3 allowed.** Both were over ACP and both used `--model claude-haiku-4.5`,
which the account silently overrode to Auto (see H).
1. acp4.log: hooks, `--additional-mcp-config` stdio server, raw events, usage. Cost 1 premium request,
   `totalNanoAiu 275,856,000`, Auto chose `mai-code-1.1-flash`.
2. acp5.log: the ask_user test.

Every other probe was a slash command over ACP (`/env`, `/mcp list`, `/usage`, `/context`, `/session info`,
`/model`). These run with no model call.

---

## A. ACP surface

### Methods — VERIFIED-LOCAL (acp1–acp5, app.js dispatch table)
| Method | Status |
|---|---|
| `initialize` | Returns `agentCapabilities {loadSession:true, mcpCapabilities{http:true, sse:true}, promptCapabilities{image:true, audio:false, embeddedContext:true}, sessionCapabilities{close:{}, list:{}}}`, `agentInfo.version "1.0.88"` and `authMethods[copilot-login]` with a `_meta.terminal-auth` command that points at `copilot.exe login`. |
| `session/new` | Returns `modes` (agent/plan/autopilot) and `configOptions` (`mode`, `allow_all`). **No `models` and no `model` option on this account** (see H). Throws `authRequired` when there is no credential. |
| `session/load` | Works. It replays history as `user_message_chunk` / `agent_message_chunk` and returns `modes` + `configOptions`. |
| `session/list` | Works. It returns every session in `COPILOT_HOME` with `{sessionId, cwd, title, updatedAt}`, so the Hub should filter by cwd. |
| `session/close` | Works (added in 1.0.78). |
| `session/set_mode` | Works, but **modeId must be the full URI** `https://agentclientprotocol.com/protocol/session-modes#plan` (also `#agent`, `#autopilot`). Plain `plan` gives error -32602. It emits `current_mode_update` and `config_option_update`. |
| `session/set_config_option` | `mode` takes the URI value. `allow_all` takes `on`/`off` and works. `model` is accepted even though it is not advertised: it returned configOptions and took no visible effect on the Free plan. The code also handles `agent`, which appears only when custom agents exist, and a reasoning option when the model supports it. |
| `session/set_model` (unstable) | Returns `{}`. **It also returned `{}` for `bogus-model`**, so the Hub cannot rely on it to validate a model. |
| `session/cancel` (notification) | Implemented. It aborts the session and cancels attached shells. |
| `session/resume`, `session/fork` | **Method not found** (the ACP SDK knows them; Copilot does not implement them). |
| `session/request_permission` (agent→client) | Options offered: `allow_once`, `allow_always`, `reject_once` (no `reject_always`). A `cancelled` outcome counts as reject. |
| `fs/read_text_file`, `fs/write_text_file`, `terminal/*`, `elicitation/create` | **Never called.** app.js defines the client wrappers but has zero call sites. Copilot uses its own file and shell tools even when the client advertises `fs`/`terminal` (VERIFIED by code). |

### Session updates Copilot emits — VERIFIED-LOCAL
`agent_message_chunk`, `agent_thought_chunk` (reasoning and `assistant.intent`), `tool_call` and `tool_call_update`
(including partial output streaming; `kind` is `execute` for shell and `other` for MCP; MCP tool titles look like
`hubprobe-ping`), `plan` (built from the internal SQL todo table), `available_commands_update`, `current_mode_update`,
`config_option_update`, `session_info_update` (title), and **`usage_update {used, size}`** (context tokens, on each
`session.usage_info`). `session.error`, `session.warning` and `session.info` become `agent_message_chunk` text
prefixed `Error:`, `Warning:` or `Info:`, so an MCP policy block shows up in the text stream.

### Usage — VERIFIED-LOCAL
`session/prompt` returns
`{stopReason:"end_turn", usage:{inputTokens, outputTokens, totalTokens, thoughtTokens, cachedReadTokens, cachedWriteTokens}}`.
**The usage figures are cumulative for the session, not per prompt.** `/usage` and `/context` responses returned the same
totals. Premium requests and AI units are not in the ACP result; they are available only through raw events.

### Raw event passthrough (a Copilot extension of ACP; the key finding for a Hub) — VERIFIED-LOCAL
In `initialize`, send
`clientCapabilities._meta["github.com/copilot"].events = ["session.usage_checkpoint","assistant.usage","hook.start","hook.end","permission.requested","permission.completed","session.mcp_servers_loaded","session.mcp_server_status_changed","session.tools_updated","session.warning","session.error","session.idle","subagent.started",...]`.

Copilot then sends JSON-RPC **notifications with method `github.com/copilot/sessionEvent`** and params
`{sessionId, type, timestamp, data, agentId?}`. Limits: at most 128 types, 32 KB per payload (larger payloads arrive as
`dataOmitted:"too-large"`), and at most 256 in flight (the excess is dropped with a log warning). Observed:
- `assistant.usage` carries `{model, inputTokens, outputTokens, cacheReadTokens, reasoningTokens, cost, duration, isAuto, initiator}` per call.
- `session.usage_checkpoint` carries `{totalNanoAiu, totalPremiumRequests, modelCacheState}`.
- `session.mcp_servers_loaded` carries each server's `status` and `source`.
- `hook.start` and `hook.end` carry input and output.
- `permission.requested` carries `{permissionRequest{kind:"mcp", serverName, toolName, args, readOnly}, resolvedByHook}`.

Events emitted before the session is registered (MCP startup inside `session/new`) are **not** forwarded; the first
`session.mcp_servers_loaded` arrived on the first prompt.

### Model and effort under ACP — VERIFIED-LOCAL + DOCUMENTED
- Spawn flags: `--model`, `--reasoning-effort`/`--effort`, `--available-tools` and `--excluded-tools` apply to every session
  (DOCUMENTED, acp-server page; changelog 1.0.60). `session/new` cannot carry them.
- On this Free account, `--model claude-haiku-4.5` was **ignored**. Events show `session.model_change newModel "auto"` and
  `auto_mode_resolved availableModels ["mai-code-1.1-flash"]`.
- `/model` over ACP returns "The model-picker dialog is only available in the interactive CLI."

### Spawn flags that do and do not apply to ACP sessions
| Flag | Result under ACP | Evidence |
|---|---|---|
| `--disable-builtin-mcps` | Honored: github-mcp-server shows as `(disabled, builtin)` | VERIFIED-LOCAL |
| `--no-custom-instructions` | **Ignored**: AGENTS.md still listed | VERIFIED-LOCAL, `/env` |
| `--allow-tool` / `--deny-tool` / `--allow-all-*` / `--allow-url` | Applied | INFERRED from `computeSessionPermissionConfig` (uses `options.rules`); changelog 0.0.400 |
| `--no-ask-user`, `--agent` | Not passed to the ACP session factory | INFERRED |
| ask_user in general | Moot: **ask_user is not available under ACP**. The model replied "The `ask_user` tool isn't available here" and asked in plain text | VERIFIED-LOCAL, acp5 |
| `--fleet` | "Not supported in ACP server mode" | DOCUMENTED |
| `--additional-mcp-config` | Honored | VERIFIED-LOCAL |

### MCP servers passed in `session/new` — VERIFIED-LOCAL
- Only `http`/`sse` entries are accepted. **stdio entries are rejected silently**: the log line is
  `Rejecting non-http/sse MCP server "<name>" from client`, and the server is missing from `/mcp list`. Changelog 1.0.25 had
  claimed stdio support; in 1.0.88 it is gone.
- A name that collides with an agent-configured server is rejected.
- A dead http server shows `hubprobe (failed): ... transport failure` in `/mcp list`. `session/new` still succeeds.
- To inject a **stdio** server under ACP, use `--additional-mcp-config @file.json` at spawn. This was verified: env reached
  the server and the tool was callable as `hubprobe-ping`.
- ACP loads user `mcp-config.json` + plugins + `--additional-mcp-config`. Workspace `.mcp.json` and `.github/mcp.json`
  load only when the folder is trusted.
- Copilot's MCP client first sends **`server/discover`** (MCP 2026-07-28 draft), then `initialize` with
  `protocolVersion "2025-11-25"`. The Hub's MCP server must tolerate the unknown method.
- Slash commands work over ACP as prompt text (`/compact`, `/context`, `/usage`, `/env`, `/mcp list`, `/session info`,
  `/plan`, `/review`, `/research`, `/autopilot`, `/allow-all`, `/add-dir`, `/cwd`, `/share`, `/remote`, and skills as
  `/<name>`). Informational ones make no model call.

## B. Permissions

- **Kinds** (DOCUMENTED, command reference, "Tool permission patterns"): `shell(cmd[:*])`, `write(path)`, `read(path)`,
  `url(domain|url)`, `memory`, `<mcp-server>(tool)`. Internal request kinds (VERIFIED, app.js): `commands`, `write`,
  `read`, `mcp`, `memory`, `custom-tool`, `path`, `url`, `hook`, `extension-*`, `factory`.
- **Deny wins** over allow, even over `--allow-all` and saved approvals (DOCUMENTED).
- `--available-tools` / `--excluded-tools` control what the model sees; allow and deny control prompting. When both filters
  are given, available wins.
- **Auto-allowed:** reads (ACP sets `approveAllReadPermissionRequests: true`) and read-only shell commands (command
  safety analysis). VERIFIED-LOCAL: `echo hookprobe .` via **powershell** ran with no permission request, while an
  MCP tool call did produce a `permission.requested`.
- **Always prompted:** writes, non-read-only shell, URLs, MCP tools ("All MCP tool invocations require explicit
  permission", DOCUMENTED), and paths outside the cwd.
- **Path verification:** access is limited to the cwd, its subtree, and the temp dir. `--add-dir` (repeatable; it also loads that
  dir's `.github/skills` and `.github/agents` as trusted), `--allow-all-paths`, `--disallow-temp-dir`. UNC paths are blocked.
- **`allow_always` over ACP means approve for this session only (in memory)** (VERIFIED, app.js `bke`/`HH`). It is not persisted.
  Persisted "this location" approvals live in `$COPILOT_HOME/permissions-config.json`; URL approvals persist in
  `settings.json` `allowedUrls` (DOCUMENTED).
- The `allow_all` config option and `--allow-all`/`--yolo` can be disabled by managed
  `permissions.disableBypassPermissionsMode: "disable"`. Managed `permissions.deny/ask/allow` rules
  (`Shell()/Read()/Edit()/Domain()`) cannot be satisfied by hooks or allow-all when they are `ask` (DOCUMENTED).
- **Sandbox (MXC):** experimental. On Windows it uses ProcessContainer/BaseContainer. The per-run switches are
  `--sandbox` and `--no-sandbox`, which are experimental-only (`--experimental`); the persistent setting is
  `sandbox.enabled` in settings.json. Managed settings can force it (`enabled`, `failIfUnavailable`,
  `allowBypass:false`, `sandboxMcpServers`). On Windows `deniedPaths` is unsupported and a policy that sets it fails. Remote
  MCP is never sandboxed. Tool telemetry showed `sandboxApplied:false` (DOCUMENTED, `copilot help sandbox`; VERIFIED
  telemetry field).

## C. Hooks (a Hub channel that works independently of MCP)

- **Events** (DOCUMENTED, hooks-reference): `sessionStart`, `sessionEnd`, `userPromptSubmitted`,
  `userPromptTransformed`, `preToolUse`, `postToolUse`, `postToolUseFailure`, `permissionRequest`, `agentStop`,
  `subagentStart`, `subagentStop`, `preCompact`, `errorOccurred`, `notification`. PascalCase names (`PreToolUse`, ...) select
  VS Code/Claude-format payloads with snake_case fields and Claude matcher semantics (`Bash`, `Edit|Write`).
- **Locations**, all merged:
  - Policy: `C:\ProgramData\GitHub\Copilot\policy.d\*.json` and `HKLM\Software\Policies\GitHub\Copilot`. These cannot be disabled.
  - Repo: `.github/hooks/*.json`, plus inline `hooks` in `.github/copilot/settings(.local).json` **and `.claude/settings(.local).json`**.
  - User: `$COPILOT_HOME/hooks/*.json` and inline `hooks` in `$COPILOT_HOME/settings.json`.
  - Plugins: `hooks.json`.
- **Trust gating:** repo hooks load only in a **trusted folder**. VERIFIED: `.github/hooks` in the untrusted probe dir showed
  "No hooks loaded". `COPILOT_ALLOW_ALL=true` (exactly `true`) trusts the cwd. Under `-p`,
  `GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS=true` opts in. **User-level hooks in `$COPILOT_HOME/hooks` load everywhere**
  (VERIFIED). That is the Hub's clean channel: point `COPILOT_HOME` at a Hub-owned dir.
- **Format:** `{"version":1,"hooks":{"preToolUse":[{"type":"command","exec":"py","args":[...],"timeoutSec":20,"matcher":"regex"}]}}`.
  Entry fields are `bash`, `powershell`, `command`, `exec`+`args` (no shell), `cwd`, `env`, `timeoutSec` (default 30).
  `type:"http"` POSTs the payload; it requires https, or `http://localhost` when `COPILOT_HOOK_ALLOW_LOCALHOST=1`, and
  `preToolUse`/`permissionRequest` HTTP hooks must be https.
- **Fire under ACP and -p: VERIFIED-LOCAL (acp4, hooks.log).**
  - Order on the first prompt: userPromptSubmitted → userPromptTransformed → **sessionStart (fires on the first prompt, not
    on `session/new`)** → preToolUse → permissionRequest → postToolUse → … → agentStop → **sessionEnd (reason
    `complete`, fires at the end of every prompt turn under ACP and -p)**.
  - Hook env had **no** `COPILOT_SESSION_ID`, so read `sessionId` from stdin. Since 1.0.81, hook inputs also carry `traceparent`.
- **Payloads observed on stdin:**
  - preToolUse: `{sessionId, timestamp, cwd, toolName:"hubprobe-ping", toolArgs:{...}}`
  - permissionRequest: `{hookName, sessionId, timestamp, cwd, toolName:"hubprobe/ping", toolInput:{...}, permissionSuggestions:[]}`.
    Note the MCP name form is `server/tool` here and `server-tool` elsewhere.
  - postToolUse: adds `toolResult{textResultForLlm, resultType, sessionLog, toolTelemetry}`.
  - agentStop: includes `transcriptPath` (`$COPILOT_HOME/session-state/<id>/events.jsonl`).
- **Decisions:**
  - preToolUse: `{permissionDecision:"allow"|"deny"|"ask", permissionDecisionReason, modifiedArgs}`. Exit 2 or a crash
    means **deny (fail-closed)**; a **timeout means fail-open**.
  - permissionRequest: `{behavior:"allow"|"deny", message, interrupt}`. **VERIFIED:** `behavior:"allow"` short-circuited the
    flow and **no `session/request_permission` reached the ACP client** (`resolvedByHook:true`). The exceptions are
    sandbox-bypass requests (allow cannot pre-approve) and the `read` and `hook` kinds (hooks skipped).
  - agentStop/subagentStop: `{decision:"block", reason}` forces another turn; there is a runaway cap of 8.
  - postToolUse: `{modifiedResult, additionalContext}`.
  - notification: `additionalContext` gets injected as a user message.
  - userPromptSubmitted: `modifiedPrompt` is honored only by SDK hooks; command hook output is dropped.
- **Kill switches:** `disableAllHooks` (settings, or per file) and the managed `allowManagedHooksOnly` (changelog 1.0.85).
  Policy hooks survive both.

## D. MCP config and policy

- **Config:**
  - User `$COPILOT_HOME/mcp-config.json`.
  - Workspace `.mcp.json` / `.github/mcp.json`, walked up to the git root, trusted folders only, **not loaded under -p** unless
    `GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP=true`. `.vscode/mcp.json` is **not read**; migrate `servers` to `mcpServers`.
  - Plugins.
  - `--additional-mcp-config` (JSON or `@file`, highest priority).
  - ACP `session/new` (http/sse only).
- **Transports:** `local`/`stdio` (`command`, `args`, `tools` required; `env` with `${VAR}` expansion; `cwd`; `timeout`),
  `http` (alias `streamable-http`), `sse`, with `headers`, OAuth (including `client_credentials`), and `oidc`.
- **Permission patterns** use the raw server name: `MyMCP(tool)`. The model-facing tool name is `server-tool`, sanitized to
  `[A-Za-z0-9_-]` and 64 chars max.
- **Policies that block MCP:**
  1. **"MCP servers in Copilot"** org/enterprise policy. It is carried per user as `is_mcp_enabled` in the cached
     `copilot_internal/user` response (`%LOCALAPPDATA%\copilot\copilot-user-cache.json`; `true` here, VERIFIED). The CLI
     passes `mcp3PEnabled` into its native `NativeMcpConfigFilter`. When it is off, **all third-party (non-built-in) servers are
     blocked, local stdio and localhost http alike** ("Block third-party MCP servers when the Copilot MCP policy does not
     allow them", changelog 0.0.416; "enforced for all users", 1.0.11). Only first-party built-ins (github-mcp-server) survive.
     DOCUMENTED + INFERRED. The docs say the policy is **disabled by default** for org-managed seats.
  2. **Enterprise allowlist via `managed-settings.json`** (`allowedMcpServers`/`deniedMcpServers`, matched by
     `serverCommand` exact argv, `serverUrl` with wildcards, or `serverName`). Sources: server-fetched, or MDM at
     `HKLM\SOFTWARE\Policies\GitHubCopilot` or `%ProgramFiles%\GitHubCopilot\managed-settings.json`. Rules:
     - An unset list allows everything; `[]` blocks all non-default servers.
     - A malformed list blocks all.
     - Unresolved `${VAR}` in a command or URL blocks the server.
     - Fetch failure keeps the previous policy.
     - Built-ins are exempt.
     - Since 1.0.88 this applies to ACP sessions too.
     A Hub stdio server launched with Hub-specific args would need an exact `serverCommand` entry.
  3. **Registry policy** ("Restrict MCP access to registry servers", CLI ≥1.0.11). Name-based, and **fail-closed** if the
     evaluate endpoint is unreachable.
- **Reporting:** the filter produces a timeline warning (`mcpFormatFilteredServersWarning`, which reaches ACP as a
  `Warning:` message chunk). Blocked-by-enterprise text reads `MCP server "X" was blocked by your enterprise "Y"`. The raw events
  `session.mcp_servers_loaded` / `mcp_server_status_changed` carry per-server status (VERIFIED for connected and failed; the
  filtered-server shape is INFERRED from the host snapshot fields `filteredServers`, `disabledServers`, `mcp3pEnabled`).
  `/mcp list` over ACP is the cheapest check.
- **Hooks as a fallback when MCP is blocked:** hooks are not governed by the MCP policies. Only `disableAllHooks`,
  `allowManagedHooksOnly` and folder trust govern them. `$COPILOT_HOME/hooks` needs no trust. So a Hub can observe every tool call
  and approve or deny it through hooks, and post context through `postToolUse.additionalContext` or `notification`, even with MCP
  off. Hooks cannot add model-callable tools; custom tools require MCP or extensions.

## E. Customization and auth

- **Custom agents:**
  - Locations: `.github/agents/` and **`.claude/agents/`** (walk up to the git root), `$COPILOT_HOME/agents/`, plugins,
    and `--add-dir` roots.
  - Files are `*.agent.md` or `*.md`. Frontmatter: `description`, `tools`, `model`/`models`/`modelPolicy`, `reasoningEffort`,
    `mcp-servers`, `infer`, `include-custom-instructions`, and a `sidekick:` block.
  - Selection: `--agent`, or the ACP `agent` config option when agents exist.
  - Built-ins: `explore`, `task`, `general-purpose`, `code-review`, `security-review`, `research`, `rubber-duck`.
- **Skills:** `SKILL.md` in `.github/skills`, `.agents/skills`, `.claude/skills`, `$COPILOT_HOME/skills`, `~/.agents/skills`,
  plugins, `COPILOT_SKILLS_DIRS`, and `skillDirectories`. Frontmatter: `name`, `description`, `allowed-tools`,
  `user-invocable`, `disable-model-invocation`. `.claude/commands/*.md` are also read. They are exposed as `/<skill>` commands
  over ACP. `copilot skill list --json` works.
- **Custom instructions:** all of these merge: **`CLAUDE.md`**, `GEMINI.md`, `AGENTS.md` (git root + cwd),
  `.github/copilot-instructions.md`, `.github/instructions/**/*.instructions.md`,
  `$HOME/.copilot/copilot-instructions.md` and `instructions/`, and `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`. `@path` imports are
  supported. They load even in untrusted folders (VERIFIED, AGENTS.md appeared). `--no-custom-instructions` works in -p and
  interactive runs but **not under ACP** (VERIFIED).
- **Implication for the AgentWeave repo:** Copilot would load `CLAUDE.md`, `.claude/skills`, `.claude/agents` and
  `.claude/settings.json` hooks.
- **Plugins:** `copilot plugin install|list|...`, marketplaces `github/copilot-plugins` and `github/awesome-copilot`,
  `--plugin-dir`. A plugin bundles skills, agents, hooks, MCP and LSP.
- **COPILOT_HOME isolation — VERIFIED-LOCAL:**
  - With `COPILOT_HOME=%TEMP%\ghcp-probe2-home` (empty), `session/new` succeeded and a real prompt ran (acp4), so **auth
    survived**. The token lives in the Windows Credential Manager (`LegacyGeneric:target=https://github.com:gutohuida.copilot-cli`).
    `config.json` holds only `lastLoggedInUser`/`loggedInUsers` and no token.
  - The custom home got its own `session-state`, `session-store.db` and `logs`, and loaded `$COPILOT_HOME/hooks`.
  - `~/.agents/skills` did **not** load under the custom home.
  - The cache dir (`%LOCALAPPDATA%\copilot`, pkg/auto-update/user cache) is **not** moved by `COPILOT_HOME`; use
    `COPILOT_CACHE_HOME` for that.
- **Token precedence:** `COPILOT_GITHUB_TOKEN` > `GH_TOKEN` > `GITHUB_TOKEN` > keychain > `gh` CLI token. Environment tokens
  silently override the stored login. Fine-grained PAT with "Copilot Requests" works; classic `ghp_` does not
  (DOCUMENTED, `copilot login --help`). **Hub caution:** do not leak a `GH_TOKEN` into the runner env unintentionally.

## F. Sessions and context

- **Storage:** `$COPILOT_HOME/session-state/<uuid>/` holds `events.jsonl`, `session.db`, `workspace.yaml`, `checkpoints/`, `files/`
  and `research/`. `session-store.db` is SQLite for cross-session index and search (VERIFIED dir listing).
  `events.jsonl` is the same event stream as `-p --output-format json` (VERIFIED types: `session.start`,
  `session.model_change`, `session.auto_mode_resolved`, `session.usage_checkpoint`, `session.shutdown{totalPremiumRequests,
  totalNanoAiu, tokenDetails, codeChanges, modelMetrics}`).
- **Resume:**
  - `--resume[=id|prefix|name]`, `--continue` (the most recent session in the cwd), and `--session-id <uuid>`, which is exact and
    creates the session if the UUID is new.
  - Under ACP use `session/load`.
  - `-n/--name` names a session.
  - `COPILOT_ENABLE_INTERRUPTED_SESSION_RESTORE=1` enables crash restore.
- **Compaction:** automatic at about 80% of the window, with a block at about 95%. `/compact [focus]` works manually (also over ACP).
  Each compaction writes a checkpoint (`/session checkpoints`). The `preCompact` hook fires. Tool output over 20 KiB is spilled to a
  file (`COPILOT_LARGE_OUTPUT_THRESHOLD_BYTES`) (DOCUMENTED).
- **Context:** `usage_update` reported `size` 128000 (mai-code-1.1-flash) and 272000 (a different auto pick). `--context
  long_context` only affects tiered-pricing models. `/context` over ACP gives a text breakdown (VERIFIED).
- **Limits:** `--max-ai-credits N` (minimum 30; a soft cap checked after each response; subagents and compaction count against it).
  `/limits` (DOCUMENTED, `help limits`). The reference page says it "resets per user message", which conflicts with `help limits`,
  which says the cap is session-wide.
- **Share:** `--share[=path]` (markdown) and `--share-gist`, both -p only.
- **Usage file:** `--usage-output-file` is **accepted by 1.0.88** (the parser takes it; it has per-agent metrics since 1.0.81).
  It was rejected on 1.0.75.

## G. Tools and modes

- **Tools** (DOCUMENTED, command reference):
  - Shell: `bash`/`powershell` + `list_`/`read_`/`stop_`/`write_` variants.
  - Files: `view`, `create`, `edit`, `apply_patch`.
  - Search: `grep`/`rg`, `glob`.
  - Web: `web_fetch` (SSRF-guarded; localhost only with `COPILOT_WEB_FETCH_ALLOW_LOCALHOST=1`), `web_search`.
  - Other: `ask_user`, `skill`, `task`, `list_agents`, `read_agent`, `write_agent`, `update_todo` (SQL todo table → ACP `plan`),
    `memory`/`store_memory`/`read_memories`, `task_complete` (autopilot).
  - Tool search (deferred loading) kicks in above about 30 tools.
- **On Windows the shell tool is `powershell`** (VERIFIED: `toolName:"powershell"`). It prefers pwsh 7 and falls back to
  Windows PowerShell 5.1 (pwsh is absent here). Flags come from `powershellFlags` (default `-NoProfile -NoLogo`).
- **Subagents:** the `task` tool. Built-in agents run on their own default models. With Auto, subagents inherit the resolved
  model. Depth defaults to 6. **Concurrency is plan-based: Free is 2**, Pro 4, and so on. Sidekick agents are also available.
- **Modes:**
  - `--mode interactive|plan|autopilot`, `--plan`, `--autopilot`; `--plan --mode autopilot` gives plan-then-autopilot.
    `--max-autopilot-continues` (help says default 5; the reference page says unlimited).
  - Autopilot under ACP is described as "enables allow-all and runs until task completion".
  - Plan mode blocks project edits at enforcement level.
  - `--no-ask-user` removes the ask_user tool. It is **absent under ACP anyway** (VERIFIED).

## H. Models

- **Listing:** there is no CLI command. Sources:
  - `/model` needs a TTY.
  - The ACP `configOptions` `model` entry appears only when selectable models exist; absent here.
  - The raw event `session.auto_mode_resolved.availableModels`.
  - `copilot help config` prints a static list: claude-sonnet-5, claude-opus-5, claude-haiku-4.5, gpt-5.5, gpt-5.4,
    gpt-5.3-codex, gemini-3.x-flash, grok-4.5, kimi-k3, mai-code-1.1-flash, among others.
- **Copilot Free is Auto-only** (DOCUMENTED, billing page: "access to models through auto model selection only"). VERIFIED:
  `--model claude-haiku-4.5` became `auto` both in the earlier -p run (Auto happened to choose haiku then) and in acp4
  (Auto chose mai-code-1.1-flash).
- **Auto:** `--model auto`, with `--auto-tier efficiency|balance|intelligence|fast`. Paid plans get 10% off.
- **Reasoning effort:** `none|minimal|low|medium|high|xhigh|max` (help). ACP docs list low through max.
- **Repo allowlist:** `.github/allowed_models.txt`.
- **BYOK:** `COPILOT_PROVIDER_BASE_URL/TYPE(openai|azure|anthropic)/API_KEY/_COMMAND/BEARER_TOKEN/WIRE_API/HEADERS` +
  `COPILOT_MODEL`, or `providers.json` / `COPILOT_PROVIDERS_CONFIG`. Needs no GitHub login and works under ACP.
- **Offline:** `COPILOT_OFFLINE=true` requires BYOK.

## I. Usage and billing

- AI credits: 1 credit is $0.01, and `nanoAiu`/1e9 = AIU. Plans (DOCUMENTED): Pro 1,500 per month, Pro+ 7,000, Max 20,000.
  Free has "an allowance" and Auto only.
- The legacy premium-request view is still emitted: `totalPremiumRequests` was 1 for acp4 and 0.33 for the haiku -p run.
- The user cache shows the Free quotas: chat 200 per month (96.6% left), `premium_interactions` 0.
- **Per-call:** `assistant.usage.cost` is the multiplier. **Per-session:** `session.usage_checkpoint` / `session.shutdown`.
- **OTel:** activated by `COPILOT_OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, or `COPILOT_OTEL_FILE_EXPORTER_PATH` (JSONL
  file exporter). An http:// endpoint other than localhost is silently disabled.
  - Spans: `invoke_agent` → `chat <model>` / `execute_tool <tool>` / `plan`.
  - Span attributes: `gen_ai.usage.input_tokens/output_tokens/cache_read.input_tokens/cache_creation.input_tokens`,
    `github.copilot.cost`, **`github.copilot.nano_aiu`** (read it on the root span only), `github.copilot.turn_count`,
    `gen_ai.conversation.id`.
  - Metrics: `gen_ai.client.token.usage`, `gen_ai.client.operation.duration`, `github.copilot.tool.call.count`, and others.
  - Span events: `github.copilot.hook.*`, `session.compaction_*`, `session.shutdown{total_premium_requests}`.
  - Content capture: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`.

## J. Special features (no Claude Code or Codex equivalent)

| Feature | Hub use? |
|---|---|
| Raw event passthrough over ACP (`github.com/copilot/sessionEvent`) | **Yes, high value.** Gives billing, usage, hook, permission and MCP status in one stream. |
| `permissionRequest` hook + `$COPILOT_HOME/hooks` | **Yes.** Headless approval without ACP round-trips, and it works when MCP is blocked. |
| `--additional-mcp-config` | **Yes.** It is the only way to inject a stdio MCP server under ACP. |
| `/delegate` → Copilot cloud agent (branch + draft PR) | Not usable: runs remotely, needs policy, and needs a TTY/interactive session. |
| `--remote` / `--connect` / remote control from github.com and mobile | Marginal. Interactive only; conflicts with Hub ownership of execution. |
| `copilot app` (desktop app) | No. |
| Built-in github-mcp-server (issues, PRs, actions tools), toolsets via `--add-github-mcp-toolset` | Optional. Disable with `--disable-builtin-mcps` for hermetic runs. |
| `/fleet` / `--fleet` parallel subagents | -p only, not ACP. Low value for the Hub. |
| `/research`, `/review`, `/security-review`, `/rubber-duck` (built-in agents) | Usable as ACP slash prompts. |
| Sidekick agents, memory (`--enable-memory`), `/chronicle`, `/every` and `/after` scheduling, LSP, extensions (`extension.mjs`), voice, `/computer` | Not needed. Extensions could add tools without MCP (INFERRED), but it is experimental. |
| Managed settings / policy hooks / sandbox floor | Enterprise constraints the Hub must detect, not features. |
| `/share`, `--share-gist` | Transcript export; optional. |

## K. Windows specifics

- **Shim:** `%APPDATA%\npm\copilot(.cmd)` runs `node npm-loader.js`, which runs
  `spawnSync(@github/copilot-win32-x64/copilot.exe, argv, {stdio:"inherit"})` (VERIFIED source). The result is two processes.
  **The Hub should spawn `copilot.exe` directly** at `%APPDATA%\npm\node_modules\@github\copilot\node_modules\@github\copilot-win32-x64\copilot.exe`
  (151 MB SEA). `authMethods._meta.terminal-auth.command` reports this exact path. Killing only the node shim may orphan
  copilot.exe (INFERRED).
- **Package cache:** copilot.exe runs a JS package extracted or downloaded to `%LOCALAPPDATA%\copilot\pkg\win32-x64\<ver>\`
  (present: 1.0.75, dated today 17:57; 1.0.83, dated Sep 13; 1.0.88). The loader (`sea-loader.js`) picks between the bundled
  version and newer cached ones. `--no-auto-update`, `--prefer-version <v>` (hidden) or `COPILOT_AUTO_UPDATE=false` pins it to the
  bundled version (VERIFIED code; DOCUMENTED env help).
- **The 1.0.75/1.0.83 mismatch** is best explained as the shim/binary version and the executed cache package differing before
  today's npm upgrade (INFERRED). Always read `initialize.agentInfo.version`.
- **Auto-update:** npm installs only notify about new versions (`autoUpdate` docs). Standalone binaries download in the
  background, and the update applies at the next launch. Auto-update is disabled when CI env vars are set. Settings:
  `autoUpdatesChannel`, plus the env vars above.
- **Shell:** the shell tool is `powershell` (pwsh 7 if present, else 5.1); flags come from `powershellFlags`;
  `--no-eager-powershell-resolution` is also available.
- **Credentials:** Windows Credential Manager, `copilot-cli` service.
- **Paths:** matching is case-insensitive, and UNC paths are blocked.

### Changelog anchors for runner design (DOCUMENTED, `changelog.json`)
| Version | Change |
|---|---|
| 1.0.25 | ACP client MCP servers (stdio claimed; now http/sse only in 1.0.88) |
| 1.0.39 | ACP `/compact /context /usage /env` and allow_all toggle |
| 1.0.40 | ACP plan updates, agent option, and skills as commands |
| 1.0.60 | Tool-filter and effort flags apply to ACP |
| 1.0.78 | ACP usage in prompt result + `usage_update`; `session/close` |
| 1.0.81 | Raw event subscriptions, subagent IDs, title and plan updates; per-agent usage in `--usage-output-file`; hooks get `traceparent` |
| 1.0.85 | `allowManagedHooksOnly` also blocks extension callbacks |
| 1.0.88 | Managed settings (MCP, permission, plugin policy) now apply to `--acp` sessions |

**Recommendation:** make ≥1.0.81 the minimum supported version.
