## Context

Kimi's multi-session fix introduced three minor bugs:
1. Watchdog nudge messages reference `/aw-checkpoint token_threshold`, a skill that does not exist.
2. The Hub API attempts to read checkpoint files from the local filesystem (`.agentweave/shared/checkpoints/`), but the Hub runs in Docker without host filesystem access — so `last_checkpoint_at` is always `None`, and Mission Control permanently shows a `⚠ No checkpoint` warning on every agent card.
3. During watchdog startup, `_process_messages_since_start` calls `_on_new_message_for_agent` for every pre-existing message, causing nudges to fire immediately if the historical message count exceeds the threshold.

All three issues are self-contained and require no architectural changes.

## Goals / Non-Goals

**Goals:**
- Nudge messages direct agents to the correct tool (`save_checkpoint` MCP tool)
- Remove the always-failing `last_checkpoint_at` filesystem lookup and its UI display
- Suppress nudge counter increments during the initial startup scan

**Non-Goals:**
- Redesigning the checkpoint or nudge system
- Adding a working cross-container checkpoint timestamp (would require a separate Hub endpoint)
- Changing the nudge threshold or frequency

## Decisions

### Fix 1: Nudge message text
Replace `/aw-checkpoint token_threshold` with the correct MCP tool invocation. The right call is `save_checkpoint` via the AgentWeave MCP tools. The nudge message should instruct agents to call `mcp__agentweave__save_checkpoint` (or `save_checkpoint` for brevity).

### Fix 2: Remove `last_checkpoint_at` from Hub API
The filesystem lookup was added speculatively and can never work in the Docker deployment model. The correct fix is removal rather than a workaround (e.g., a Hub endpoint), because checkpoints are not yet a Hub-tracked concept. Removing the field is cleaner than leaving a permanently-`None` field and a broken UI warning.

Files to change: `agents.py` (API), `agents.py` (schema), `agents.ts` (TypeScript type), `MissionControlPage.tsx` (UI).

### Fix 3: Skip nudge increments during startup scan
`_process_messages_since_start` is an initialization method that populates `known_messages` from disk. It should not trigger behavioral side effects. The simplest fix is to not call `_on_new_message_for_agent` inside the startup scan — the counters start at zero when the watchdog starts and only increment from new messages seen during polling.

**Alternative considered**: Reset counters after the startup scan. Rejected — it's simpler and more correct to never increment during the scan in the first place.

## Risks / Trade-offs

- Removing `last_checkpoint_at` is a minor breaking change to the Hub API schema — any external consumer relying on this field (unlikely given it was always `None`) would need updating. Risk is negligible.
- Fix 3 means message counts reset on watchdog restart. This is acceptable — nudges are meant to prompt in-session checkpointing, and a restart is a natural session boundary.

## Migration Plan

No migrations needed. Changes are additive removals with no state side effects.
