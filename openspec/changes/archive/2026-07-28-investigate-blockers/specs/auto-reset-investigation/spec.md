## ADDED Requirements

### Requirement: Forced-reset behaviour is documented per runner

The investigation findings for Blocker 1 SHALL document what each supported runner does when it receives a watchdog-issued "checkpoint and start a fresh session" instruction while its context is high. The findings SHALL cover whether the agent writes a checkpoint, whether the agent exits cleanly, whether the worktree is left dirty, what happens if the agent ignores the instruction, and what grace window is appropriate before force-kill.

#### Scenario: Per-runner reset behaviour is documented

- **WHEN** the Blocker 1 findings document is reviewed
- **THEN** it SHALL record the observed behaviour for each runner the dev loop uses
- **AND** it SHALL record wall-clock times for each step of the reset path (instruction sent, agent acknowledges, agent writes checkpoint, agent exits, watchdog confirms clean exit)
- **AND** it SHALL recommend a watchdog grace window before force-kill based on the observed exit latency

#### Scenario: Force-kill behaviour is documented

- **WHEN** the Blocker 1 findings document is reviewed
- **THEN** it SHALL record what happens when the agent ignores the reset instruction and the watchdog sends SIGTERM
- **AND** it SHALL record what happens when SIGTERM is followed by SIGKILL after a short grace
- **AND** it SHALL explicitly state whether the worktree is recoverable in the force-kill case (no uncommitted changes lost from tracked files the agent was actively editing)

#### Scenario: Cooperative reset path is documented

- **WHEN** the Blocker 1 findings document is reviewed
- **THEN** it SHALL record the cooperative reset path end-to-end (agent writes checkpoint, exits cleanly, next session reads checkpoint) for at least one runner
- **AND** it SHALL recommend a default grace window for the cooperative path that gives the agent enough time to write a real checkpoint