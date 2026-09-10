## MODIFIED Requirements

### Requirement: A waiting task names what it is waiting for

A task in the waiting status SHALL carry a human-readable statement of what it is waiting for. Where
the system recorded the block, that statement SHALL be derived from the question asked. Where the
operator sets it directly, the system SHALL require the statement and SHALL refuse the transition
without one.

The statement SHALL be cleared whenever the task leaves the waiting status, by any route.

A status alone leaves the operator working out what they are holding up, which is the position they
were already in when the task said work was under way and nothing was happening. The status answers
"why is nothing moving"; only the statement answers "what do you need from me".

A control that collects the statement SHALL be operable without a pointer. The statement is
mandatory — it is the entire reason the control asks rather than sending a move that would be
refused — so a control that can be reached one way and not the other does not make the transition
harder, it makes it unavailable to an operator working from the keyboard, and it does so without
reporting anything: the field stays empty and the confirmation stays disabled with nothing on screen
saying why.

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

#### Scenario: The statement can be given from the keyboard alone

- **WHEN** the operator moves a task to the waiting status without using a pointer at any point
- **THEN** the statement they type is held by the control that asked for it
- **AND** the move can be completed with the statement they typed
