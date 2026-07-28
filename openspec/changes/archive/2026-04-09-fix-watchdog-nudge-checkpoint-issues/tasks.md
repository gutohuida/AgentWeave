## 1. Fix nudge message command reference

- [x] 1.1 In `src/agentweave/watchdog.py`, update `_send_checkpoint_nudge` message body: replace `/aw-checkpoint token_threshold` with `save_checkpoint` (the MCP tool name)

## 2. Remove last_checkpoint_at from Hub API and schema

- [x] 2.1 In `hub/hub/api/v1/agents.py`, remove the `last_checkpoint_at` filesystem lookup block (the `try` block that reads `.agentweave/shared/checkpoints/`)
- [x] 2.2 Remove the `last_checkpoint_at=last_checkpoint_at` kwarg from the `AgentSummary(...)` constructor call in the same file
- [x] 2.3 In `hub/hub/schemas/agents.py`, remove the `last_checkpoint_at: Optional[datetime] = None` field from `AgentSummary`
- [x] 2.4 In `hub/ui/src/api/agents.ts`, remove the `last_checkpoint_at?: string` field from the `AgentSummary` interface
- [x] 2.5 In `hub/ui/src/components/agents/MissionControlPage.tsx`, remove the checkpoint warning section (the `<div>` with the `save` icon and `⚠ No checkpoint` display) from `MissionCard`

## 3. Suppress nudge increments during startup scan

- [x] 3.1 In `src/agentweave/watchdog.py`, find `_process_messages_since_start` (the startup scan method) and remove or guard the `_on_new_message_for_agent` calls so pre-existing messages do not increment the nudge counter
