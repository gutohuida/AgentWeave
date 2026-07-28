## Context

AgentWeave's current agent model is static: agents are declared in `agentweave.yml`, the watchdog knows their runner type (claude, kimi, claude_proxy, manual), and all communication flows from AgentWeave outward (spawn process → agent reads inbox via MCP). This works well for known agents but makes it impossible for third-party agents (Hermes, custom scripts) to join a session without modifying AgentWeave's code.

The Hub already has an `Agent` DB table, an `AgentHeartbeat` table, and a full MCP server. The pieces exist; what's missing is a self-registration contract.

## Goals / Non-Goals

**Goals:**
- Any MCP-capable agent can join a Hub session using only the Hub URL and project API key
- Registration is idempotent — safe to call on every startup and after `/compact`
- Existing Claude and Kimi paths are completely unchanged
- Phase 1 delivers `poll` contact mode only (agent manages its own inbox polling)
- Hub dashboard shows self-registered agents alongside configured ones

**Non-Goals:**
- `mcp-push` and `watchdog-spawn` contact modes (Phase 2)
- Capability declaration and task routing by capability (Phase 3)
- Per-agent access tokens or session-scoped registration tokens (Phase 3)
- Changes to `agentweave.yml`, `config.py`, `session.py`, or any existing MCP tools
- Supporting self-registration on local or git transports (Hub/HTTP only)

## Decisions

### Decision 1: No per-agent token — project API key is the security boundary

**Chosen:** All MCP calls authenticate with the project API key (`Authorization: Bearer aw_live_xxx`). Agent identity is the `name` field passed in each call, same as today.

**Rejected:** Per-agent token issued at registration. Problem: AI agents compact their context window, losing the token. Solutions (env var, file on disk) add friction that defeats the simplicity goal. Per-agent tokens also provide no meaningful additional security since all agents in a session share the same project and are already mutually trusted.

### Decision 2: Idempotent registration — no "first call wins" locking

**Chosen:** `register_agent()` always succeeds for a valid name + API key. If the agent is already registered, it updates `last_seen` and returns the same role and context. Re-registering after compaction is the designed recovery path.

**Rejected:** One-time registration with a conflict error on re-register. This would require the agent to persist a "registered" flag across compaction, which brings back the token problem.

### Decision 3: Self-registered agents stored in Hub DB only, not in agentweave.yml

**Chosen:** Four new nullable columns on the existing `Agent` table: `contact_mode`, `self_registered` (bool), `mcp_endpoint`, `spawn_cmd`. No new table needed. Self-registered agents are ephemeral — they exist while the Hub is running and the agent is active.

**Rejected:** Writing self-registered agents back to `agentweave.yml`. That file is committed to git and represents the intentional, static team configuration. Mixing runtime registrations into it would create noise and potential conflicts.

### Decision 4: `get_context()` returns role guide content as a string

**Chosen:** `get_context(role)` reads the role template file from disk (`templates/roles/<role>.md`) and returns the content as a string in the MCP response. Agent receives it inline, no filesystem access needed.

**Rejected:** Returning a URL or file path for the agent to fetch separately. Agents running remotely (different machines, containers) may not have access to the AgentWeave filesystem.

### Decision 5: Poll mode only in Phase 1

**Chosen:** Phase 1 only supports `contact_mode="poll"` — agent calls `get_inbox()` on its own schedule. Watchdog skips these agents entirely.

**Rationale:** Covers 100% of the immediate use case (Hermes, any long-running agent). `mcp-push` requires the Hub to act as an MCP client (calling tools on the agent's server), which is a larger architectural addition. Keeping Phase 1 narrow reduces risk to existing watchdog behavior.

## Risks / Trade-offs

**[Risk] Self-registered agent name collides with a configured agent** → Mitigation: `register_agent()` rejects names already present in the session's configured agent list. Returns a clear error: "Agent name 'claude' is reserved for a configured agent."

**[Risk] Stale registrations accumulate if agents crash without deregistering** → Mitigation: Phase 1 accepts this — registrations are cheap metadata rows. Phase 2 adds `deregister_agent()` and TTL-based cleanup from heartbeat age.

**[Risk] `get_context()` returns stale content if role templates change mid-session** → Mitigation: Acceptable for Phase 1. Agent can call `get_context()` again at any time to refresh. Phase 2 can add a `version` field.

**[Risk] Hub-only feature creates inconsistency (local/git transport doesn't support it)** → Mitigation: `register_agent()` returns a clear error when called against a non-HTTP transport. The feature is scoped to Hub from the start.

## Migration Plan

1. Add Alembic migration for four new columns on `Agent` table (all nullable, no default required for existing rows).
2. Deploy updated Hub Docker image — migration runs on startup.
3. Deploy updated CLI with new MCP tools — additive, no breaking changes.
4. Existing sessions continue working unchanged; self-registration is opt-in by new agents.

**Rollback:** Remove the three new MCP tools and revert the migration. No data loss risk since the new columns are additive and nullable.

## Open Questions

- Should the Hub emit an SSE event (`agent_registered`) when a new agent self-registers, so the UI updates in real time without polling? (Likely yes — follows existing SSE patterns for tasks/messages.)
- What role should be assigned when `role_request` is omitted and the session has no obvious default? Current thinking: assign `"collaborator"` as the default session role.
