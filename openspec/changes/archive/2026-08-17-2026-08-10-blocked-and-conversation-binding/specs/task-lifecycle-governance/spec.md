# Task lifecycle governance — deltas

## ADDED Requirements

### Requirement: A task can be waiting on a person

The system SHALL provide a status meaning that work began and cannot proceed until someone outside
the run supplies something. A task in that status SHALL be reachable only from the status meaning
work is under way, so that a task nobody has started is never described as waiting.

The status SHALL NOT have a direct edge to any status meaning the work is finished. Work that was
waiting and is now done SHALL pass back through the in-progress status first, so that no recorded
history states a task was completed while still waiting on a person who never answered.

#### Scenario: Work under way can become waiting

- **WHEN** a task whose work is under way is moved to the waiting status
- **THEN** the transition is accepted and recorded

#### Scenario: Work not yet started cannot be waiting

- **WHEN** a task that has not been started is moved to the waiting status
- **THEN** the move is refused as illegal
- **AND** the refusal names what is reachable instead

#### Scenario: A waiting task cannot be completed directly

- **WHEN** a task in the waiting status is moved directly to completed
- **THEN** the move is refused
- **AND** the task must return to the in-progress status first

#### Scenario: Waiting work can be redirected or abandoned

- **WHEN** the operator reassigns or rejects a task that is waiting
- **THEN** the transition is accepted

### Requirement: A task is recorded as waiting because the system observed it

The system SHALL move a task into the waiting status as a consequence of observing that the run
working on it ended with an unanswered question outstanding, attributed to that run and recorded as
system-caused.

The system SHALL move it back out when that question is answered.

A task SHALL NOT enter or leave the waiting status because an agent asserted that it should. An
agent that could declare itself blocked could claim to be waiting on a person it never asked, which
is the one claim a completion gate would most reward.

#### Scenario: A run that ends with a question outstanding leaves its task waiting

- **WHEN** a run bound to a task ends
- **AND** a blocking question it asked has not been answered
- **THEN** the task is recorded as waiting
- **AND** the transition names the run and is recorded as system-caused

#### Scenario: Answering releases the task

- **WHEN** the question that caused a task to be recorded as waiting is answered
- **THEN** the task returns to the in-progress status
- **AND** the transition is recorded

#### Scenario: An agent cannot declare itself waiting

- **WHEN** an agent requests the waiting status for its own task
- **THEN** the request is refused

#### Scenario: The operator may block and release directly

- **WHEN** the operator moves a task into or out of the waiting status
- **THEN** the transition is accepted and recorded as an operator action

### Requirement: A waiting task names what it is waiting for

A task in the waiting status SHALL carry a human-readable statement of what it is waiting for. Where
the system recorded the block, that statement SHALL be derived from the question asked. Where the
operator sets it directly, the system SHALL require the statement and SHALL refuse the transition
without one.

The statement SHALL be cleared whenever the task leaves the waiting status, by any route.

A status alone leaves the operator working out what they are holding up, which is the position they
were already in when the task said work was under way and nothing was happening. The status answers
"why is nothing moving"; only the statement answers "what do you need from me".

#### Scenario: A system-recorded block explains itself

- **WHEN** a run ends with an unanswered question and its task is recorded as waiting
- **THEN** the task states what it is waiting for
- **AND** that statement identifies the question asked

#### Scenario: An operator block without a statement is refused

- **WHEN** the operator moves a task to the waiting status without saying what it is waiting for
- **THEN** the transition is refused
- **AND** the task is unchanged

#### Scenario: Leaving the waiting status clears the statement

- **WHEN** a waiting task moves to any other status
- **THEN** it no longer states what it is waiting for

#### Scenario: A control offering the waiting status collects the statement

- **WHEN** an operator surface offers a move to the waiting status
- **THEN** it obtains the statement before requesting the move

### Requirement: Only an unanswered blocking question makes a task wait

The system SHALL record a task as waiting only on account of a question that is unanswered, marked
as blocking, and asked by the run whose end is being evaluated.

A question that does not block is the agent leaving a note and continuing; a task parked on one would
make the status mean that an agent mentioned something. A question left open by a different run is
not evidence that this run stopped for it.

#### Scenario: A non-blocking question does not make a task wait

- **WHEN** a run ends having asked a non-blocking question and without moving its task
- **THEN** the task is not recorded as waiting
- **AND** the run is divergent as normal

#### Scenario: An answered question does not make a task wait

- **WHEN** a run ends having asked a question that was answered, without moving its task
- **THEN** the task is not recorded as waiting

#### Scenario: Another run's open question does not make this task wait

- **WHEN** a run ends without moving its task
- **AND** the only unanswered blocking question was asked by a different run
- **THEN** the task is not recorded as waiting
