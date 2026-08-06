# Design — agent messaging delivery

## Reproduction of record

Everything below was observed on 2026-08-06 against a local Hub on `127.0.0.1:8010`, project
`proj-d9b5ed67` ("Two Codex Mini"), agents `codex-mini-1` / `codex-mini-2`, runner
`runner-f787147b` (`cli: codex`, `model: gpt-5.4-mini`), Codex CLI `0.146.0` on Windows 11.

| Run | Agent config | Observed |
|---|---|---|
| 1 | default (`yolo` unset) | 3× `agentweave.send_message: user cancelled MCP tool call` |
| 2 | `config.yolo = true` | `agentweave.send_message completed` → `Hub API error 405: Method Not Allowed` |

Run 2's 405 was traced to `POST http://127.0.0.1:8000/api/v1/agent-actions/messages`. Port 8000 was
held by a Docker-hosted older Hub (`curl http://127.0.0.1:8000/` returned an HTML shell with
`data-theme="cosmic"`, a theme system removed in `2026-08-04-hub-charcoal-visual-refresh`). The
route table of the *correct* Hub on 8010 confirms `POST /api/v1/agent-actions/messages` exists and
accepts POST, so the 405 could only have come from a different process.

## Decision 1 — how Codex approval is resolved

**This was determined empirically on 2026-08-06 against Codex CLI 0.146.0 on Windows 11**, using a
throwaway one-tool MCP server (`probe_ping`, returning a fixed token) so the result could not be
confused with an AgentWeave-specific fault. It is not: **every** MCP tool call in `codex exec` is
auto-cancelled under a sandbox, whatever the server.

### Verified results

| Configuration (with `--sandbox workspace-write` unless noted) | MCP call | Sandbox holds |
|---|---|---|
| default (`approvals_reviewer` unset → `user`) | ✗ cancelled | ✓ yes |
| `--ignore-user-config` | ✗ cancelled | — |
| `approval_policy="never"` | ✗ cancelled | — |
| `sandbox_workspace_write.network_access=true` | ✗ cancelled | — |
| `approvals_reviewer="auto_review"` | ✓ works | **✗ no** |
| `approvals_reviewer="guardian_subagent"` | ✓ works | **✗ no** |
| `--sandbox danger-full-access` | ✓ works | ✗ none by definition |
| `--dangerously-bypass-approvals-and-sandbox` | ✓ works | ✗ none by definition |

Sandbox holding was tested directly: the agent was told to write a file outside its workspace. Under
the default reviewer the file was never created. Under **both** `auto_review` and
`guardian_subagent` the write was approved and the file appeared on disk.

### What this rules out

- **`approval_policy="never"` is not "auto-approve".** It means never *ask*, which resolves an
  approval request as denied. It makes the failure certain, not absent.
- **There is no per-server trust or approval key.** Tested against a complete server definition
  under `--strict-config`, `mcp_servers.<name>` accepts `enabled` and `startup_timeout_sec` but
  rejects `tool_approval`, `auto_approve`, `trust`, `trusted`, and `approval_policy` as unknown
  fields. Codex 0.146.0 offers no way to trust one MCP server.
- **It is not caused by the operator's `config.toml`.** `--ignore-user-config` reproduces it, so
  `approvals_reviewer = "user"` present in that file is the default behaviour, not a local
  misconfiguration.
- **It is not a network restriction.** Granting `network_access` under `workspace-write` changes
  nothing.

### Within `codex exec`, the trade is unavoidable

**Within headless `exec` there is no configuration that permits MCP tool calls while preserving the
filesystem sandbox.** Every setting that permits the call permits *every* escalation. That is a
property of `exec`, not of Codex — and the distinction turns out to matter enormously.

## Decision 1a — `codex exec` is the wrong transport; use `codex app-server`

`exec` is one-shot and headless. There is no client attached to it, so anything requiring approval
is resolved by a policy rather than by an answer, and the only policies available are "deny
everything" (default, kills MCP) or "approve everything" (kills the sandbox).

**`codex app-server` is a different protocol with a client attached.** It speaks JSON-RPC over
stdio, and approval requests are sent *to the client*, which answers each one individually. The Hub
is a client. It can answer them.

