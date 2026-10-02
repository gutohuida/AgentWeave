# GitHub Copilot CLI as a full runner

**Date:** 2026-09-27 · **Status:** exploration, nothing built · **Master at writing:** `8627adf`
**Asked by the operator:** *"I want to take full advantage of ghcp … the focus should still be the MCP
server but it's not necessary to work. I want a full implementation. Mapping everything that we have
today, the functionalities that we use with claude code and codex to be used with ghcp as well. Also
want to know if ghcp has something special that is different."* Size chosen: **L** (a runner seam
first, then Copilot on it).

**The fire test** is the operator's work PC: Copilot is available there and MCP servers are
restricted by company policy. A Copilot agent there must still reach the Hub.

Evidence appendices (in this directory):
- **A.** `a-copilot-cli-capabilities.md` covers the Copilot CLI. It is based on 37 docs pages, the shipped `app.js` and `changelog.json`, and five ACP probes. Each claim is tagged VERIFIED-LOCAL, DOCUMENTED or INFERRED.
- **B.** `b-agentweave-run-inventory.md` lists everything a Claude or Codex run gets today, with `file:line` references.
- **C.** `c-reaching-the-hub-without-mcp.md` covers the fallback channel and detection, and which findings they close.

## Read this first: what the evidence is and is not

- **Versions.** Everything was measured on **Copilot CLI 1.0.88**, npm-installed on this machine.
  - One early probe ran **1.0.75**. The CLI's loader picks between a bundled package and newer cached ones, and `--no-auto-update` pins the bundled one.
  - Several ACP features exist only from **1.0.78 / 1.0.81**. Managed policy applies to ACP only from **1.0.88**.
  - The Hub must read `initialize.agentInfo.version` and refuse anything older than its supported minimum.
- **The account here is Copilot Free.** Free gets **Auto model selection only**: `--model claude-haiku-4.5` was silently replaced by `auto`. Free also caps concurrent subagents at 2 and has a small monthly allowance.
  - Nothing about model pinning, per-model cost or paid-plan limits was exercisable here.
  - The work PC is presumably Copilot Business, which will behave differently. See "Probes to run on the work PC".
- **No company policy was exercised.** The MCP-policy behaviour below is DOCUMENTED plus code-read (appendix A §D), not measured.
- Three probe prompts were run in total, each costing Free allowance. The rest used slash commands over ACP, which make no model call.

**Corrections found by slice 2's R1 (`a-copilot-agent-runs-over-acp`, same evening, measured on 1.0.88):**
- `--no-auto-update` runs 1.0.88 here, not 1.0.75.
- `~/.agents/skills` *does* load under a custom `COPILOT_HOME`.
- Copilot's MCP tool-call timeout defaults to **30 s**, which would cut every `ask_user` short. The Hub sets 660000 ms in the MCP config.
- The D1 probe held: a file in `$COPILOT_HOME/agents` makes `session/new` offer an `agent` option, and `set_config_option` selects it.

## The 09-20 question, answered

`2026-09-20-the-approval-transport-is-not-the-tool-surface.md` said the first design question for
Copilot is *"what are its values on the three axes"*. `resolve_access_path` conflates those axes
today because, for Claude and Codex, they co-vary.

| axis | Copilot's value | co-varies with MCP? |
|---|---|---|
| **1. tool surface**: can the Hub hand the agent its tools? | MCP via `--additional-mcp-config @file` at spawn (stdio; verified). **Falls back to a Hub-shipped shim** when MCP is blocked. | yes |
| **2. approvals**: can the Hub approve the agent's tool calls? | **Yes, always, over ACP `session/request_permission`**, which is part of the Hub↔CLI protocol and not an MCP tool. A `permissionRequest` hook in a Hub-owned `$COPILOT_HOME` is a second route (verified under ACP). | **no** |
| **3. plane access**: how does the agent call send_message, update_task and the rest? | MCP tools, or the HTTP plane through the shim | yes |

**Copilot is the runner on which axis 2 comes apart from axes 1 and 3.** So `resolve_access_path`
has to split before Copilot can be correct. With MCP blocked, Copilot still gets the `workspace`
posture, answered by `_decide`. That is exactly what F299 says a blocked Claude run cannot get.

## The shape

