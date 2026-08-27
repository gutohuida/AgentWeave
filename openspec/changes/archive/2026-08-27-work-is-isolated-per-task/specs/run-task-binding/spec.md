## ADDED Requirements

### Requirement: A turn's task is resolved before its workspace is chosen

The system SHALL resolve which task a turn is about before it chooses the workspace that turn will run in, so the workspace can be the one belonging to that task.

Resolving the binding SHALL remain a read. It SHALL NOT create the run's binding, move the task, or rebind the conversation; those effects SHALL stay where they are, before delivery, so a bound run whose task never moved cannot exist as a partial write.

Where the turn names a task that does not exist in the project, the refusal SHALL be raised before any checkout is provisioned. A request that is going to be refused SHALL NOT leave a workspace behind.

Resolving the binding SHALL NOT take precedence over the project directory being unavailable. A project whose directory cannot be resolved SHALL still report that condition, with its directory state, rather than reporting a task refusal instead.

#### Scenario: The workspace is chosen after the task is known

- **WHEN** a turn bound to a task begins
- **THEN** the workspace it runs in is the one belonging to that task

#### Scenario: A refused binding leaves nothing provisioned

- **WHEN** a turn is triggered naming a task that does not exist in the project
- **THEN** the request is refused
- **AND** no checkout has been created for the agent or the named task

#### Scenario: An unavailable project directory still wins

- **WHEN** a turn is triggered naming a nonexistent task in a project whose directory is unavailable
- **THEN** the reported condition is the unavailable directory, with its directory state

#### Scenario: Resolution causes no state change of its own

- **WHEN** the binding for a turn is resolved
- **THEN** no task status has changed, no run is bound, and no conversation has been rebound as a
  result of the resolution alone
