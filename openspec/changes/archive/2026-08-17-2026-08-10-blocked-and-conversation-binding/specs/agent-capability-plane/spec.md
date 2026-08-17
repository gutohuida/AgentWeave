# Agent capability plane — deltas

## ADDED Requirements

### Requirement: An agent cannot declare its own work blocked or unblocked

No agent-facing operation — over HTTP or MCP — SHALL move a task into or out of the status meaning
it is waiting on a person. That status SHALL be reached only by the system observing an unanswered
question, or by the operator.

This is the same rule, for the same reason, as an agent's inability to bind its own run or to set
its own task's divergence policy: a state the subject can assert is not a state that constrains it.
Of all the statuses, this is the one an agent under a completion gate has most reason to want — it
is the account that excuses an unfinished task — so it is the one that must be earned by actually
having asked a person something they have not yet answered.

#### Scenario: The agent surface offers no blocking operation

- **WHEN** an agent enumerates the operations available to it
- **THEN** none of them moves a task into or out of the waiting status

#### Scenario: Requesting the status directly is refused

- **WHEN** an agent requests the waiting status for a task through any available operation
- **THEN** the request is refused
- **AND** the task is unchanged

#### Scenario: Asking a real question is the only route

- **WHEN** an agent asks the operator a blocking question and its run ends unanswered
- **THEN** its bound task is recorded as waiting
- **AND** the record identifies the question it is waiting on