```
                    ┌──────────────────────────────── Hub ─────────────────────────────────┐
                    │ trigger_agent_directly → RunnerAdapter["copilot"]                     │
                    │   ├─ writes $COPILOT_HOME/<agent>/ (hooks/, mcp.json, agents/…)       │
                    │   ├─ spawns copilot.exe --acp  (NOT the npm shim)                     │
                    │   │    --no-auto-update --disable-builtin-mcps                        │
                    │   │    --additional-mcp-config @mcp.json   --model/--effort …         │
                    │   ├─ ACP client ─ initialize(+ raw event subscription)                │
                    │   │              session/new | session/load(provider_session_id)      │
                    │   │              session/prompt(context + turn notices + message)     │
                    │   │  ◀─ session/update: text · thought · tool_call(+diff) · plan ·    │
                    │   │                     usage_update · session_info                   │
                    │   │  ◀─ github.com/copilot/sessionEvent: assistant.usage · AIU ·      │
                    │   │                     mcp status · permission.* · hook.* · warnings │
                    │   │  ◀─ session/request_permission ──▶ _decide / operator card        │
                    │   └─ session/cancel → kill copilot.exe tree                           │
                    └──────────────────────────────────────────────────────────────────────┘
                               ▲ MCP (stdio, agentweave server)   ▲ fallback: shim → HTTP
                               │ /api/v1/agent-actions/*          │ same routes, same run token
                     copilot.exe (model, tools, subagents) ───────┘
```

Why ACP and not `-p --output-format json`: `-p` cannot ask anybody. Tools must be pre-allowed
(`--allow-all-tools` is "required for non-interactive mode"). That makes a runner which "cannot
collaborate unless yolo", the same reason `codex exec` stopped being Codex's default. ACP is
Copilot's equivalent of `codex app-server`, and `codex_appserver.py` is the model to follow.
`-p` stays useful for **one-shot calls** (`worker.py` probes and checkpoints,
`conversation_titles.py`).

## Parity map: everything a Claude or Codex run gets, and its Copilot counterpart

Key: ✅ verified on this machine · 📄 documented only · ❓ unknown or needs a probe · ⚠ gap or decision.
The inventory rows come from appendix B, and their evidence is there.

### Launch, lifecycle, transport

| Function (today) | Claude | Codex | **Copilot** |
|---|---|---|---|
| Transport | PTY `PtySession` | app-server JSON-RPC (default) / `exec` pipe | **ACP JSON-RPC over stdio** ✅. Spawn `copilot.exe` directly: the npm shim is `node` running a second process, and killing the shim may orphan the exe. |
| Prompt delivery | `-p` | JSON-RPC turn | `session/prompt` with text and embedded resources ✅ |
| Resume a conversation | `--resume <id>` | `thread/resume` | `session/load <id>` ✅; it replays history as chunks, which the Hub must not re-render as new output. `--session-id <uuid>` lets the Hub *choose* the id up front (`-p`) ✅. `session/resume` and `session/fork` are not implemented ✅. |
| Stop / interrupt | kill the process tree | `turn/interrupt` | `session/cancel` (also cancels its shells) ✅, then kill `copilot.exe` |
| Per-run env and credential | `AW_RUN_TOKEN`, `HUB_URL`, … | an explicit `env_vars` allow-list | Passed to the stdio MCP server through `--additional-mcp-config` `env` ✅. **Do not leak `GH_TOKEN`/`GITHUB_TOKEN`/`COPILOT_GITHUB_TOKEN`**: they silently override the operator's Copilot login 📄. |
| Config isolation | explicit flags | `CODEX_HOME` | **A Hub-owned `COPILOT_HOME` per agent** ✅. Auth survives because the token lives in Windows Credential Manager. It gives its own session store and logs, and `~/.agents/skills` is not loaded. The cache dir does not move (`COPILOT_CACHE_HOME`). |
| Launchability / auth check | binary + login | binary + login | A branch already exists (dead) in `launchability.py:116`. It checks the env tokens only and should instead be `initialize` → `authMethods`/`authRequired` plus a version check ⚠ |
| Version pinning | none | none | **Needed.** Require ≥ 1.0.81 (raw events, usage) and ideally ≥ 1.0.88 (policy under ACP). Read `agentInfo.version`; spawn with `--no-auto-update` ⚠ |
| Liveness, reconciliation, divergence, scheduler, inbound queue | runner-agnostic | same | Unchanged. They reach a runner only through `trigger_agent_directly` |
| One-shot calls (`worker.py`, `conversation_titles.py`) | `claude -p` | `codex exec` | `copilot -p --output-format json` ✅ (the `result` line carries `sessionId`, `premiumRequests`) |

