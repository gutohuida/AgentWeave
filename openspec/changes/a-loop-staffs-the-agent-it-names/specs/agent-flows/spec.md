## ADDED Requirements

### Requirement: A firing staffs a documentless loop only with the agent its job names

The Hub SHALL staff a firing of a loop that declares no specification document only with the agent that loop's job names, and SHALL NOT select any other agent for it, whatever else is available.

Where that agent cannot take a turn, the firing SHALL staff nobody for the task rather than
substituting another agent. The task SHALL keep its status and SHALL gain no assignee, and a later
firing SHALL consider it again.

This restriction SHALL be a filter over the agents the Hub has already determined to be available,
and SHALL NOT introduce any further condition on whether an agent can take a turn. An agent
excluded by it SHALL be excluded because this loop does not name it, never because it was judged
unable to work.

A flow SHALL be unaffected: the agents a firing of a loop that declares a specification document may
staff SHALL remain every available agent in the project, so that a flow may still start several
tasks in one firing.

The distinction SHALL be the presence of the declared document and nothing else.

#### Scenario: A busy agent's loop does not hand its work to a free sibling

- **WHEN** a loop declares no specification document, its job names one agent, that agent is running
  a turn, another agent in the project is free, and the loop's job is fired
- **THEN** no task is started
- **AND** the free agent is not selected
- **AND** the loop's pending task keeps its status and gains no assignee

#### Scenario: A loop does not start a second task alongside the first

- **WHEN** a loop declares no specification document, two of its tasks have all their dependencies
  met, its own agent is free, and another agent in the project is free
- **THEN** exactly one task is started
- **AND** it is started for the agent the loop's job names
- **AND** the second task keeps its status and gains no assignee

#### Scenario: A flow still staffs every available agent

- **WHEN** a loop declares a specification document, two of its tasks have all their dependencies
  met, and two eligible agents are available
- **THEN** both tasks are started

#### Scenario: An agent the loop names but cannot be started is not replaced

- **WHEN** a loop declares no specification document and the agent its job names has no runner bound
- **THEN** no task is started
- **AND** no other agent is selected in its place

#### Scenario: A loop fires its own agent once that agent is free

- **WHEN** a loop declares no specification document, the agent its job names has finished its turn,
  and the loop's job is fired with claimable work
- **THEN** a task is started for the agent the loop's job names
