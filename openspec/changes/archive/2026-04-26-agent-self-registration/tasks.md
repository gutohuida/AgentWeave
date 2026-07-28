## 1. Constants and shared types

- [x] 1.1 Add `CONTACT_MODES = ["poll", "mcp-push", "watchdog-spawn"]` to `src/agentweave/constants.py`

## 2. Hub DB migration

- [x] 2.1 Add four nullable columns to `Agent` model in `hub/hub/db/models.py`: `contact_mode` (String, nullable), `self_registered` (Boolean, default False), `mcp_endpoint` (String, nullable), `spawn_cmd` (JSON, nullable)
- [x] 2.2 Generate Alembic migration in `hub/hub/db/` for the new Agent columns
- [x] 2.3 Verify migration applies cleanly against an existing DB without data loss

## 3. CLI MCP server — new tools

- [x] 3.1 Add `register_agent(name, contact_mode, role_request, mcp_endpoint, spawn_cmd)` to `src/agentweave/mcp/server.py` — validates contact_mode, rejects configured-agent name collisions, returns `{ role, context }`
- [x] 3.2 Add `get_context(role)` to `src/agentweave/mcp/server.py` — loads role template from `templates/roles/<role>.md`, returns `{ content }` or `{ error }`
- [x] 3.3 Add `heartbeat(agent)` to `src/agentweave/mcp/server.py` — validates agent is registered, returns `{ ok }`
- [x] 3.4 Guard all three tools to return an error when transport is not HTTP

## 4. Hub MCP server — new tools

- [x] 4.1 Add `register_agent()` to `hub/hub/mcp_server.py` — writes/updates Agent row in DB, returns role and context inline
- [x] 4.2 Add `get_context()` to `hub/hub/mcp_server.py` — reads role template and returns content
- [x] 4.3 Add `heartbeat()` to `hub/hub/mcp_server.py` — writes AgentHeartbeat row, validates agent exists

## 5. Hub API — agents endpoint

- [x] 5.1 Update `GET /api/v1/agents` in `hub/hub/api/v1/agents.py` to merge self-registered agents from the `Agent` DB table into the response
- [x] 5.2 Add `self_registered` boolean field to each agent entry in the response
- [x] 5.3 Add `liveness` field (`online` / `offline`) derived from last heartbeat age (threshold: 2 minutes)

## 6. Watchdog guard

- [x] 6.1 Add `is_self_registered(agent)` helper in `src/agentweave/watchdog.py` (or session/transport layer) that checks Hub DB via HTTP transport
- [x] 6.2 Add guard in the watchdog agent-processing loop: skip agents where `self_registered=True` and `contact_mode="poll"`
- [x] 6.3 Verify existing Claude and Kimi agents are unaffected by the guard

## 7. Hub UI

- [x] 7.1 Add `self_registered` and `liveness` fields to the agent API TypeScript types in `hub/ui/src/api/agents.ts`
- [x] 7.2 Add a "Self-Registered" or "External" badge variant to the agent badge components
- [x] 7.3 Display the badge on `AgentCard` for self-registered agents
- [x] 7.4 Display online/offline liveness indicator on `AgentCard` for self-registered agents

## 8. Tests

- [x] 8.1 Add unit tests for `register_agent()` MCP tool: success, re-registration, name collision, invalid contact_mode, non-HTTP transport
- [x] 8.2 Add unit tests for `get_context()`: valid role, unknown role
- [x] 8.3 Add unit tests for `heartbeat()`: success, unknown agent
- [x] 8.4 Add unit test for watchdog guard: self-registered poll agent is skipped, Claude/Kimi are not skipped
- [x] 8.5 Add integration test for `GET /api/v1/agents` returning self-registered agents with liveness field
