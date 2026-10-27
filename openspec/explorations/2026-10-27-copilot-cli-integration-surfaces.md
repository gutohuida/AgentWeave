# Copilot CLI integration surfaces: ACP vs. the Copilot SDK

**Date:** 2026-10-27  **Author:** Architect (operator request)  **CLI:** 1.0.102-0.unstable, bundled
`@github/copilot-sdk` 1.0.13-preview.4 (SDK protocol version 3)
**Findings:** F1046, F1047, F1048, F1049 in `scripts/drive/FINDINGS.md`
**Probes:** `scripts/drive/d1027_copilot_bg_ctx_probe.py` (ACP) and
`scripts/drive/d1027_copilot_sdk_probe.mjs` (SDK). Both use the same models and prompts.

## Question

The operator asked whether AgentWeave uses Copilot the way it is meant to be used, and why the
Copilot runner has a turn timeout. The suspicion was that the fixes proposed for F1046–F1048 patch
over the wrong integration. They do.

## The surfaces Copilot CLI offers

| Surface | How it starts | Built for | Protocol |
|---|---|---|---|
| Interactive TUI | `copilot` | a person at a terminal | n/a |
| One-shot | `copilot -p "..."` | scripts, single prompt | text or JSON output |
| **ACP server** (what `hub/hub/copilot_acp.py` uses) | `copilot --acp --stdio` | **editors and IDEs** (Zed, JetBrains, Neovim) | Agent Client Protocol: open standard, NDJSON JSON-RPC, `session/new`, `session/prompt`, `session/update`, `session/request_permission`, `session/cancel` |
| **SDK server** (what GitHub's SDKs use) | `copilot --headless --no-auto-update --stdio` (or TCP) | **applications that embed Copilot** | Copilot's own JSON-RPC (LSP-style `Content-Length` framing). The SDK calls 318 methods. Official SDKs: Python (`github-copilot-sdk`), TypeScript, Go, .NET, Java, Rust. |

Both server modes are documented by GitHub as public preview. The Python SDK on PyPI is 1.0.27,
"Development Status :: 3 - Alpha", needs Python 3.11 or later, and depends on pydantic, httpx and
python-dateutil.

### Why ACP exists

Zed created ACP as an editor-to-agent standard, the agent counterpart of LSP: one client works with
every compliant agent. Its strengths are vendor neutrality, a versioned public spec, and the features
an editor needs (permission prompts, delegated file and terminal access, diffs, session load).
GitHub's ACP docs list "IDE integrations" first.

ACP fixes most per-session settings when the server starts. Per GitHub's docs, `session/new` carries
only `cwd` and MCP servers, and tool filters and reasoning effort come from the server's launch
flags. It has no concept of context tier, background agents or spend limits.

### Why AgentWeave chose ACP (and what it missed)

`openspec/explorations/2026-09-27-copilot-as-a-full-runner.md` compared ACP only with `-p`:
"`-p` cannot ask anybody … ACP is Copilot's equivalent of `codex app-server`". That reasoning is
right about `-p`. The SDK server (`--headless`) was never considered. It is the actual counterpart of
`codex app-server`: a programmatic host protocol from the same vendor as the runtime.

## Measured differences (probes run 2026-10-27)

| Need | ACP (current) | SDK server | Evidence |
|---|---|---|---|
| 1M context window | **Impossible.** No `contextTier` anywhere in the ACP agent's code. `usage_info.tokenLimit` was 200000 for opus-5.5 default, opus-5.5 `--context long_context`, and sonnet-5.5 `long_context`. | `createSession({contextTier: "long_context"})` gave **`tokenLimit` 1000000** for claude-opus-5.5. Default tier gave 200000. | `sdk_ctx_opus_long.jsonl`, `sdk_ctx_opus_default.jsonl`. `app.js`: ACP `newSession`/`loadSession` pass no tier. |
| Know the root agent finished, with background work still running | `session/prompt` returns only when every background agent is done (68.5 s for a 60 s sleep). Root `assistant.turn_end` (t=6.3 s) and `session.idle` (t=72.3 s) **are** forwarded if subscribed, but the Hub subscribes to neither. | Same events, plus `session.background_tasks_changed` as background tasks start and stop. `send()` returns at once (0.003 s), and completion is `session.idle`. | `acp_bg_events.jsonl`, `sdk_bg_sonnet55.jsonl` |
| List or cancel one background agent | No. Copilot's ACP agent implements no extension methods (no `extMethod`), and `session/cancel` cancels everything. | `session.tasks.list`, `session.tasks.cancel`, `session.tasks.waitForPending`, `session.cancelAllBackgroundAgents`, `session.tasks.getProgress` | `copilot-sdk/index.js` method table |
| Sub-agent model and tier | No | `session.tools.updateSubagentSettings`; the `task` tool takes `context_tier` | SDK method table, `app.js` |
| Context meter per agent | `usage_update` has no agent id, so sub-agent samples get mixed into the root's meter (F1047). | Every event carries `agentId`; `session.usage_info` has `tokenLimit` and `currentTokens`. | both probes |
| Spend bound | none | `sessionLimits.maxAiCredits` (experimental) | `generated/session-events.d.ts` |
| Ask the operator for permission | `session/request_permission` | `onPermissionRequest` async handler (also `onUserInputRequest`, `onElicitationRequest`) | `types.d.ts` |
| Resume a conversation | `session/load` (replays history) | `resumeSession(id)`, `listSessions`, `getLastSessionId` | `client.d.ts` |
| MCP servers, tool filters, system prompt | MCP per session; tool filters only at server launch | per session: `mcpServers`, `availableTools`/`excludedTools`, `systemMessage`, `customAgents`, `skillDirectories`, `hooks` | `types.d.ts` |
| Turn timeout | none | none (`sendAndWait`'s timeout is only how long the caller waits; it "does not abort in-flight agent work") | `session.d.ts` |

Copilot's own semantics are the same on both surfaces. A session is idle only when the root agent,
its background agents and any attached shells are all done. When a background agent finishes,
Copilot resumes the root with a `system.notification` (`agent_idle`) inside the same prompt. That is
Copilot's design, not an ACP artefact.

## Why the Hub has a 600 s turn timeout

`copilot_acp.py` reuses `codex_appserver.DEFAULT_TURN_TIMEOUT_SECONDS = 600`, which was written for
Codex ("No protocol-level turn timeout exists … so a stuck app-server cannot wedge an agent
forever"). The Claude runner has no turn wall clock: a run ends when its process exits. Neither
Copilot surface has a turn timeout.

A fixed wall clock is the wrong instrument for Copilot:
- It cannot tell a hung turn from a working one.
- It kills background agents the model started on purpose (F1046: the FinOps Architect was cut at
  600 s twice, and its sub-agents died with it).

Copilot provides what a correct bound needs: a continuous event stream for liveness,
`background_tasks_changed`, and `tasks.list`/`tasks.cancel`. The bound should be an **inactivity
limit** (no events for N minutes) plus an optional operator-set cap, not 600 s total.

## Assessment of earlier proposals

| Proposal | Verdict |
|---|---|
| F1046 "extend the deadline while sub-agents run" | **Superseded.** Replace the wall clock with an inactivity bound driven by Copilot's events. |
| F1046 "tell agents background work counts against the turn" | Still useful as guidance, but it is a workaround. |
| F1047 "drop sub-agent usage samples" | **Correct fix on ACP:** take the meter from root-only `session.usage_info` (it has `agentId` and `tokenLimit`), not `usage_update`. |
| F1048 "report upstream / use the Claude runner" | Only the SDK surface gives 1M today. Upstream ACP may never add `contextTier`. |
| D "per-agent turn limit (migration)" | Unnecessary if the bound becomes inactivity-based. |

## Recommendation

1. **Now, still on ACP (Tier 1):**
   - Subscribe to `assistant.turn_end`, `session.idle`, `session.background_tasks_changed`,
     `session.usage_info` and `system.notification`.
   - Replace the 600 s wall clock with an inactivity bound.
   - Show "root finished, background agents running" as running work.
   - Source the context meter from root `session.usage_info`.
   - Fixes F1046 and F1047.
2. **Next (Tier 2, runner transport):** move the Copilot runner to the SDK server. Either use the
   official Python SDK, which is alpha and adds three dependencies to the Hub, or speak its JSON-RPC
   directly the way `codex_appserver.py` speaks Codex's.
   - Gains: 1M context (F1048), per-agent background control, sub-agent settings, spend limits, and
     per-session tool filters.
   - Hazards: both surfaces are preview, and much of the SDK protocol is `@experimental`. Pin the
     CLI version (`--no-auto-update` is already passed). Keep a protocol-version check
     (`SDK_PROTOCOL_VERSION = 3`), and keep the d1027 probes as a drive that runs on CLI upgrade.

## Limits of this research

- Probes ran single prompts. A plain turn with no background agents was not shown to hang or not
  hang, and the inactivity threshold needs a drive on real runs.
- The SDK probe used the bundled Node SDK, not the Python SDK.
- The permission and ask-user round trip, MCP config and session resume were checked against the
  SDK's type definitions, not driven.
- 1M context was confirmed as the window the session reports (`tokenLimit`), not by filling it.
