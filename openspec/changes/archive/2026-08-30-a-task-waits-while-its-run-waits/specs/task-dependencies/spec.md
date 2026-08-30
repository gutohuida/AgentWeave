## MODIFIED Requirements

### Requirement: An unmet dependency prevents starting and nothing else

A task SHALL NOT be moved to in-progress while any task it depends on is not yet approved, where that
move starts work. A task with unmet dependencies SHALL still be assignable, and SHALL still be
rejectable.

Being unable to start and having stopped are different states, and the task lifecycle already
distinguishes them: a task nobody has started is pending, and the status meaning "stopped" is
reachable only from in-progress and denotes work waiting on something a person must supply. A
dependency is a precondition on the act of starting, not a property the task carries.

Assignability is deliberate: it is what allows an entire wave of work to be assigned in advance, with
each task starting when its own prerequisites clear.

**Resuming a stopped task is not starting it, and is not gated.** This reverses the resumption
scenario this requirement previously carried, and the reversal follows from the paragraph above
rather than from a new judgement. The waiting status is reachable only from in-progress, and the
edge into in-progress is the gated one — so a task that is waiting has already passed this gate and
has already begun. It follows that a prerequisite can only fail at the resume edge if it changed
*after* the task started: it left approved, or it was declared while the task was already waiting.
The first of those is the case the sibling requirement below already governs — a dependent that has
started continues, flagged rather than stopped — so gating the resume edge contradicts it. The
second is a dependency declared against work already under way, and it is likewise too late to
prevent that work: the gate would not stop the work, only the record of it.

The cost of gating it is not symmetrical with the cost of not gating it. A refused resumption strands
the task: the operator's answer releases nothing, and an agent whose question went unanswered is
refused the completion of work it has already finished, with no action available to it either way.
An ungated resumption returns a task to the state the regression requirement below already describes
and already requires to be surfaced.

#### Scenario: Starting is refused while a prerequisite is unapproved

- **WHEN** a task whose prerequisite is not approved is moved to in-progress
- **THEN** the move is refused
- **AND** the refusal names the prerequisite that is not met

#### Scenario: Assignment is permitted while a prerequisite is unapproved

- **WHEN** a task whose prerequisite is not approved is assigned to an agent
- **THEN** the assignment succeeds

#### Scenario: Rejection is permitted while a prerequisite is unapproved

- **WHEN** the operator rejects a task whose prerequisite is not approved
- **THEN** the rejection succeeds

#### Scenario: Starting succeeds once every prerequisite is approved

- **WHEN** the last unapproved prerequisite of a task becomes approved
- **THEN** that task may be moved to in-progress

#### Scenario: Resuming a waiting task is not gated

- **GIVEN** a task waiting on a person, whose prerequisite is not approved
- **WHEN** the wait ends by any route
- **THEN** the task returns to in-progress
- **AND** the return is not refused for the unmet prerequisite

#### Scenario: A dependency declared during a wait does not strand the task

- **GIVEN** a task waiting on a person
- **WHEN** a dependency on unapproved work is declared against it, and the wait then ends
- **THEN** the task returns to in-progress
- **AND** the unmet prerequisite is reported against the task

#### Scenario: The board and the gate agree about a waiting task

- **WHEN** a loop's board and the transition service are each asked whether a waiting task may
  proceed, and a prerequisite is not approved
- **THEN** neither refuses it
