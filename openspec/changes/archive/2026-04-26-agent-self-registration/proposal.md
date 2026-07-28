## Why

AgentWeave today requires every agent to be declared in `agentweave.yml` before a session starts, and the watchdog can only reach agents it knows how to spawn headlessly (Claude, Kimi). Adding any new agent type — Hermes, a custom script, or any third-party AI tool — requires code changes in AgentWeave itself. This limits the platform to a closed list of supported agents and prevents the ecosystem from growing organically.

## What Changes

- **New MCP tool `register_agent()`**: any agent with a Hub URL and project API key can join a session at runtime by declaring its name and contact mode.
- **New MCP tool `get_context()`**: agents retrieve their role guide as a string over MCP, replacing the assumption that agents read files from disk.
- **New MCP tool `heartbeat()`**: agents signal liveness to the Hub periodically; the Hub shows online/offline status in the dashboard.
- **Registration is idempotent**: agents can call `register_agent()` freely after `/compact` or a restart without side effects. No per-agent token — the project API key is the security boundary.
- **Contact mode field**: agents declare how AgentWeave should reach them (`poll`, `mcp-push`, `watchdog-spawn`). Phase 1 ships `poll` only.
- **Hub DB extended**: four new columns on the `Agent` table store self-registration metadata.
- **Watchdog guard**: one check skips self-registered `poll` agents — they manage their own inbox polling.
- **Hub UI**: self-registered agents appear in the dashboard alongside configured agents, with an online/offline badge.

No changes to `agentweave.yml`, `config.py`, `session.py`, or any existing MCP tools. Claude and Kimi are unaffected.

## Capabilities

### New Capabilities

- `agent-registration`: MCP-based agent self-registration, idempotent re-registration, contact mode declaration, and role + context delivery at registration time.
- `agent-context-delivery`: serving role guide content over MCP via `get_context()` so agents don't need filesystem access to bootstrap.
- `agent-liveness`: heartbeat tool and Hub-side liveness tracking (last heartbeat timestamp, online/offline status in the dashboard).

### Modified Capabilities

None — this change is purely additive.

## Impact

**`src/agentweave/mcp/server.py`** — three new `@mcp.tool()` functions added.

**`hub/hub/mcp_server.py`** — same three tools added on the Hub side.

**`hub/hub/db/models.py`** — four new nullable columns on `Agent`: `contact_mode`, `self_registered`, `mcp_endpoint`, `spawn_cmd`. `AgentHeartbeat` table unchanged.

**`hub/hub/db/engine.py`** — Alembic migration for new columns.

**`hub/hub/api/v1/agents.py`** — `GET /api/v1/agents` extended to include self-registered agents from the DB alongside session-configured agents.

**`src/agentweave/watchdog.py`** — one guard: skip self-registered agents with `contact_mode=poll`.

**`src/agentweave/constants.py`** — `CONTACT_MODES` constant added.

**Hub UI** — additive: badge and panel section for self-registered agents.
