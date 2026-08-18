# task-lifecycle-governance

## ADDED Requirements

### Requirement: A task list can be scoped to one loop's queue

The Hub SHALL let a caller of the task list scope the result to exactly the tasks that name one
loop, and SHALL apply no other filter to that scoped result — an explicit loop scope SHALL show
every task naming it, regardless of that task's own status.

A scope naming a loop with no queued tasks SHALL return an empty list, and this SHALL NOT be an
error.

#### Scenario: Scoping to a loop returns exactly its queued tasks

- **WHEN** the task list is requested scoped to one loop
- **THEN** every task naming that loop is returned
- **AND** no task naming a different loop, or naming none, is returned

#### Scenario: A loop-scoped view hides nothing regardless of status

- **WHEN** the task list is scoped to a loop that owns a task in a terminal status
- **THEN** that task is included in the scoped result
