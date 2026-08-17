# Task lifecycle governance — deltas

## ADDED Requirements

### Requirement: Declining a question releases the task it parked

Where a question caused a task to be recorded as waiting, declining that question SHALL return the
task to the in-progress status and clear what it was waiting for, as an operator-caused transition.

The operator has stated the answer is not coming, so the task is no longer waiting on them. A task
left waiting would claim to be held up by a question that has been closed — a block with nothing
behind it, which is the state the requirement that a block names what it is waiting for exists to
prevent.

A declined question SHALL NOT cause a task to be recorded as waiting. Otherwise the run-boundary
check would park the task again on the question the operator just closed, and the release would be
undone by the mechanism it was meant to satisfy.

#### Scenario: Declining frees the task

- **WHEN** the operator declines the question that caused a task to be recorded as waiting
- **THEN** the task returns to the in-progress status
- **AND** it no longer states what it is waiting for

#### Scenario: A declined question does not park a task

- **WHEN** a run ends without moving its task
- **AND** the only outstanding blocking question it asked has been declined
- **THEN** the task is not recorded as waiting

#### Scenario: The boundary check applies again once released

- **WHEN** a task released by a decline is later dropped by a bound run
- **THEN** that run is divergent as normal

#### Scenario: Declining a question that parked nothing changes no task

- **WHEN** the operator declines a question that never caused a task to wait
- **THEN** no task changes status
