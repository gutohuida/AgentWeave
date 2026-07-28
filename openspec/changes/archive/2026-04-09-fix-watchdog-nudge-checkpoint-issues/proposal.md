## Why

Three minor bugs introduced by Kimi's multi-session fix produce noisy or non-functional behavior in the watchdog and Hub UI: agents receive nudge messages referencing a command that doesn't exist, the Mission Control checkpoint warning fires permanently in Docker, and stale messages from before watchdog startup trigger spurious nudges on restart.

## What Changes

- Replace the nonexistent `/aw-checkpoint token_threshold` command reference in nudge messages with the real MCP tool call (`save_checkpoint`)
- Remove the filesystem-based `last_checkpoint_at` lookup from the Hub API — the Hub runs in Docker and can never read the host filesystem, so the field is always `None` and the UI permanently shows a `⚠ No checkpoint` warning
- Skip nudge counter increments during the initial message scan at watchdog startup so pre-existing messages don't trigger nudges immediately on restart

## Capabilities

### New Capabilities
<!-- None — these are all bug fixes with no new spec-level behavior -->

### Modified Capabilities
<!-- No spec-level requirement changes — implementation fixes only -->

## Impact

- `src/agentweave/watchdog.py`: nudge message text; skip `_on_new_message_for_agent` during `_process_messages_since_start` initial scan
- `hub/hub/api/v1/agents.py`: remove `last_checkpoint_at` filesystem lookup block
- `hub/hub/schemas/agents.py`: remove `last_checkpoint_at` field
- `hub/ui/src/api/agents.ts`: remove `last_checkpoint_at` field from `AgentSummary`
- `hub/ui/src/components/agents/MissionControlPage.tsx`: remove checkpoint warning section from `MissionCard`