### Verified against Codex CLI 0.146.0 on 2026-08-06

The app-server protocol was driven directly — `initialize` → `thread/start` (with
`sandbox: "workspace-write"` and the probe MCP server registered) → `turn/start` — and every
server→client request was logged.

**MCP tool calls arrive as `mcpServer/elicitation/request`**, carrying:

```json
{"serverName": "probe", "mode": "form",
 "_meta": {"codex_approval_kind": "mcp_tool_call",
           "persist": ["session", "always"],
           "tool_description": "...", "tool_params": {"note": "appserver"}}}
```

They are **distinguishable by server name and by `codex_approval_kind`**, which is exactly the
per-server granularity `exec` does not have. Answering `{"action": "accept"}` executed the tool.

**The decisive test** put both in one turn: call the MCP tool, *then* write a file outside the
workspace. Approving only the MCP elicitation and denying everything else produced:

| Server→client request | Answer | Outcome |
|---|---|---|
| `mcpServer/elicitation/request` (`kind: mcp_tool_call`, `server: probe`) | accept | tool executed, token returned |
| `item/commandExecution/requestApproval` ("write … outside the sandboxed workspace") | deny | **file never created** |

The sandbox held completely while collaboration worked. The schema confirms the separation is
structural, not incidental: `ServerRequest` declares `item/commandExecution/requestApproval`,
`item/fileChange/requestApproval`, `item/permissions/requestApproval`, and
`mcpServer/elicitation/request` as distinct methods.

### Verified 2026-08-06: existing session IDs resume cleanly through `thread/resume`

Section 5's open question in `implications-codex-appserver.md` — "existing stored Codex session
identifiers may not be resumable through the new path" — is resolved. Tested against a real
session recorded by the *current* `codex exec resume <session_id>` production path: run
`run-7c46ad24` (agent `codex-mini-1`, Hub `runs.session_id = 019fd481-71f1-7e90-98dc-9033753492bc`).

A standalone probe (`initialize` → `thread/resume` with `{"threadId": "019fd481-…"}`, no other
setup) returned a complete `ThreadResumeResponse`: full turn history (including the very
`send_message` call this change fixes, its recorded failure `"Hub API error 405: Method Not
Allowed"` preserved verbatim), `source: "exec"` correctly identifying the thread's origin, cwd,
git info, sandbox settings, and model — everything `thread/start` needs to be unnecessary for a
continuing conversation.

**No migration and no breakage.** `codex exec`'s session ID and `app-server`'s `threadId` are the
same identifier space — both resolve to the same on-disk rollout file
(`~/.codex/sessions/…/rollout-…-<id>.jsonl`). Every value already stored in `Run.session_id` for a
Codex run remains valid as `thread/resume`'s `threadId` after the transport swap; task 2.6 requires
no translation layer and no data migration.

### Consequence

**The original requirement stands and is restored.** Collaboration costs nothing. The Hub approves
tool calls for the one MCP server it installed, and answers every other approval according to the
sandbox the operator selected. `approvals_reviewer` is not used, `yolo` keeps its current meaning
and is not required for messaging, and no new operator-facing trade is introduced.

### Cost, stated honestly

This is a **transport rearchitecture of the Codex runner**, not a flag. `codex exec` is a one-shot
subprocess whose `--json` stdout is parsed; `app-server` is a persistent JSON-RPC peer with threads,
turns, and a request/response obligation in both directions. It touches command construction, output
parsing, session resume, and the run lifecycle.

It is worth it beyond this bug: structured protocol events replace stdout scraping, thread and turn
identity become first-class instead of inferred, and usage reporting arrives as data.

`app-server` is marked `[experimental]` in `codex --help`. That is a real risk and is recorded
below. It is mitigated by keeping the `exec` path until the app-server path is verified equivalent,
not by adopting on faith.

### Staging

Section 3 (the callback address) is independent of this and much smaller. It should land first: it
is a correctness fix that stands on its own, and it is what turns a mis-delivered write into a
refusal.

## Decision 2 — the Hub's own address

