## ADDED Requirements

### Requirement: A firing that starts no agent SHALL NOT be reported as running

The Hub SHALL NOT report a firing as in progress once it is known that no agent was started for it.
Where a firing queues its input but the turn does not begin, the firing's record SHALL reach a
terminal state carrying the stated reason, without waiting for any later sweep.

This was measured on 2026-08-21: a firing whose agent had no runner bound left its record at
`in_progress` and the loop reported itself as firing continuously, with nothing behind it. The reason
existed at the moment it happened and was discarded.

#### Scenario: A firing whose agent cannot start is not reported as running

- **GIVEN** a loop whose agent cannot be started
- **WHEN** its job fires
- **THEN** the firing's record does not remain in an in-progress state
- **AND** the loop is not reported as firing

#### Scenario: The reason the turn did not begin is preserved

- **WHEN** a firing queues its input and the turn does not begin
- **THEN** the firing's record carries the stated reason it did not begin
- **AND** that reason is the one the queue itself would give for the same agent

#### Scenario: A firing that does start is unaffected

- **WHEN** a firing queues its input and the agent's turn begins
- **THEN** the firing is reported as in progress exactly as before
- **AND** its record reaches its terminal state when the agent's run ends

### Requirement: A stranded firing SHALL be recoverable without restarting the Hub

The Hub SHALL clear firings left in progress with no live run behind them without requiring a
restart. A restart SHALL remain sufficient, but SHALL NOT be necessary.

An unattended loop is the case this exists for, and it is the case where nobody restarts anything.
Before this, a stranded firing was reconciled only at Hub start, so the loop card stayed wrong for as
long as the Hub stayed up.

#### Scenario: A stranded firing is cleared while the Hub keeps running

- **GIVEN** a firing recorded as in progress with no live run behind it
- **WHEN** the Hub continues running without being restarted
- **THEN** that firing is eventually recorded as failed
- **AND** the loop stops being reported as firing

#### Scenario: A live firing is never cleared out from under itself

- **GIVEN** a firing whose run is still running
- **WHEN** the Hub clears stranded firings
- **THEN** that firing is left alone

### Requirement: A refused firing SHALL leave no artefact implying work happened

A firing refused before any agent is briefed SHALL NOT create a conversation. A refused firing
already leaves no claim, queues no input, and changes no task; a conversation is the remaining
artefact that implies otherwise.

Measured 2026-08-21: five firings produced five conversations and three of those firings were
refused, each leaving a thread named after the job with nothing in it. On a five-minute schedule a
stalled loop produces twelve an hour, none distinguishable by name from a real one until opened.

#### Scenario: A firing refused by the stall condition creates no conversation

- **GIVEN** a loop whose queue is stalled
- **WHEN** its job fires and the firing is refused
- **THEN** no conversation is created for that firing

#### Scenario: A firing refused by the stop condition creates no conversation

- **GIVEN** a loop past its stop time
- **WHEN** its job fires and the firing is refused
- **THEN** no conversation is created for that firing

#### Scenario: A firing that proceeds still gets its conversation

- **WHEN** a firing is not refused and briefs an agent
- **THEN** a conversation is created and named after the job, as before
