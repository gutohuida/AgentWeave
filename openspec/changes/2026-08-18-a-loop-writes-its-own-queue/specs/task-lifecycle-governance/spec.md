# task-lifecycle-governance

## ADDED Requirements

### Requirement: A task's loop is set by a named writer when the task is created

The Hub SHALL set a task's loop only at creation, and only from one of two writers: the approval of a
specification document bound to that loop, or the loop's creator adding the task directly.

A task's loop SHALL NOT be changed after creation, by any actor. Moving finished or in-flight work
between loops would make a loop's queue history — and therefore its stop condition, which is derived
from that history — unable to answer what work the loop was ever given.

#### Scenario: A task created outside either writer has no loop

- **WHEN** a task is created by any path other than a bound document's approval or its loop's creator
- **THEN** the task has no loop
- **AND** it does not appear in any loop's queue

#### Scenario: A task's loop cannot be reassigned

- **GIVEN** a task that belongs to a loop's queue
- **WHEN** any actor attempts to change which loop it belongs to
- **THEN** the attempt is refused
- **AND** the task's loop is unchanged

#### Scenario: A terminal task remains in its loop's queue history

- **GIVEN** a task in a loop's queue that has reached a terminal status
- **WHEN** the loop's queue history is retrieved
- **THEN** the task is included
