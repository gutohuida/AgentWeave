## ADDED Requirements

### Requirement: The operator can rename a task

The operator SHALL be able to change a task's title after it is created, and an agent SHALL NOT.

A title is the line the board and the task view show. It is written once at creation, often by an
agent, and goes stale when the work moves; without a way to change it the only remedy is to replace
the task, which discards its history.

A title SHALL NOT be blank and SHALL keep the length bound it has at creation; a request that sets
the title to nothing SHALL be refused as blank, while a request that does not mention the title
SHALL leave it unchanged. Renaming SHALL NOT record a status transition, and SHALL NOT require
restating the task's status: a task in any status, including a blocked one, can be renamed.

An agent's rename SHALL be refused before anything in the same request is applied.

#### Scenario: The operator renames a task

- **WHEN** the operator changes a task's title
- **THEN** the task shows the new title everywhere it is listed
- **AND** its status and transition history are unchanged

#### Scenario: A blank title is refused

- **WHEN** the operator submits a title that is empty after trimming
- **THEN** the change is refused and the title is unchanged

#### Scenario: A blocked task can be renamed

- **GIVEN** a task that is blocked
- **WHEN** the operator changes its title from the task view
- **THEN** the title changes
- **AND** the task is still blocked, with its reason unchanged

#### Scenario: An agent cannot rename a task

- **WHEN** an agent's run submits a new title for a task, with or without a status
- **THEN** the change is refused and the title is unchanged
- **AND** no status the same request asked for is applied
