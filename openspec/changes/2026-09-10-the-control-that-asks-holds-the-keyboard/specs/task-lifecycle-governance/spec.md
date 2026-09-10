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

A control that collects the statement SHALL accept it from the keyboard: once the operator has
chosen the move, the keyboard SHALL be in that control. The statement is mandatory — it is the
entire reason the control asks rather than sending a move that would be refused — so a control that
takes the statement from a pointer and not from the keyboard does not make the transition harder, it
makes it unavailable to an operator working from the keyboard, and it does so without reporting
anything: the field stays empty and the confirmation stays disabled with nothing on screen saying
why.

This says nothing about how the operator *reaches* the control. Where focus starts when a panel
opens is a general question about panels, it is governed by the interaction requirements rather than
restated here, and it is not settled today.

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

#### Scenario: The statement is typed into the control that asked for it

- **WHEN** the operator chooses the move to the waiting status from the keyboard
- **THEN** the keyboard is in the control asking what the task is waiting for, once the menu has
  closed
- **AND** what they type next appears in it
- **AND** the move can be completed with the statement they typed
