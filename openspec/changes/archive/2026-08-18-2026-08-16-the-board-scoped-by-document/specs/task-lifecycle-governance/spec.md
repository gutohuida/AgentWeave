# task-lifecycle-governance

## ADDED Requirements

### Requirement: A task list can be scoped to one specification document's declared work

The Hub SHALL let a caller of the task list scope the result to exactly the tasks one specification
document declared, and SHALL apply no other filter to that scoped result — an explicit scope SHALL
show every task the document declared, regardless of that task's own status or its declaring
document's phase.

A scope naming a document with no declared tasks SHALL return an empty list, and this SHALL NOT be
an error.

#### Scenario: Scoping to a document returns exactly its declared tasks

- **WHEN** the task list is requested scoped to one specification document
- **THEN** every task whose declaring document is that document is returned
- **AND** no task whose declaring document is a different document is returned

#### Scenario: A scoped view hides nothing regardless of status or phase

- **WHEN** the task list is scoped to a document that is itself archived
- **AND** that document declared a task whose own status is terminal
- **THEN** that task is included in the scoped result

### Requirement: The task list's default view retires completed work from archived documents

The Hub SHALL offer a task list mode that excludes a task if, and only if, the task's declaring
document has reached the `archived` phase and the task's own status is terminal. This exclusion
SHALL NOT be applied unless the caller asks for it, so a caller that does not ask for it — including
every caller that existed before this exclusion was added — SHALL see every task exactly as before.

A task with no declaring document SHALL NOT be excluded by this mode, regardless of its status.

An open (non-terminal) task whose declaring document is archived SHALL NOT be excluded by this
mode — work someone still has to do is not retired because the document that described it was
tidied away.

This exclusion SHALL NOT alter any task's status, assignee, or any other field. It changes only
what a request that asks for it is shown.

#### Scenario: A completed task from an archived document is excluded

- **WHEN** the exclusion mode is requested
- **AND** a task's declaring document is archived
- **AND** that task's own status is terminal
- **THEN** that task is absent from the result

#### Scenario: An open task from an archived document is not excluded

- **WHEN** the exclusion mode is requested
- **AND** a task's declaring document is archived
- **AND** that task's own status is not terminal
- **THEN** that task is present in the result

#### Scenario: A task with no declaring document is never excluded

- **WHEN** the exclusion mode is requested
- **AND** a task has no declaring document
- **THEN** that task is present in the result regardless of its status

#### Scenario: The exclusion is opt-in

- **WHEN** the task list is requested without asking for the exclusion mode
- **THEN** every task is returned, including ones the exclusion mode would have hidden

#### Scenario: Exclusion never mutates a task

- **WHEN** the exclusion mode causes a task to be absent from one request's result
- **THEN** a subsequent unscoped request for that same task returns it with every field unchanged
