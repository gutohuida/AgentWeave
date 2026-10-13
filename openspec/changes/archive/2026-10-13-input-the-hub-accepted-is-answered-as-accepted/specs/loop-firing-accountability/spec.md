## MODIFIED Requirements

### Requirement: A firing that starts no agent SHALL NOT be reported as running

The Hub SHALL NOT report a firing as in progress once it is known that no agent will be started for it.
Where a firing queues its input and the start of its turn is refused terminally, the firing's record
SHALL reach a terminal state carrying the stated reason, without waiting for any later sweep.

This was measured on 2026-08-21: a firing whose agent had no runner bound left its record at
`in_progress` and the loop reported itself as firing continuously, with nothing behind it. The reason
existed at the moment it happened and was discarded.

A firing whose turn could not start yet, for a reason that can clear on its own (a busy or locked
store), is not such a firing: the Hub retries starting it (`agent-conversation-workspace`, *Input the
system has accepted is answered as accepted*), so it is not known that no agent will start. Its record
stays in progress. If no run is ever behind it, the Hub's clearing of stale firings records it as
failed, as for any firing left in progress with no live run behind it.

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

#### Scenario: A firing whose start failed transiently stays in progress

- **GIVEN** a firing that has queued its input
- **WHEN** the attempt to start its turn fails for a reason that can clear on its own
- **THEN** the firing's record is not recorded as failed
- **AND** it stays in progress while the Hub retries starting the turn
