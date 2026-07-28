## Why

Developers and teams need a way to participate as a first-class agent in an AgentWeave session while remaining in control — receiving messages from automated agents, delegating work, and responding on their own schedule, all from an interactive terminal session. The current system treats every agent identically: the watchdog auto-triggers all of them, making it impossible to run as a human-piloted participant without being constantly interrupted.

## What Changes

- Add a `pilot` boolean flag to per-agent config in `session.json` (and synced to Hub)
- Watchdog skips auto-execution for agents with `pilot: true` — messages pile up silently
- New CLI command: `agentweave agent configure <agent> --pilot / --no-pilot`
- New MCP tool `register_session(session_id)` for pilot agents to self-register their `--resume` session ID with the Hub
- New Hub API endpoint `POST /api/v1/agents/{agent}/register-session`
- On registration: regenerate `.agentweave/agent-context/{agent}.md` and print the ready-to-use launch command
- Hub UI: PILOT badge on agent cards, registered session display, register session form, trigger button disabled for pilot agents
- Hub DB: `pilot` and `registered_session_id` columns on Agent model

## Capabilities

### New Capabilities

- `pilot-mode`: Per-agent flag and supporting mechanics that mark an agent as human-controlled — disables auto-trigger, enables pull-based inbox access
- `session-registration`: One-time registration of a CLI session ID (`--resume`) with the Hub, via MCP tool, CLI command, or Hub UI form; latest registration replaces previous

### Modified Capabilities

## Impact

- `src/agentweave/session.py` — add `pilot` field to agent config schema
- `src/agentweave/watchdog.py` — guard: skip auto-execute for pilot agents
- `src/agentweave/cli.py` — `agentweave agent configure --pilot / --no-pilot`; `agentweave session register` command
- `src/agentweave/mcp/server.py` — new `register_session` MCP tool
- `src/agentweave/constants.py` — add pilot to valid agent config keys
- `hub/hub/db/models.py` — add `pilot` (bool) and `registered_session_id` (str, nullable) to Agent model
- `hub/hub/api/v1/agents.py` — new register-session endpoint
- `hub/hub/api/v1/agent_trigger.py` — check pilot flag before executing
- `hub/hub/mcp_server.py` — new `register_session` MCP tool
- `hub/ui/src/components/agents/AgentCard.tsx` — PILOT badge
- `hub/ui/src/components/agents/AgentInfoTab.tsx` — registered session + register form
- `hub/ui/src/components/agents/AgentPromptPanel.tsx` — disable trigger for pilot agents
- `hub/ui/src/api/agents.ts` — register session mutation hook
