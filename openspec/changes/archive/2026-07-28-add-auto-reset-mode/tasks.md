## 1. Configuration

- [ ] 1.1 Add `auto_reset: bool` and `reset_threshold: int` to the per-agent
  configuration schema (in `agentweave.yml`).
- [ ] 1.2 Document both keys with defaults (`auto_reset=false`,
  `reset_threshold=70`).

## 2. Watchdog: auto-reset path

- [ ] 2.1 When `auto_reset` is true for an agent and the agent's reported
  context crosses `reset_threshold`, the watchdog SHALL send a reset
  instruction to the agent instead of writing `compact_decision.md`.
- [ ] 2.2 The watchdog SHALL start a grace timer when it sends the reset
  instruction. Grace duration SHALL come from the Blocker 1 findings
  document for the agent's runner.

## 3. Watchdog: force-kill path

- [ ] 3.1 If the agent does not begin a clean exit within the grace
  window, the watchdog SHALL send SIGTERM.
- [ ] 3.2 If SIGTERM does not produce an exit within a second short grace,
  the watchdog SHALL send SIGKILL.
- [ ] 3.3 After SIGKILL, the watchdog SHALL verify the worktree is
  recoverable (no uncommitted changes to tracked files the agent was
  actively editing).
- [ ] 3.4 The watchdog SHALL record the forced reset as an event on the
  Hub with the reason and the recovery verification outcome.

## 4. Agent: checkpoint handoff

- [ ] 4.1 When the agent receives a "please reset" instruction, it SHALL
  write a checkpoint file to
  `.agentweave/shared/checkpoints/<agent>-<timestamp>.md` containing
  current task, branch, files modified, what is done, what is next,
  open questions, and verification commands.
- [ ] 4.2 The agent SHALL exit the session cleanly after writing the
  checkpoint.
- [ ] 4.3 The next session for the same agent SHALL read the most recent
  checkpoint file for its agent as its first action and SHALL
  incorporate the checkpoint contents into its context before proceeding.

## 5. Tests

- [ ] 5.1 Per-runner cooperative reset test: simulate the agent
  receiving the reset instruction, writing a checkpoint, and exiting.
  Assert the next session reads the checkpoint first.
- [ ] 5.2 Per-runner force-kill test: simulate the agent ignoring the
  reset instruction. Assert the watchdog SIGTERMs and SIGKILLs within
  the documented grace windows and that the worktree is recoverable.
- [ ] 5.3 Test that auto-reset is NOT triggered when `auto_reset` is
  false for the agent.
- [ ] 5.4 Test that `reset_threshold` below 50 is rejected at config load
  time (sanity bound).

## 6. Documentation

- [ ] 6.1 Update `AGENTS.md` and the operator guide to describe the
  auto-reset mode, the configuration keys, and the expected checkpoint
  format.
- [ ] 6.2 Document the per-runner grace windows from the Blocker 1
  findings so operators can tune them.