`settings.aw_port` describes *intent*; the bound socket describes *fact*. Uvicorn can be told a port
by CLI argument, by env var, by programmatic `run()`, or be given `port=0`, and only one of those
paths flows through `settings`.

The Hub SHALL capture its actually-bound address from the running server's socket and every agent
callback URL SHALL be derived from that captured value.

**Implemented differently than first scoped here.** uvicorn's own `Server.startup()` calls
`await self.lifespan.startup()` *before* it binds the listening socket in the standard host/port
path (verified against installed uvicorn 0.41.0 source) — the address genuinely cannot be observed
from inside the lifespan hook. Instead, HTTP middleware records `request.scope["server"]` — the real
accepted-connection address uvicorn's transport layer reports (`get_local_addr(transport)`), not
configured intent — into a module-level global (`hub/hub/bound_address.py`) on every request. A
module global rather than `app.state` because `trigger_agent_directly` is deliberately
request-decoupled: the scheduler calls it with no HTTP request in flight, so nothing but a value
observed from some *prior* request is available at that call site. This is the risk section's
anticipated fallback ("prefer the ASGI lifespan's view of the server over reaching into uvicorn
internals") landing on the side that was actually available.

`HUB_URL`, when explicitly set in the Hub's own environment, remains an intentional operator
override and keeps precedence: a reverse proxy or container publishing a different external address
is a real deployment. What is removed is the *silent* fallback to a configured default. If neither
an explicit `HUB_URL` nor a captured bound address is available, starting a run is an error.

## Decision 3 — run credentials are instance-scoped

Fixing the URL removes the reproduction but not the class of failure. Any future path that sends an
agent action to the wrong Hub should fail closed.

A run token is minted by one Hub instance and recorded in one database. The receiving Hub already
looks the run up; today a token from another instance simply fails to resolve, which is correct but
indistinguishable from an expired token. The instance identity SHALL be carried and checked
explicitly so the rejection reason is diagnosable, and so a future shared-database deployment cannot
turn a mis-delivery into a successful cross-instance write.

## Decision 4 — failure visibility

`hub/hub/mcp_server.py` raises `HubAPIError` / `RuntimeError` into the agent's transcript and
nowhere else. Two changes:

1. The MCP adapter's error text SHALL name the endpoint it attempted, so a mis-delivered call is
   diagnosable from the transcript alone. The current text (`Hub API error 405: Method Not Allowed`)
   omits the one fact that mattered.
2. A tool call the Hub *can* observe failing SHALL be recorded as a run event and surfaced on the
   agent timeline. A call denied before leaving the agent's process (Defect 1) is by construction
   not observable Hub-side; this is why Decision 1 must fix that case rather than report it.

## Decision 5 — runner name mojibake

`GET /runners` returns `"Codex CLI â€” GPT-5.4-Mini"`. That is a UTF-8 em dash (`—`, `E2 80 94`)
decoded as Latin-1 and re-encoded. The auto-provisioning path in `hub/hub/api/v1/agents.py` builds
this name. Implementation must first establish **where** the double-encoding happens — name
construction, DB write, or response serialisation — because the fix differs, and any already-stored
name needs repairing or regenerating, not just the new ones.

This is bundled here rather than in the UI change because it is a data-correctness bug in the same
provisioning path, not a visual one.

## Decision 6 — Claude has the same class of defect, with a cheaper fix (task 2.15)

**This was determined empirically on 2026-08-06 against Claude Code CLI 2.1.221**, using the same
throwaway one-tool MCP server as Decision 1, driven headless (`-p`, `--output-format stream-json`,
no `--dangerously-skip-permissions`) — the exact shape of a non-yolo Hub-spawned Claude run.

### The first result was confounded, and the confound itself is a finding

The first run (no explicit `--permission-mode`) showed the MCP tool call *and* a `Write` to a path
outside the working directory both succeeding silently, with no prompt and no error. This is not
Claude Code's out-of-the-box behavior: this development machine's `~/.claude/settings.json` sets
`"permissions": {"defaultMode": "bypassPermissions"}` as the operator's own personal convenience
setting, and the Hub's current `_build_claude_command` (`runner_commands.py`) never passes
`--permission-mode` at all for a non-yolo run — so it silently inherits whatever the *operator's own
machine* has configured globally, not what the agent's `yolo` setting says.

**This is a distinct, separately actionable finding**: whether a "non-yolo" Claude agent is actually
sandboxed today depends on the Hub operator's own `~/.claude/settings.json`, not on the Hub's own
`yolo` flag. On a fresh install (no such override) the CLI's documented posture is to ask for
permission — which headless mode cannot answer — so the likely default-install behavior is closer to
the blocked case below, not the silently-permissive one this specific machine produced.

### Controlling for it: `--permission-mode manual`

A CLI flag overrides `settings.json`, so `--permission-mode manual` isolates the variable under test
without touching this machine's real settings (swapping `HOME`/`USERPROFILE` to get a clean profile
was tried first and rejected — it also drops this machine's auth, since Claude Code stores
credentials there too). Under `--permission-mode manual`, **both** the MCP tool call and the
out-of-cwd write were refused with the identical, undifferentiated message:

