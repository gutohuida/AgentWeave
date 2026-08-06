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

### The consequence — a requirement had to change

**On Codex 0.146.0 there is no configuration that permits MCP tool calls while preserving the
filesystem sandbox.** The three settings that permit the call all do so by permitting *every*
escalation.

This invalidates the original requirement that collaboration must not cost the sandbox. It was
written before the behaviour was measured and it is not satisfiable on this provider. Pretending
otherwise would either block the feature indefinitely or produce an implementation that quietly
claims a protection it does not have.

**Chosen: make the trade explicit, operator-owned, and visible, rather than implicit.**

A Codex agent that can collaborate is a Codex agent whose escalations are auto-approved. The Hub's
obligation is therefore to (a) never make that choice silently on the operator's behalf, (b) state
plainly what is given up, and (c) keep the sandboxed-and-non-collaborating configuration available
and working for operators who prefer it.

`auto_review` is preferred over `guardian_subagent` for this purpose: both failed the sandbox test
identically, and `guardian_subagent` additionally spends model calls per approval for a protection
it did not provide.

### Not closed

Per-server MCP trust is the setting this actually needs, and Codex does not have it. This is worth
raising upstream. If a future Codex version adds it, the requirement reverts to the stronger form
and the operator-facing trade disappears — the spec should be re-tightened at that point, not left
permanently relaxed.

## Decision 2 — the Hub's own address

`settings.aw_port` describes *intent*; the bound socket describes *fact*. Uvicorn can be told a port
by CLI argument, by env var, by programmatic `run()`, or be given `port=0`, and only one of those
paths flows through `settings`.

The Hub SHALL capture its actually-bound address during startup — from the running server's socket,
in the lifespan hook — and every agent callback URL SHALL be derived from that captured value.

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

## Risks

- **The Codex approval key may differ across Codex versions.** Mitigation: task 1.1 verifies against
  the installed CLI, and the fallback in Decision 1 keeps the failure loud instead of silent.
- **Capturing the bound address is uvicorn-shaped.** Mitigation: prefer the ASGI lifespan's view of
  the server over reaching into uvicorn internals; if the address genuinely cannot be observed,
  Decision 2's "refuse rather than guess" rule applies.
- **Stale Hub instances on neighbouring ports are an operator-environment hazard**, not only a code
  bug. The instance-scoped credential check (Decision 3) is what makes the environment hazard
  harmless.
