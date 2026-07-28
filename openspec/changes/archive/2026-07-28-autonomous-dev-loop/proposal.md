## Why

The three blockers have been investigated (`investigate-blockers`) and fixed (`fix-context-tracking`, `add-auto-reset-mode`, `add-durable-trigger-retry`). The substrate is ready for a near-continuous development loop on the AgentWeave repo using three agents — opencode, kimi, and codex — coordinated through a second Hub on port 8001.

The user wants the agents to research, design, implement, review, and document changes to the AgentWeave repo on feature branches while the user only handles topic selection and the final merge to `main`. The loop must be pausable for the night and resumable the next day with a single command.

## What Changes

- Stand up a dev Hub on port 8001 with its own database, separate from the interactive Hub on port 8000.
- Give each of opencode, kimi, codex a git worktree on a long-lived agent branch and a long-lived CLI session pointing at the dev Hub.
- Define the `autonomous_dev` role and assign it to each agent.
- Schedule the kickoff jobs and the steady-state jobs on a staggered cron.
- Implement the kickoff message template that briefs every wake.
- Implement the Hub task templates for implementation, peer review, research proposal, and escalation.
- Implement the reviewer-assignment rule (round-robin among agents that did not author).
- Write the operator runbook.

## Capabilities

### New Capabilities

- `three-agent-dev-loop`: The runtime loop itself — per-agent worktrees, long-lived CLI sessions, staggered scheduled jobs, Hub task coordination, idle→research→propose→user-pick→deep-dive flow, two-of-three consensus with third-agent tie-break, strict peer review, and night-mode pause/resume.

### Modified Capabilities

None.

## Impact

- CLI: configuration key for `auto_reset`, kickoff message template, methodology-focused `autonomous_dev` role guide.
- Hub: separate dev Hub instance, possibly Hub task templates surfaced in the UI.
- Hub UI: nothing new beyond what the three blocker fixes ship; possibly a brief "loop health" indicator on the dev Hub dashboard.
- Tests: integration test for a single topic's full lifecycle (research → user-pick → branch → implementation → review → approval → ready for human merge).
- Docs: operator runbook, updated `AGENTS.md` with the ground rules.
- Depends on: `fix-context-tracking`, `add-auto-reset-mode`, and `add-durable-trigger-retry` being shipped.