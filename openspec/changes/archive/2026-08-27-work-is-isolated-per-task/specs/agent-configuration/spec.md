## MODIFIED Requirements

### Requirement: An agent's workspace states where it works and whether that place is its own

The workspace section SHALL state the directory an agent's turn runs in, and whether that directory is an isolated checkout or the project checkout it shares.

Where an agent's work is isolated per task, the section SHALL list the task checkouts that exist for that agent's tasks as well as the agent's own, and SHALL distinguish the two kinds. An operator shown only one directory for an agent working three tasks is shown a place two thirds of its work is not.

Each listed checkout SHALL name the branch it is on and the task it belongs to, where it belongs to one, so an operator can find a task's work without knowing how checkouts are named.

A task that is being worked in the agent's own checkout because its work began before per-task isolation SHALL be shown as such. Otherwise an operator looking for that task's checkout finds none and concludes the work was lost.

Reading it MUST NOT provision anything. An agent that has never run SHALL be told where it will work rather than shown an empty section, because a section that renders blank is indistinguishable from one that failed to load.

Where an agent's isolation cannot be prepared, the section SHALL state the reason — the same condition that would otherwise surface only as a refused turn.

#### Scenario: An agent that has never run

- **WHEN** the operator opens the workspace section for an agent with no checkout yet
- **THEN** the directory it will work in is stated
- **AND** no checkout is created by opening the section

#### Scenario: An agent working several tasks

- **WHEN** the operator opens the workspace section for an agent holding more than one task with a
  checkout of its own
- **THEN** each of those checkouts is listed, with its branch and the task it belongs to

#### Scenario: A task still worked in the agent's own checkout

- **WHEN** the operator opens the workspace section for an agent holding a task whose work began
  before per-task isolation
- **THEN** that task is shown as being worked in the agent's own checkout

#### Scenario: A workspace that cannot isolate

- **WHEN** an agent's project directory cannot provide an isolated checkout
- **THEN** the section states why
- **AND** it says so before a turn is refused over it
