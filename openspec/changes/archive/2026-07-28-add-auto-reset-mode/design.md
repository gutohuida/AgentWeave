## Context

The Blocker 1 findings from `investigate-blockers` document what happens when a watchdog-issued reset instruction is delivered to a busy agent at high context, including the cooperative path (agent writes a checkpoint and exits) and the uncooperative path (agent ignores the instruction, watchdog force-kills). This change implements a safe auto-reset mode that the watchdog can apply without requiring a human in the loop.

The exact grace windows come from the findings, so the implementation agent fills in the specific numbers after the user approves the findings.

## Goals / Non-Goals

**Goals:**

- Add `auto_reset` and `reset_threshold` configuration on each agent in `agentweave.yml`.
- Implement the watchdog's auto-reset path: send reset instruction, start grace timer, SIGTERM, SIGKILL, verify worktree recovery.
- Implement the agent-side checkpoint handoff: write a checkpoint file under `.agentweave/shared/checkpoints/`, exit cleanly.
- Implement the next-session flow: read the most recent checkpoint as the first action.

**Non-Goals:**

- Touch the watchdog's retry behaviour (that is the durable-trigger-retry change).
- Touch the context-tracking pipeline (that is the fix-context-tracking change).
- Replace `compact_decision.md` with this flow for interactive agents. Interactive agents keep the existing compact-decision flow; auto-reset is opt-in per agent.

## Decisions

### Decision: Per-agent opt-in via agentweave.yml

`auto_reset` is opt-in per agent. Interactive agents keep the existing `compact_decision.md` flow. The default is `auto_reset=false` so existing setups are not affected.

### Decision: Grace windows come from the findings, are configurable per agent

The watchdog SHALL read grace-window defaults from configuration. The defaults SHALL be the values recorded in `openspec/changes/investigate-blockers/findings/blocker-1.md` for each runner. Agents can override in `agentweave.yml` if the operator has a reason to.

### Decision: Watchdog is allowed to force-kill

The watchdog SHALL SIGTERM, wait a short grace, then SIGKILL a non-cooperating agent. This is required because autonomous mode has no human mediator. The exact grace durations come from the findings.

### Decision: Checkpoint format is canonical

The checkpoint file SHALL contain: current task, branch, files modified, what is done, what is next, open questions, verification commands. This format is referenced by the next session's first action.

## Open Questions

- The specific grace windows come from the findings.
- Whether the checkpoint is written by the agent as part of receiving the reset instruction, or by the watchdog as part of SIGTERM cleanup. Default: agent writes it; watchdog verifies the file exists after kill.