```
Claude requested permissions to use mcp__probe__probe_ping, but you haven't granted it yet.
Claude requested permissions to write to <path>, but you haven't granted it yet.
```

**This is the same class of defect Decision 1 found in `codex exec`**: no distinction exists at this
layer between "the Hub's own tool" and "an arbitrary filesystem write" — both are gated by one
undifferentiated permission check, and headless mode has no way to answer it. A non-yolo Claude
agent, correctly configured for its own sandbox, cannot use AgentWeave's MCP tools at all — the exact
trade Decision 1a's `app-server` rewrite exists to avoid for Codex.

### Unlike Codex, no transport rewrite is needed

Claude Code exposes `--allowedTools` (per-tool static allowlist, e.g. `"mcp__agentweave__*"`) as a
CLI flag. Verified live: `--permission-mode manual --allowedTools "mcp__probe__probe_ping"` let the
probe tool execute normally while the out-of-cwd `Write` was **still refused**, with the identical
permission-denied message as the fully-blocked case above. **Do not assume parity in either
direction, per task 2.15's own instruction — this is the asymmetry**: Codex needed a new transport
because `exec`'s approval is a one-shot policy with no client attached; Claude's gate is a static,
spawn-time allowlist the Hub can already set on every invocation via `runner_commands.py`, no new
runner architecture required.

### What is and is not established

- **Established**: the defect exists in Claude Code 2.1.221 under an explicit, non-bypass permission
  mode. The fix shape (`--permission-mode manual` + `--allowedTools "mcp__agentweave__*"` for
  non-yolo Claude runs) is verified to separate "the Hub's own tools work" from "the sandbox holds."
- **Not established, and out of scope for this change**: what the CLI's true default resolves to
  with zero explicit configuration on a fresh install (inferred, not directly measured, from
  `--dangerously-skip-permissions`'s existence as a named escape hatch and from `manual` mode's
  behavior — not from a clean-profile run, since that would have required dropping this machine's
  auth); whether `--allowedTools` needs the explicit `--permission-mode manual` alongside it on a
  machine with no `bypassPermissions` override, or is sufficient alone (the one test with
  `--allowedTools` and no `--permission-mode` flag ran on this machine's `bypassPermissions`-default
  profile, so it is not a clean read); and whether implementing this fix in `_build_claude_command`
  belongs in this change or a follow-on — it changes every non-yolo Claude run's command line, a
  larger blast radius than task 2.15's own scope ("record what was established").

## Risks

- **The Codex approval key may differ across Codex versions.** Mitigation: task 1.1 verifies against
  the installed CLI, and the fallback in Decision 1 keeps the failure loud instead of silent.
- **Capturing the bound address is uvicorn-shaped.** Mitigation: prefer the ASGI lifespan's view of
  the server over reaching into uvicorn internals; if the address genuinely cannot be observed,
  Decision 2's "refuse rather than guess" rule applies.
- **Stale Hub instances on neighbouring ports are an operator-environment hazard**, not only a code
  bug. The instance-scoped credential check (Decision 3) is what makes the environment hazard
  harmless.

See also `implications-codex-appserver.md` in this change directory for the full consequence
analysis of Decision 1a.
