## Why

The investigation change (`investigate-blockers`) has established what happens when a watchdog-issued reset instruction is delivered to a busy agent at high context, including what happens when the agent ignores the instruction and the watchdog force-kills it. This change implements a safe auto-reset mode that the watchdog can apply without requiring a human in the loop.

Auto-reset is required for the autonomous dev loop because agents are unreliable at noticing their own context pressure. The watchdog is the only trusted source of "we should reset" signals.

## What Changes

- Add an `auto_reset` configuration on each agent in `agentweave.yml`, with a `reset_threshold` (default 70).
- Add the watchdog path that auto-sends the reset instruction instead of writing `compact_decision.md`.
- Add the watchdog path that SIGTERMs and then SIGKILLs a non-cooperating agent after a documented grace window, and that verifies the worktree is recoverable afterward.
- Add the agent-side flow that writes a checkpoint file under `.agentweave/shared/checkpoints/<agent>-<timestamp>.md` and exits cleanly.
- Add the next-session flow that reads the most recent checkpoint as its first action.
- Add tests for the cooperative path and the force-kill path per runner.

## Capabilities

### New Capabilities

- `auto-reset-mode`: Watchdog-driven mechanism that forces an agent to checkpoint and start a fresh session when context crosses a configured threshold, including safe subprocess kill semantics and a checkpoint-based handoff to the next session.

### Modified Capabilities

None.

## Impact

- CLI: configuration key on each agent; new or modified skills for the checkpoint handoff.
- Watchdog: new code path that replaces `compact_decision.md` when `auto_reset: true` is set; new subprocess-kill logic with grace windows per the investigation findings.
- Hub: probably no schema changes; possibly a new event type for forced resets.
- Tests: per-runner tests for both cooperative and force-kill paths.
- Depends on: `investigate-blockers` being shipped (grace windows come from the findings).