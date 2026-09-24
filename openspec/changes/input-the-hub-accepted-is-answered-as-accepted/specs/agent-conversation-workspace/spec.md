## ADDED Requirements

### Requirement: Input the system has accepted is answered as accepted, and a failure to start it is retried

A request whose input the system has durably queued SHALL be answered as accepted, whatever fails after the input was queued other than the withdrawal of input the system has refused, and the system SHALL itself retry starting a turn for input it could not start for a reason that can clear on its own, without waiting for an unrelated action.

Once input is queued, it will be delivered. Answering such a request as a failure tells the operator
their input was lost when it was not, and invites them to send it again, so the agent receives it
twice. The answer SHALL say that the input was accepted and, where no turn started with it, what it
is waiting for.

Accepting input is only honest if something will start it. Where the system tried to start a turn
for accepted input and could not, for a reason that can clear on its own (a busy or locked store),
it SHALL try again on its own, and SHALL NOT leave the input waiting until the operator opens a
project, saves a setting, or another run ends.

A failure that will not clear on its own SHALL NOT be retried. It SHALL be recorded once, the input
SHALL stay queued, and the answer SHALL NOT promise a retry.

A failure to record that the input arrived, as an event, SHALL NOT change the answer, because the
input itself was queued.

The same holds for input a loop, flow or job firing queues: once that input is queued, a failure to
start its turn that can clear on its own SHALL leave the firing in progress, not failed, and SHALL be
retried as above.

This does not change what is answered for input that is refused for what it asked; that is answered
as a refusal, as before. **Exception:** where the input was refused and withdrawing it from the queue
then fails, the request is answered as a server error, as before. The caller is owed the refusal,
and the input stays queued, where the next attempt refuses it again.

#### Scenario: Starting the turn fails after the input was queued

- **WHEN** an operator submits input to an agent
- **AND** the input is queued
- **AND** the attempt to start a turn with it fails for a reason that can clear on its own
- **THEN** the request is answered as accepted
- **AND** the answer states that the system could not start a turn yet and will try again
- **AND** the answer identifies the queued input

#### Scenario: The system retries on its own

- **WHEN** an attempt to start a turn for accepted input has failed for a reason that can clear on its own
- **AND** the condition that caused it clears
- **THEN** a turn starts with that input without any further request from the operator

#### Scenario: A failure that will not clear is not retried

- **WHEN** the attempt to start a turn for accepted input fails for a reason that will not clear on its own
- **THEN** the request is answered as accepted
- **AND** the failure is recorded once
- **AND** no retry is attempted
- **AND** the input stays queued
- **AND** the answer does not say that the system will try again

#### Scenario: A turn that started before the failure is reported as started

- **WHEN** a turn has already taken the input when the attempt to start it fails
- **THEN** the request is answered as started, identifying that turn

#### Scenario: Recording the arrival fails

- **WHEN** the input is queued and recording its arrival as an event fails
- **THEN** the request is answered exactly as it would have been had the event been recorded

#### Scenario: A firing whose turn could not start yet stays in progress

- **GIVEN** a loop, flow or job firing that has queued its input
- **WHEN** the attempt to start the turn fails for a reason that can clear on its own
- **THEN** the firing is not recorded as failed
- **AND** the system retries starting the turn
- **AND** when the condition clears, the turn starts with the firing's input

#### Scenario: A withdrawal that fails after a refusal is still a server error

- **WHEN** input is queued and then refused for what it asked
- **AND** withdrawing it from the queue fails
- **THEN** the request is answered as a server error
- **AND** the input stays queued