### Instructions and context

| Function | Claude | Codex | **Copilot** |
|---|---|---|---|
| Rendered agent context (`.agentweave/context/<agent>.md`) | `--append-system-prompt-file` | `-c model_instructions_file=` | ⚠ **Decision D1.** No system-prompt flag. Options: (a) a **custom agent** `$COPILOT_HOME/agents/<agent>.agent.md` whose body is the context and whose frontmatter carries `tools`, `model`, `reasoningEffort` and `mcp-servers`, selected through the ACP `agent` config option 📄 (`--agent` is not passed to ACP sessions, INFERRED); (b) `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` → a Hub dir 📄; (c) an embedded resource on every prompt ✅ |
| Turn notices (access path, snapshot, spec turn) | prepended to the prompt | same | same (prompt text) ✅ |
| Project instructions | via the context | via the context | via the context, **plus Copilot loads the repo's own `CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`, `.claude/skills`, `.claude/agents` and `.claude/settings.json` hooks by itself** ✅. `--no-custom-instructions` is **ignored under ACP** ✅. ⚠ **Decision D2** |
| `@path` expansion neutralised | yes (Claude expands `@`) | n/a | Copilot also supports `@path` imports in instructions 📄. Whether the prompt expands `@` is ❓ |
| Charter | in the context | in the context | in the context, or a native custom agent (D1a) |

### Tools the Hub gives the agent (the capability plane)

| Function | Claude | Codex | **Copilot** |
|---|---|---|---|
| The ~30 `agentweave` MCP tools (messaging, tasks, questions, checkpoints, jobs/loops/flows, specs, evidence) | `--mcp-config` + `--allowedTools mcp__agentweave__*` | `-c mcp_servers.agentweave.*` | `--additional-mcp-config @file` (stdio) ✅. In ACP `session/new`, **stdio servers are silently rejected**; only http/sse are accepted there ✅. Model-facing names are `agentweave-<tool>` (sanitised, max 64 chars), and permission patterns use `agentweave(<tool>)` ✅ |
| Tool names told to the agent (`a-claude-run-is-told-its-agentweave-tools-by-their-full-names`) | `mcp__agentweave__x` | per-runner | `agentweave-x` ⚠. Tonight's change makes the surface per-runner, and Copilot adds a third spelling |
| MCP handshake | — | — | Copilot's client sends **`server/discover` before `initialize`**. The Hub's server must tolerate an unknown method ❓ (fastmcp behaviour unmeasured) |
| MCP adapter online (`POST /mcp-adapter-online`) | yes | yes | yes. It becomes **the per-run detection signal** for the fallback (see the fire test) |
| When MCP is unavailable | notice says curl (F301: blocked in practice) | same | **Shim**: a call mode of the Hub's pinned, stdlib-only tool-server script (`aw <tool> --json @file`), which reads `AW_RUN_TOKEN` from env and never takes it in argv. The Hub auto-approves `shell(aw …)` in `_decide`. Appendix C ranks the options |
| `ask_user` (operator in the loop) | MCP tool, blocking poll | same | **Copilot's own `ask_user` does not exist under ACP** ✅. The model asks in plain text instead. So the Hub's `ask_user` (MCP or shim) is the only question channel. This fits the no-backstop rule: an agent that does not call it has ended its turn |

### Permissions and posture

