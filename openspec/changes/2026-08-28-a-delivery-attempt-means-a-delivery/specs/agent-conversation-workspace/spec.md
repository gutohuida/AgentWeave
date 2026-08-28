# agent-conversation-workspace — delta

## ADDED Requirements

### Requirement: A delivery attempt is counted only where a delivery was attempted

The system SHALL count a delivery attempt against queued input only where that input was carried by
a run, or where the turn was refused for a reason about what the input asked for.

Input refused because the environment the agent would run in is not ready SHALL NOT have a delivery
attempt counted against it, and SHALL NOT be given up on for that reason. No delivery was attempted:
the refusal was raised before anything carried it anywhere, and the environment is agent-wide, so no
other input is waiting behind this one that could have run in its place. Counting it means the
operator's own activity — sending another message, or asking the system to start the work already
waiting — consumes the allowance that exists to detect repeated failure, and destroys input that
nothing ever tried to deliver.

Where the system gives up on input, the reason it records SHALL describe what actually happened to
that input. Input that was never carried anywhere has not failed to be delivered.

#### Scenario: Sending more input does not consume the earlier input's allowance

- **WHEN** an operator submits input to an agent whose environment is not ready
- **AND** the operator submits further input to the same agent
- **THEN** no delivery attempt is counted against the earlier input
- **AND** the earlier input remains queued

#### Scenario: Asking the system to start waiting work does not destroy it

- **WHEN** input is waiting for an agent whose environment is not ready
- **AND** the operator asks the system to start the waiting work without submitting anything new
- **THEN** no delivery attempt is counted against that input
- **AND** the input remains queued

#### Scenario: Unrelated activity does not consume it either

- **WHEN** input is waiting for an agent whose environment is not ready
- **AND** another agent's turn ends, causing every queued agent to be re-evaluated
- **THEN** no delivery attempt is counted against that input

#### Scenario: A run that carried the input and failed still counts

- **WHEN** a run carrying queued input fails
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it

#### Scenario: A refusal about what was asked still counts

- **WHEN** a turn is refused because of what the queued input asked for
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it
