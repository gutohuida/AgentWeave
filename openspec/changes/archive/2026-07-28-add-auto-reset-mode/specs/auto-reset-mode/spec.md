## ADDED Requirements

### Requirement: Agent configuration declares auto-reset behaviour

The AgentWeave session configuration SHALL allow an agent to declare that it should be auto-reset when its context usage crosses a configured threshold. The declaration SHALL include a threshold (default 70 percent) and SHALL be visible to the watchdog when deciding whether to issue a reset instruction.

#### Scenario: Agent enables auto_reset in agentweave.yml

- **WHEN** an agent's `agentweave.yml` includes `auto_reset: true` with a threshold
- **THEN** the watchdog SHALL treat that agent as auto-reset rather than interactive
- **AND** the watchdog SHALL issue a reset instruction when the agent's reported context crosses the configured threshold

#### Scenario: Reset threshold has a sane default

- **WHEN** `auto_reset: true` is set without an explicit `reset_threshold`
- **THEN** the watchdog SHALL use 70 as the default threshold

### Requirement: Watchdog forces checkpoint and reset without agent cooperation

When auto-reset is enabled for an agent and the agent's reported context crosses the configured threshold, the watchdog SHALL send a reset instruction to the agent and SHALL start a grace timer. If the agent does not begin a clean exit within the grace window, the watchdog SHALL SIGTERM the agent subprocess and, after a second short grace, SHALL SIGKILL it. The watchdog SHALL verify after kill that the agent's worktree is in a recoverable state.

#### Scenario: Cooperative agent resets cleanly

- **WHEN** an auto-reset-capable agent receives the reset instruction
- **AND** it writes a checkpoint file under `.agentweave/shared/checkpoints/<agent>-<timestamp>.md`
- **AND** it exits the session within the grace window
- **THEN** the watchdog SHALL record a successful reset
- **AND** the next session SHALL read the checkpoint as its first action

#### Scenario: Uncooperative agent is force-killed

- **WHEN** an auto-reset-capable agent receives the reset instruction
- **AND** it does not exit within the grace window
- **THEN** the watchdog SHALL SIGTERM the agent subprocess
- **AND** if the subprocess does not exit within a second short grace, the watchdog SHALL SIGKILL it
- **AND** the watchdog SHALL verify the worktree is recoverable and SHALL record the forced reset

#### Scenario: Auto-reset is not triggered when disabled

- **WHEN** an agent does not have `auto_reset: true` in its configuration
- **THEN** the watchdog SHALL NOT auto-send a reset instruction when context crosses any threshold
- **AND** the watchdog SHALL fall back to the existing `compact_decision.md` flow

### Requirement: Grace windows come from investigation findings

The grace window before SIGTERM and the short grace before SIGKILL SHALL be sourced from the Blocker 1 investigation findings for the agent's runner. The defaults SHALL be overridable per agent in `agentweave.yml`.

#### Scenario: Grace window is runner-aware

- **WHEN** the watchdog applies auto-reset to an agent
- **THEN** the grace window SHALL match the value recorded in `openspec/changes/investigate-blockers/findings/blocker-1.md` for the agent's runner
- **AND** the watchdog SHALL respect any per-agent override in `agentweave.yml`

### Requirement: Checkpoint file is the durable handoff for a new session

The agent checkpoint file written during a forced reset SHALL contain enough state for a freshly started session to resume the work: current task, branch, files modified so far, what is done, what is next, open questions, and any verification commands. The next session SHALL read the most recent checkpoint file for its agent as its first action.

#### Scenario: New session reads checkpoint first

- **WHEN** an agent starts a fresh session after a forced reset
- **AND** a checkpoint file exists for that agent under `.agentweave/shared/checkpoints/`
- **THEN** the session SHALL read the most recent checkpoint file before taking any other action
- **AND** the session SHALL treat the checkpoint contents as authoritative for "where I am"

### Requirement: Auto-reset mode is tested with each runner

The auto-reset feature SHALL include tests that exercise the cooperative path (agent writes checkpoint and exits) and the force-kill path (agent ignores instruction, watchdog kills, worktree is recoverable) for each runner the dev loop uses.

#### Scenario: Cooperative reset test exists per runner

- **WHEN** the auto-reset feature is shipped
- **THEN** a test SHALL simulate a cooperative reset for each runner and assert that a checkpoint file is written, the session ends, and the next session reads the checkpoint first

#### Scenario: Force-kill reset test exists per runner

- **WHEN** the auto-reset feature is shipped
- **THEN** a test SHALL simulate an uncooperative agent and assert that the watchdog SIGTERMs and then SIGKILLs within the documented grace windows
- **AND** the test SHALL assert that the worktree is recoverable (no lost tracked changes)