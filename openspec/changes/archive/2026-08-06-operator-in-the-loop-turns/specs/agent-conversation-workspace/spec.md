## ADDED Requirements

### Requirement: A pending request is answerable where the agent asked it

A question or approval an agent is waiting on SHALL appear in the conversation it arose from, in
sequence with the rest of that turn's work, and SHALL be answerable there.

The operator MUST NOT be required to leave the conversation to answer it. Existing places that list
outstanding questions remain valid and are not replaced.

While a request is pending, the conversation SHALL make clear that the agent is waiting on the
operator rather than working — waiting on a person and working are different states and MUST NOT
look the same.

Once resolved, the request and its resolution SHALL remain in the conversation as part of that
turn's record.

#### Scenario: A pending question appears in its conversation

- **WHEN** an agent asks a waiting question during a turn
- **THEN** it appears in that conversation in sequence with the turn's other work
- **AND** can be answered without leaving the conversation

#### Scenario: Waiting is distinguishable from working

- **WHEN** an agent is waiting on the operator
- **THEN** the conversation shows it as waiting on the operator
- **AND** does not present it as still working

#### Scenario: The resolution stays in the record

- **WHEN** a pending request has been answered
- **THEN** the request and the answer remain visible in the conversation

#### Scenario: Existing question surfaces still work

- **WHEN** an outstanding question exists
- **THEN** it also remains visible where outstanding questions are already listed

### Requirement: A running turn can be redirected without being destroyed

Where a provider supports it, the operator SHALL be able to send further direction to a turn that is
already running, and SHALL be able to stop one, from the conversation.

Redirecting a turn MUST NOT discard the work it has already done. Stopping a turn SHALL leave its
work so far in the record rather than removing it.

Both actions SHALL be recorded as operator actions on the run's timeline.

Where a provider does not support redirection, the interface MUST NOT offer it. It MUST NOT offer an
action that will not work.

#### Scenario: A running turn accepts further direction

- **WHEN** the operator sends direction to a running turn on a provider that supports it
- **THEN** the turn receives it and continues
- **AND** the work already done is not discarded

#### Scenario: Stopping preserves what happened

- **WHEN** the operator stops a running turn
- **THEN** the turn ends
- **AND** the work it had already done remains in the record

#### Scenario: Operator intervention is recorded

- **WHEN** the operator redirects or stops a running turn
- **THEN** the action is recorded on the run's timeline as an operator action

#### Scenario: Unsupported redirection is not offered

- **WHEN** the running turn's provider does not support redirection
- **THEN** the interface does not offer it
