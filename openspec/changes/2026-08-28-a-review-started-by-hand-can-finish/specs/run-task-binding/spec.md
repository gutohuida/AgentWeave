## MODIFIED Requirements

### Requirement: A run started to review a task binds to that task

The system SHALL bind a run started to review a task to the task under review, by the same binding
the runtime already performs for a run started to work a task, and SHALL NOT require a second
mechanism to do it.

A review turn is not one of the causes for which an unbound run is legitimate. Exploration,
conversation, questions and scheduled work have no task; a review has exactly one, and it is the
task whose work is being judged.

The instruction that gives a review turn its workspace SHALL remain distinct from the binding.
Selecting which commit a reviewer checks out and recording which task a run is about are different
questions, and a single value answering both would make an entry's two purposes inseparable.

Binding a review SHALL NOT move the task. The transitions available to a run from a task under
review do not include starting it, so binding records the association and changes no status.

This SHALL NOT be read as forbidding the dispatch that precedes the binding from moving the task.
Staffing a review — recording its reviewer as the task's holder and moving the task into review — is
an act of dispatch, and it happens before the binding is resolved. By the time the binding is read,
the task is already in review and already held by its reviewer, and binding still changes neither.
The rule constrains what binding does, not what the task's status was when binding observed it.

Where a turn delivers both an item of work and a review, the binding SHALL be determined
deterministically by the same ordering already used to select among several items naming a task.

#### Scenario: A review run records the task it is reviewing

- **WHEN** a run is started to review a task
- **THEN** the run durably identifies that task
- **AND** the binding is readable for the run's whole life and after it ends

#### Scenario: Binding a review does not start the task

- **WHEN** a run binds to a task that is under review
- **THEN** the task's status is unchanged
- **AND** the task's assignee is unchanged

#### Scenario: Staffing precedes binding, and binding still moves nothing

- **WHEN** a review turn is dispatched for a task that its reviewer does not yet hold
- **THEN** the task is held by that reviewer and in review before the binding is resolved
- **AND** resolving the binding changes neither the task's status nor its assignee

#### Scenario: A review turn is subject to the run boundary

- **WHEN** a run bound to a task under review ends
- **THEN** the boundary determination is performed for it, as for any other bound run

#### Scenario: The workspace instruction and the binding stay separate

- **WHEN** a review turn is prepared
- **THEN** the value selecting the commit to check out and the value recording the bound task are
  distinct
- **AND** neither is derived by reinterpreting the other

#### Scenario: A turn carrying both work and a review binds deterministically

- **WHEN** a turn delivers an item naming a task for work and an item naming a task for review
- **THEN** the run binds to exactly one of them
- **AND** the same input always produces the same binding
