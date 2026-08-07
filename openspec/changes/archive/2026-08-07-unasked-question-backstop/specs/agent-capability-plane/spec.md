## ADDED Requirements

### Requirement: A turn that ends on an unasked question is surfaced to the operator

The system SHALL durably record, and show the operator, any run that completes having produced a
trailing question without opening a question of record.

An agent that ends a turn on an unanswered question has stopped working and is waiting for an answer
that cannot arrive, because nothing was ever asked. From the operator's side this is
indistinguishable from a completed turn. Detection is the only available remedy: no provider
protocol permits requiring that a turn end through a particular tool.

#### Scenario: A completed run ends in a question and opened no question row

- **WHEN** a run completes, its final assistant text ends in a question, and the run opened no
  question of record
- **THEN** a pending record of the unasked question is stored, carrying the agent, the run, the
  conversation and the question text
- **AND** an event is broadcast so the operator's view updates without a reload

#### Scenario: The run asked properly

- **WHEN** a run completes having opened a question of record
- **THEN** no unasked-question record is created, regardless of how its final text ends

#### Scenario: The run did not end in a question

- **WHEN** a run completes and its final assistant text does not end in a question
- **THEN** no unasked-question record is created

#### Scenario: The turn is about to continue

- **WHEN** a run completes ending in a question and the agent still has queued input
- **THEN** no unasked-question record is created, because the next turn starts on its own

#### Scenario: The run did not complete

- **WHEN** a run ends in any status other than completed
- **THEN** no unasked-question record is created

### Requirement: The operator can convert an unasked question into a real one

The system SHALL offer the operator, for each pending unasked question, an action that re-prompts the
agent to ask that same question through the question tool, and an action that dismisses it.

Answering the detected question directly is not possible: the turn has ended and no tool call is
waiting on a value. Re-prompting is the only action that restores the intended flow.

#### Scenario: The operator re-prompts the agent

- **WHEN** the operator chooses to have the question asked properly
- **THEN** the record moves out of pending
- **AND** the agent is triggered with an instruction naming that question and requiring it be asked
  through the question tool with its required structure

#### Scenario: The operator dismisses it

- **WHEN** the operator dismisses a pending unasked question
- **THEN** the record moves out of pending and the operator is not shown it again

#### Scenario: A record is acted on twice

- **WHEN** an action is taken on a record that is no longer pending
- **THEN** the request is refused rather than silently repeated

### Requirement: Operator-facing severity values are the ones the operator's view understands

Events persisted for the operator's attention SHALL use the severity vocabulary the operator's views
filter and style by.

A severity that no view recognises is worse than none: the row renders unmarked and is hidden by the
filter intended to reveal it, so the events most needing attention are the ones least likely to be
seen.

#### Scenario: A refused action is recorded

- **WHEN** the system records that an agent's action was refused
- **THEN** the stored severity is one the operator's activity view filters and styles by
