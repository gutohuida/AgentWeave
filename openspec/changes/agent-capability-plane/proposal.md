## Why

The Hub-native umbrella already narrowed the MCP tool list and bound the stdio adapter to
`AW_AGENT_IDENTITY`, but the underlying application boundary is still not least privilege. A
Hub-spawned agent receives a full project API key (`HUB_API_KEY`), so it can call operator routes
directly. Messaging, task, and question REST bodies still accept caller-supplied agent names, and
only scheduled-job mutations consistently validate the `X-AgentWeave-Agent`/`Run` pair. The MCP
adapter is therefore safer than direct HTTP instead of being a thin equal-capability transport.

The archived conversation-workspace slice table identifies an independent **Agent capability
plane** successor: one least-privilege read/write application API for agents, available through
direct HTTP and a thin MCP adapter with equal capability and run-bound attribution. This change
closes that dependency and unlocks the single-runtime successor.

## What Changes

- Mint an unguessable credential for each Hub-owned run, persist only its digest, inject the secret
  into that run, and accept it only while the matching run is active.
- Add one agent-facing application API whose actor (project, agent, run) is derived exclusively from
  that credential. A project/operator API key cannot impersonate a run on this surface, and a run
  credential cannot access operator routes.
- Expose only outbound intent: peer messages, shared task-ledger reads/writes, operator questions
  and answers, governed agent requests, and governed scheduled-work mutations.
- Persist run attribution on every agent-caused effect, not only in transient headers or logs.
- Make MCP and ordinary command access thin adapters over exactly that API and remove the full
  project credential from spawned-agent environments.
- Verify capability and error parity across direct HTTP, MCP, and command paths, including refusal
  after run termination and structural impossibility of caller-selected identity.

## Capabilities

### New Capabilities

- `agent-capability-plane`: run-scoped authentication, least-privilege agent application API,
  durable effect attribution, and transport parity.

### Modified Capabilities

- `agent-tool-surface`: its existing intent-only and attribution requirements are retained, but the
  underlying security boundary moves from inherited identity/project credentials to the new
  run-scoped capability plane.

## Impact

- Run/effect database models and migrations.
- Authentication dependencies and new agent-facing routes/services.
- Hub spawn environment, canonical MCP adapter, and CLI HTTP transport/commands.
- Existing operator routes remain project-key authenticated and do not become agent-callable.
- Single-runtime work may proceed after this change archives.

