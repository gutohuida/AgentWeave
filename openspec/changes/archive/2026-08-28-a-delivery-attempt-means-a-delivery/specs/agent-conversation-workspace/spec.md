# agent-conversation-workspace — delta

## ADDED Requirements

### Requirement: A delivery attempt is counted only where a delivery was attempted

The system SHALL NOT count a delivery attempt against queued input where nothing was delivered and
the reason nothing was delivered prevents the agent from running at all.

Input refused for a reason that prevents the agent from running **at all** SHALL NOT have a delivery
attempt counted against it, and SHALL NOT be given up on for that reason. No delivery was attempted:
the refusal was raised before anything carried it anywhere, and while the reason holds no other
input for that agent could have run in its place either, so giving up on this input buys nothing.
Counting it means the operator's own activity — sending another message, or asking the system to
start the work already waiting — consumes the allowance that exists to detect repeated failure, and
destroys input that nothing ever tried to deliver.

This SHALL NOT extend to a refusal that prevents only this input from being delivered. Where other
queued input could have run, the input at the head of the queue is in the way, and the system SHALL
go on counting its attempts and SHALL still give up on it at the limit.

Where the system gives up on input, the reason it records SHALL describe what actually happened to
that input. Input that was never carried anywhere has not failed to be delivered.

#### Scenario: Sending more input does not consume the earlier input's allowance

- **WHEN** an operator submits input to an agent whose environment is not ready
- **AND** the operator submits further input to the same agent
- **THEN** no delivery attempt is counted against the earlier input
- **AND** the earlier input remains queued

#### Scenario: The input is still there when the agent becomes able to run

- **WHEN** input has been waiting for an agent that cannot run at all
- **AND** the operator has submitted further input and asked the system to start the waiting work
- **AND** the operator then makes the agent able to run
- **THEN** every input they submitted is delivered
- **AND** none of it was discarded while they were making the agent able to run

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

#### Scenario: A refusal that blocks only this input still counts

- **WHEN** a turn is refused for a reason that would not prevent the agent's other queued input from
  being delivered
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it, so it cannot hold the queue indefinitely