| Posture | Claude | Codex app-server | **Copilot (ACP)** |
|---|---|---|---|
| `workspace` (Hub answers; `_decide`) | `--permission-prompt-tool mcp__agentweave__approve_tool_call` | `decide_approval` on JSON-RPC requests | `session/request_permission` → `_decide`, with **no MCP dependency** ✅. Reads and read-only shell commands are auto-allowed by Copilot and never reach us ✅. Writes, non-read-only shell, URLs, MCP tools and out-of-cwd paths always ask 📄 |
| `manual` / Ask me (operator card) | the same tool routes to a card | `ASK_OPERATOR` | `request_permission` held open while a card is answered. The options are `allow_once`, `allow_always` (**this session only, in memory** ✅) and `reject_once` |
| `acceptEdits` | native | n/a | Emulate in `_decide` (allow `write` inside the workspace), or `--allow-tool=write` ⚠ |
| full access / yolo | `--dangerously-skip-permissions` | bypass flag | ACP config option `allow_all: on` ✅. **A company can disable it** (`permissions.disableBypassPermissionsMode`) 📄, and the Hub must then show it cannot grant it |
| read-only / plan turns (spec turns' `--disallowedTools`) | tool deny-list | sandbox read-only | `--excluded-tools` / `--deny-tool` at spawn, or ACP **plan mode** (`session/set_mode` with the **full URI** `…session-modes#plan`), which blocks project edits ✅ |
| Shell judge / path judge (`workspace_writes.py` write-tool tables) | Claude tool names | Codex item kinds | Copilot kinds: `commands`, `write`, `read`, `mcp`, `url`, `memory`, `path`, … ✅. The shell tool on Windows is **`powershell`** (pwsh 7 if present, else 5.1) ✅. The shell judge must read PowerShell ⚠ |
| Recording (`/permission-decisions`, outside-write record, ask-me cards) | shared | shared | shared. Raw events add `permission.requested/completed` with `resolvedByHook` ✅ |
| OS sandbox | n/a | Codex sandbox | Copilot MXC sandbox, experimental. Per run: `--experimental --sandbox`; on Windows it uses ProcessContainer. A company may force it 📄 |

### Stream, UI, usage, models

| Function | Claude | Codex | **Copilot** |
|---|---|---|---|
| Normalised events (`runner_events.py`, closed set) | `parse_claude_line` | `map_item_to_events` | a new ACP mapper: `agent_message_chunk`→text, `agent_thought_chunk`→thinking, `tool_call`/`tool_call_update` (with `diff` content and streamed output)→tool events, `plan`→todo/plan, `session_info_update`→title ✅. `Error:`/`Warning:`/`Info:` arrive as *message text* ✅, so the mapper must classify them |
| Context meter (`context_readings.py`) | reported | catalog | **`usage_update {used, size}`** notifications ✅ |
| Token usage (`usage_accounting.py`) | parsed | rollout files | per call: raw event `assistant.usage {model, inputTokens, outputTokens, cacheReadTokens, reasoningTokens, cost, isAuto}` ✅. The ACP prompt result's `usage` is **cumulative per session**, so it must be differenced ✅ |
| Spend unit | tokens / $ | tokens | ⚠ **Decision D3.** Copilot bills in **AI credits** (`nanoAiu`, 1 credit = $0.01) and legacy **premium requests**. Both come from `session.usage_checkpoint`. The allowance and budget must learn a second unit, or convert |
| Rate-limit / quota holds (`provider_allowance.py`) | only the Claude parser produces holds | none | Copilot quota exhaustion must synthesise a hold, or the queue will hammer an exhausted plan ❓ (error shape not yet seen) |
| Models (`model_catalog.py`) | hand list | reads `~/.codex/models_cache.json` | **No listing command.** Sources: the static list in `copilot help config`, `session.auto_mode_resolved.availableModels` (live, per session), and the ACP `model` config option when the plan allows choice ✅. `session/set_model` accepts a bogus name ✅, so the Hub validates |
| Reasoning effort | per-model control | per-model control | `--effort none…max` at spawn; ACP reasoning option when the model supports it 📄 |
| Compaction and checkpoints | Hub assumes Claude auto-compacts at ~95% | — | Copilot auto-compacts at **~80%** and blocks at ~95% 📄. It fires a `preCompact` hook and `session.compaction_*` events. Checkpoint policy thresholds must be per-runner ⚠ |
| UI (`RunnerCli`, `CLI_OPTIONS`, `Icon.tsx`) | — | — | A third literal, an icon, Auto in the model picker, and a spend unit in credits |

### Specs that name Claude or Codex and need a Copilot counterpart
`runner-registry` (3 requirements: the closed `{claude, codex}` set is a MUST reject),
`agent-run-sandboxing` (Claude-only wording; Codex is absent too), `agent-stream-events`,
`agent-context-usage` (per-runner mapping, 3 window requirements), `usage-accounting`,
`agent-capability-plane`, `agent-composer`, `runtime-diagnostics`. Appendix B §10 lists them.

## The fire test: Copilot on a PC where MCP is restricted

**How a company blocks MCP** (appendix A §D, documented plus code-read):
1. **"MCP servers in Copilot" org policy off.** This is the *default* for org seats. **Every** non-built-in server is blocked, local stdio and localhost HTTP alike. It shows as `is_mcp_enabled` in `%LOCALAPPDATA%\copilot\copilot-user-cache.json`.
2. **`managed-settings.json` allow/deny lists.**
   - Stdio servers match on the exact argv.
   - An unresolved `${VAR}` in the command blocks the server.
   - `[]` blocks all.
   - This applies to ACP since 1.0.88.
3. **Registry-only policy.** Fail-closed if the registry check endpoint is unreachable.

**What still works with MCP blocked:** ACP itself, so the Hub still streams, **approves** (axis 2),
cancels, resumes, meters and delivers messages in prompts. **Hooks** also still work: MCP policy does
not govern them; only `disableAllHooks`, managed `allowManagedHooksOnly` and folder trust do, and
`$COPILOT_HOME/hooks` needs no trust.

**What is lost:** the model can no longer *call* the Hub (send_message, update_task,
record_evidence, ask_user, …). Hooks cannot add model-callable tools. Only MCP or experimental
extensions can.

**So the fallback is the shim, chosen per run:**

```
 spawn with MCP ──▶ first prompt ──▶ did /mcp-adapter-online arrive for THIS run within N s?
                                      │ yes                         │ no / raw event says blocked
                                      ▼                             ▼
                              tool surface = MCP          tool surface = shim (aw <tool>)
                                                          notice tells the agent; _decide
                                                          auto-approves shell(aw …)
```

- **Detection is per run, not the permanent `mcp_adapter_online_at` flag.** That is F340's defect.
- **Corroboration** comes from raw events `session.mcp_servers_loaded` / `mcp_server_status_changed` and the `Warning: MCP server "…" was blocked by your enterprise` text chunk. **These arrive only with the first prompt, not during `session/new`** ✅.
  - So the first turn's notice cannot know the answer. Either run a cheap `/mcp list` slash prompt first (no model call), or phrase the notice as "if the `agentweave-*` tools are absent, use `aw`".
- **Packaging the Hub server as a Copilot plugin** (`--plugin-dir`) is worth one probe on the work PC. Lockdown messages quote "only plugin/managed MCP servers are permitted".
- **Findings this closes for Copilot:** F299 (no MCP-named approver), F301 (shim + Hub-answered permissions), F340 (per-run detection, reusable for Claude). F339 becomes moot for Copilot. The parked 2026-09-13 (i)/(ii)/(iii) question is retired by splitting axis 2 out.

## What is special about Copilot (no Claude Code / Codex equivalent)

**Worth using:**
- **Raw event subscription over ACP.** Send `clientCapabilities._meta["github.com/copilot"].events=[…]` in `initialize` and receive `github.com/copilot/sessionEvent` notifications. They carry:
  - per-call usage and cost, and session AIU and premium requests;
  - MCP server status;
  - permission requests, with whether a hook resolved them;
  - hook starts and ends;
  - subagent lifecycle and warnings.

  One structured stream holds everything the Hub meters and diagnoses. Limits: 32 KB per event, 256 in flight.
- **Hooks as an approval and telemetry channel that survives MCP policy**:
  - 14 events;
  - a `permissionRequest` that can allow or deny;
  - `preToolUse`, which can rewrite arguments. It **fails open on timeout**, so it is not to be trusted for denial.
  - `agentStop`, which can force another turn (capped at 8);
  - `postToolUse` / `notification`, which can inject context.
- **Native custom agents** (`.agent.md` with tools, model, effort and MCP servers in frontmatter) map directly onto AgentWeave's agent + charter. **Built-in agents** are usable as prompts: `/review`, `/security-review`, `/research`, `rubber-duck`, `explore`.
- **Plan mode is enforced**: project edits are blocked, not merely discouraged. **Autopilot** runs until `task_complete`.
- **Auto model selection** picks a model per session (`--auto-tier efficiency|balance|intelligence|fast`), reports what it chose (`session.auto_mode_resolved`), and costs 10% less on paid plans. A new "model" value for the catalog.
- **BYOK** (`COPILOT_PROVIDER_*`: openai / azure / anthropic, local Ollama, offline mode): Copilot's harness can run on the operator's own key or a local model, with no GitHub login.
- **Multi-model catalog in one runner**: Claude, GPT, Gemini, Grok, Kimi and MAI models behind one CLI.
- **Subagents** via the `task` tool, with plan-based concurrency (Free 2, Pro 4). Its SQL todo table surfaces as ACP `plan` updates.
- Built-in **GitHub MCP server** for issues, PRs and Actions. Disable it for hermetic runs; could be offered as an option.

**Not usable by a Hub that owns execution:** `/delegate` (Copilot cloud agent, remote), `--remote`/`--connect`, `copilot app`, `/fleet` (not supported under ACP), memory, `/every`/`/after` scheduling, voice, `/computer`. Extensions (`extension.mjs`, experimental) could add non-MCP tools, and are a later probe.

**Behaviours that differ and will bite** (each measured unless marked):
1. It reads **`CLAUDE.md` and `.claude/` (skills, agents, hooks)** by itself, and `--no-custom-instructions` is ignored under ACP (D2).
2. **Stdio MCP in ACP `session/new` is silently dropped**; only `--additional-mcp-config` injects stdio.
3. **ACP prompt usage is cumulative**, not per prompt.
4. **`session/set_model` never validates.** On a Free plan `--model` is silently overridden to Auto.
5. **`sessionStart` fires on the first prompt**, and `sessionEnd` fires at the end of *every* turn under ACP.
6. **Pre-session events are not forwarded**, so MCP status is first seen on the first prompt.
7. **Mode ids are URIs.** Plain `plan` returns -32602.
8. **MCP tool names have two spellings**: `server/tool` in `permissionRequest` hooks, `server-tool` everywhere else.
9. **`server/discover` precedes `initialize`** in its MCP client.
10. **Shell is PowerShell on Windows.**
11. **Environment GitHub tokens override the stored login.**
12. **The npm shim is two processes.**
13. **The CLI ships weekly.** Six integration-relevant changes landed between 1.0.25 and 1.0.88 (appendix A §K).
14. Reads and read-only shell commands **never ask**, so `_decide` never sees them. The Hub's view of reads comes from `tool_call` updates only.

## The change, sliced (for R1s, in this order)

Each slice is its own openspec change. Each goes through R1/R2/R3, then an Opus review before APPROVED.

0. **After tonight's queue.** About six of tonight's 28 changes touch this code: tool full names,
   permissions pill / `posture_at_rest`, ask-me card, run records calls, codex models, runner cannot
   collaborate (appendix B §11). Build on top of them, not beside them.
1. **`a-runner-is-an-adapter`: the seam, with no behaviour change.**
   - One `RunnerAdapter` per CLI owns:
     - command and transport;
     - event mapping;
     - MCP injection;
     - instruction channel;
     - posture mapping and write-tool table;
     - catalog provider;
     - launchability and auth;
     - usage extraction and context window;
     - resume id;
     - stop;
     - one-shot call.
   - Claude and Codex move onto it.
   - `resolve_access_path` splits into the three axes. Closes F393's "three disagreeing registries" as a side effect.
   - Proof: the full suite plus a drive of both runners, unchanged.
2. **`copilot-runs-over-acp`: the runner.**
   - `RUNNER_CLIS` gains `copilot` (the `runner-registry` delta).
   - The ACP client: initialize with raw events and a version gate; new/load; prompt; cancel.
   - `COPILOT_HOME` per agent, stdio MCP via `--additional-mcp-config`, and a spawn of `copilot.exe` directly.
   - `request_permission` → `_decide` and operator cards.
   - Postures mapped, including plan mode for read-only turns.
   - The ACP event mapper, the context meter from `usage_update`, and one-shot calls via `-p`.
   - UI: the literal, the icon, Auto in the picker.
3. **`a-run-reaches-the-hub-without-mcp`: runner-generic.**
   - Per-run MCP detection, replacing the permanent flag (F340).
   - The shim as a call mode of the pinned tool-server script.
   - `_decide` auto-approves the shim.
   - Notices say which surface this run has.
   - Closes F301 and F299 for Copilot; F340 for all.
4. **`copilot-spend-is-counted`:**
   - AI credits and premium requests as a unit in accounting, the allowance and the budget (D3).
   - Quota-exhaustion holds.
   - Per-call usage from raw events.
   - Checkpoint thresholds per runner (80% compaction).
   - **Done 2026-10-02:** built as `a-copilot-run-shows-its-credits` and archived as
     `openspec/changes/archive/2026-10-02-a-copilot-run-shows-its-credits/`. Its drive confirmed
     that the session checkpoint continues across `session/load`. Two items are left open: F481
     (no on-demand compaction for Copilot) and F482 (no real quota refusal captured yet).
5. **`copilot-agents-are-native`:**
   - Agent + charter rendered as a Copilot custom agent (D1).
   - Hub-owned hooks for telemetry and `agentStop`.
   - Built-in review and research agents as flow steps (optional).
   - BYOK exposure as a runner setting (optional).

Slices 2 and 3 together are the fire test. Slice 3 could go first if the work PC matters more than
parity.

## Decisions for the operator

- **D1: the instruction channel.** Options:
  - a custom agent file (native; carries tools, model and effort);
  - `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`;
  - an embedded resource on every prompt (works today, costs context every turn).
- **D2: repo instructions Copilot loads unasked.** In a repo like this one, a Copilot agent reads `CLAUDE.md`, `.claude/skills`, `.claude/agents` and `.claude/settings.json` hooks. That is useful as project knowledge, but wrong where it says "Claude". It cannot be turned off under ACP. Options: accept and document; or have the Hub-rendered context take precedence explicitly.
- **D3: the spend unit.** Options: count AI credits natively beside tokens; convert credits to dollars (1 credit = $0.01); or keep tokens (available per call) and show credits as information only.
- **D4: the test account.** This machine's Free plan is Auto-only with a small allowance. Every drive turn spends it, and "drive on Haiku" cannot be honoured. Options: drive on Free with Auto and accept the quota; use the work PC's plan; or use BYOK with the operator's Anthropic key through Copilot's harness (which keeps drives on Haiku).
- **D5: slice order.** Parity first (1→2→3), or the fire test first (1→3→2)?
- **D6:** the 2026-09-21 decision on F299/F301/F339/F340 says *"reopen when a runner that cannot take MCP — GHCP — is implemented"*. Its premise is wrong: Copilot *can* take MCP. What reopens them is Copilot on a *policy-restricted* machine. Record the correction?

**Answered by the operator, 2026-09-27** (`spec-queue/DECISIONS.md`, `ghcp-d1` to `ghcp-d6`):
- **D1:** a custom agent file for the stable context; per-turn material stays in the prompt.
- **D2:** Copilot-native files are written when a Copilot agent is created, into a Hub-owned `COPILOT_HOME`.
- **D3:** credits are shown as information, and tokens stay the unit.
- **D4:** Free plan for now. A Claude Max subscription cannot back Copilot's BYOK, which needs an API key.
- **D5:** parity first (1 → 2 → 3 → 4 → 5).
- **D6:** the 09-21 trigger is corrected.

## Probes to run on the work PC (before slice 3 is designed in detail)

Only the operator can run these. Each is a slash command or a flag, with no model call unless noted.
1. `copilot --version`; in an interactive session `/env` and `/mcp list`. Are MCP servers enabled at all? What policy source is named?
2. `%LOCALAPPDATA%\copilot\copilot-user-cache.json`: `is_mcp_enabled`, and the plan / SKU.
3. Does `copilot --acp` start at all (policy could disable it)? Is `allow_all` offered in `session/new`'s `configOptions`?
4. A stdio server via `--additional-mcp-config`: which status or warning appears?
5. The same server as a plugin (`--plugin-dir`): allowed?
6. Do user hooks in a custom `COPILOT_HOME` load (`allowManagedHooksOnly`)?
7. Can Copilot's `powershell` tool run a local script (the shim) without a policy refusal? One model call.

## Related

- `2026-09-20-the-approval-transport-is-not-the-tool-surface.md`: the three axes, which this note answers.
- `2026-07-29-stream-events-context-usage-boundary.md` and `2026-07-28-spec-journey.md`: the earlier documentation-only Copilot usage notes. The OTel file is still an option, but raw events make it unnecessary.
- Findings F299, F301, F339, F340 (the MCP-less path), F393 (the registries), F325 (per-runner context delivery), F302 (turn-start notice honesty).
- The legacy `copilot` entries in `src/agentweave/constants.py` and the dead branch at `hub/hub/launchability.py:116`: hints, not support.
