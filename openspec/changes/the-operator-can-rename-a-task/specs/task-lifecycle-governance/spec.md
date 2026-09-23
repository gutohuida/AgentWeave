## ADDED Requirements

### Requirement: The operator can rename a task

The operator SHALL be able to change a task's title after it is created, and an agent SHALL NOT.

A title is the line the board and the task view show. It is written once at creation, often by an
agent, and goes stale when the work moves; without a way to change it the only remedy is to replace
the task, which discards its history.

A title SHALL NOT be blank and SHALL keep the length bound it has at creation. Renaming SHALL NOT
record a status transition.

#### Scenario: The operator renames a task

- **WHEN** the operator changes a task's title
- **THEN** the task shows the new title everywhere it is listed
- **AND** its status and transition history are unchanged

#### Scenario: A blank title is refused

- **WHEN** the operator submits a title that is empty after trimming
- **THEN** the change is refused and the title is unchanged

#### Scenario: An agent cannot rename a task

- **WHEN** an agent's run submits a new title for a task
- **THEN** the change is refused and the title is unchanged
