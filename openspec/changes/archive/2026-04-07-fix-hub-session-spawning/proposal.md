## Why

When users send messages to agents via the Hub UI, three separate bugs compound to create a new Claude/Kimi session for every message instead of resuming the existing one — causing an ever-growing list of sessions and broken conversation continuity.

## What Changes

- **Hub UI** (`AgentPromptPanel.tsx`): Disable the send button while session data is loading, preventing messages from being sent in the default `'new'` mode before the auto-select effect fires.
- **Hub backend** (`agent_trigger.py`): When `session_mode == 'new'`, append a `[NewSession]` marker to the message content so the watchdog can distinguish an explicit new-session request from the absence of a tag.
- **Watchdog** (`watchdog.py`): In `_make_direct_trigger_callback`, fall back to `_load_agent_session(recipient)` when neither `[Session: ...]` nor `[NewSession]` is present in the message — matching the existing behavior of the ping callback. Parse `[NewSession]` as an explicit override to create a fresh session.
- **Watchdog** (`watchdog.py`): Persist triggered direct-trigger message IDs to `.agentweave/triggered_direct.json` so the `seen` set survives watchdog restarts, preventing re-triggers of unread messages.

## Capabilities

### New Capabilities

- `direct-trigger-session-continuity`: Hub UI direct triggers resume the agent's existing session by default, only starting a new session when explicitly requested or when no prior session exists.
- `watchdog-trigger-persistence`: Triggered direct-trigger message IDs are persisted to disk so watchdog restarts do not re-execute already-processed messages.

### Modified Capabilities

<!-- No existing spec-level requirements are changing -->

## Impact

- `hub/ui/src/components/agents/AgentPromptPanel.tsx` — send button disabled while sessions loading
- `hub/hub/api/v1/agent_trigger.py` — `[NewSession]` marker added to message content for `session_mode == 'new'`
- `src/agentweave/watchdog.py` — direct trigger callback updated (session fallback + `[NewSession]` parsing + persistent seen set)
- No API contract changes, no DB schema changes, no breaking changes
- Affects: Hub UI, watchdog process, kimi and claude_proxy agents
