# Design — non-yolo Claude runs get an explicit permission mode

The research behind this change already happened, live, in
`2026-08-06-agent-messaging-delivery/design.md` Decision 6. This document does not repeat that
experiment; it records the two implementation decisions specific to landing the fix in
`runner_commands.py`.

## Decision 1 — `--permission-mode manual`, not `--permission-mode plan` or another mode

Claude Code's non-bypass permission modes were not individually re-surveyed this change; Decision 6
verified `manual` specifically (both an MCP call and an out-of-cwd write refused identically without
`--allowedTools`; the MCP call alone permitted with it). `manual` is the mode this change ships because
it is the only one measured. Do not substitute a different mode without re-verifying live — the
Decision 6 finding is mode-specific, not "any non-bypass mode behaves this way."

## Decision 2 — the allowlist is the literal wildcard string, not an enumerated tool list

`_build_claude_command` already hardcodes `"agentweave"` as the `mcpServers` key a few lines above
where `--allowedTools` is added (`hub/hub/runner_commands.py:127-136`). Claude Code exposes an MCP
server's tools to the CLI as `mcp__<server-key>__<tool-name>`, and `--allowedTools` accepts glob
patterns, so `"mcp__agentweave__*"` covers every tool the Hub's `mcp_server.py` declares today
(`send_message`, `create_task`, `list_tasks`, `get_task`, `update_task`, `ask_user`, `get_answer`,
`request_agent`, `create_job`, `delete_job`, `toggle_job`, `run_job` — see its `@mcp.tool()`
decorators) and any added later, without this file needing to enumerate them by name. The two strings
(`"agentweave"` the mcpServers key, `"mcp__agentweave__*"` the allowlist pattern) are not derived from
one shared constant — they are two literals that must agree by convention. If the mcpServers key ever
changes, both call sites in this function need to change together; there is currently no test that
would catch only one of them changing (added as part of this change — see tasks).

## Decision 3 — the allowlist flag is added only when `mcp_command` is set, not unconditionally

A non-yolo run with no MCP command configured (unusual today, since the Hub always passes one, but not
structurally impossible) has nothing to allowlist. Adding `--allowedTools` unconditionally would be
dead argv for that case; gating it on the existing `if mcp_command:` branch keeps the two flags'
presence tied to what they actually govern.

## Not decided here

- Whether `manual` is the right mode for a fresh install with no `bypassPermissions` override —
  Decision 6 states the true zero-config default was never directly measured. This change makes the
  Hub's command line explicit either way; it does not depend on knowing that answer.
- Any operator-facing surface for a refusal under the new, now-real sandbox. That is
  `2026-08-06-operator-in-the-loop-turns`'s escalation feature, deferred independently of this change.
