## Context

AgentWeave's Hub UI sends messages to agents via `POST /api/v1/agent/trigger`. The watchdog on the host picks these up as "direct trigger" messages and spawns the agent CLI. Three independent bugs cause a new session to be created per message rather than resuming the existing one:

1. **UI timing**: `AgentPromptPanel` initializes with `sessionMode = 'new'`; an async `useEffect` switches it to `'resume'` once sessions load. Messages sent during the loading window create unnecessary new sessions.
2. **Watchdog ignores saved session**: `_make_direct_trigger_callback` sets `session_id = None` unconditionally when no `[Session:...]` tag is in the message — unlike `_make_ping_callback` which always calls `_load_agent_session(recipient)`.
3. **In-memory `seen` set**: The deduplication set lives only in the watchdog process. On restart, all unread direct-trigger messages are re-processed, each creating a new session.

## Goals / Non-Goals

**Goals:**
- Hub UI direct triggers resume the agent's saved session by default
- Explicit "New Session" requests from the UI are honored
- Watchdog restart does not re-execute already-triggered messages
- No DB schema changes, no new HTTP endpoints, no breaking API changes

**Non-Goals:**
- Changing agent-to-agent session management (ping callback is already correct)
- Handling session expiry differently (existing stale-session retry at lines 1022–1047 is sufficient)
- Solving session extraction failures (kimi regex miss is a separate reliability concern)

## Decisions

### Decision 1: `[NewSession]` marker in message content (not a new field)

The Hub message `content` field is already used to carry `[Session: <id>]` tags. Adding `[NewSession]` follows the same pattern and requires no DB schema migration, no new API parameters, and no changes to the Hub SSE broadcast or message schema.

**Alternative considered**: Add a `force_new_session` boolean to the `Message` DB model and a new API field. Rejected — requires a DB migration and changes to the Hub API contract, for a simple boolean flag.

### Decision 2: Disk file for persistent `seen` set (`.agentweave/triggered_direct.json`)

Store triggered message IDs as a JSON object `{msg_id: iso_timestamp}` on disk. On watchdog startup, load IDs from the last 24 hours into the in-memory `seen` set. After spawning, append the new ID. This mirrors how `_save_agent_session` already persists data in `.agentweave/agents/`.

**Alternative considered**: Mark the `Message.read = True` in the Hub DB immediately after triggering. Rejected — the message must stay unread so the agent can retrieve it via `get_inbox`. Making it read would silently hide it from the agent.

**Alternative considered**: Timestamp-based filter (skip messages older than N minutes). Rejected — heuristic that breaks on slow systems or long-running agents.

### Decision 3: UI — disable send while sessions loading (not change default state)

Keep `sessionMode`'s initial value tied to sessions data: if `isLoadingSessions`, disable the send button. This is the minimal change — no UX restructuring, no state machine refactor. The existing auto-select `useEffect` continues to work exactly as before once data arrives.

**Alternative considered**: Default to `'resume'` immediately and show a spinner. More complex — requires handling the case where sessions is empty after load.

## Risks / Trade-offs

- **Disk file race**: If watchdog crashes between spawning and writing to `triggered_direct.json`, the message is re-triggered on restart. This is acceptable — same as the current behavior for all messages, and the file write happens synchronously immediately after spawning the thread.
- **`[NewSession]` parsing coupled between Hub and watchdog**: If Hub is updated but watchdog is not (or vice versa), old watchdog would see no `[NewSession]` tag and fall back to the saved session instead of creating a new one. This is a graceful degradation (resumes instead of spawning new), not a hard failure.
- **Old unread messages from pre-fix Hub**: On first watchdog restart after deploying, messages created before the fix have no `[NewSession]` tag and no `[Session:...]` tag. The new watchdog would fall back to saved session for these. Low risk — they are likely stale messages.

## Migration Plan

1. Deploy Hub (Docker rebuild) — adds `[NewSession]` marker to new messages
2. Restart watchdog — picks up new parsing logic and loads `triggered_direct.json` if present
3. No rollback complexity — reverting either side degrades gracefully (session resume instead of new, or re-trigger on restart)

## Open Questions

- Should `triggered_direct.json` be added to `.gitignore`? (Yes — same as `agents/`, `messages/`, `tasks/` — should not be committed.)
