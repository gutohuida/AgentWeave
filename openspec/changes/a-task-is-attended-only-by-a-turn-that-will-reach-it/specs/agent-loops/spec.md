## MODIFIED Requirements

### Requirement: A task reported as in flight is one an agent is actually working

A firing SHALL classify a task as in flight only where an agent is actually working it: a turn bound to that task is running, or input naming that task is waiting to be delivered to the agent whose name is on it. A name written in the task's assignee SHALL NOT by itself be sufficient.

Input counts as waiting to be delivered to an agent only where all of these hold: it is queued for that agent, not for any other; it is within the project's hop budget; and its last delivery was not refused. Input queued for another agent is that agent's turn, not the named agent's, and SHALL NOT count however the Hub happens to read the rows. Input past the hop budget is delivered only if the operator releases it, so it is a turn nobody will take unless they act. Input whose last delivery was refused waits for an attempt that the same refusal may answer again, so it is not a turn being taken either; the refusal's own sentence is what the operator is owed instead.

Where an assigned task is in flight by this definition, the firing SHALL NOT brief its agent on it again, whatever the reason the waiting input has not started. A second briefing does not start the first one; it queues one more copy that is delivered as a separate turn once a turn can start.

Where a non-terminal task has an assignee and neither condition holds, the firing SHALL record it as a step it could not staff, naming the task and the agent whose name is on it, and that reason SHALL reach the loop's stall reason and the loop's own state surface. The refusal's sentence SHALL NOT state or imply that the work is being done, that nothing is wrong, or that a later firing will pick it up.

An assignee is a record of who holds a task, not evidence that a turn exists. Reading it as evidence lets a firing report a queue as busy while every agent in the project is idle, which is worse than silence: the operator is not merely uninformed, they are told the flow is healthy, and the remedy is theirs alone to apply.

#### Scenario: A review with no turn behind it is not counted as in flight

- **WHEN** a loop fires and its only non-terminal task is under review with an assignee, and no run bound to that task is running and no undelivered queue entry names it
- **THEN** the firing does not report the task as in flight
- **AND** the recorded reason names the task and the agent whose name is on it

#### Scenario: The refusal does not claim the work is being done

- **WHEN** a firing is refused for a task whose assignee holds no turn
- **THEN** the refusal's reason does not state that the task is already being worked
- **AND** it does not state that a later firing will pick up whatever finishes

#### Scenario: The loop's state surface names it too

- **WHEN** a loop's state is read while it holds a review nobody is doing
- **THEN** the loop's stall reason names that review rather than being absent

#### Scenario: A review whose turn is running is still in flight

- **WHEN** a loop fires while a run bound to its under-review task is running
- **THEN** the firing reports that task as in flight, as it does today
- **AND** the loop records no stall for it

#### Scenario: A staffed review still waiting in the queue is still attended

- **WHEN** a review has been staffed and its input is queued for an agent that has not yet been given a turn
- **THEN** the firing does not report that review as unstaffed
- **AND** no stall is recorded for it

#### Scenario: The board still says the agent holds it rather than merely being assigned it

- **WHEN** a loop's state is read while it holds a review nobody is doing
- **THEN** the task's agent capacity still reports that the agent holds it, distinct from the value used when a turn is running and distinct from the value used for a task's own assignee

#### Scenario: Input for another agent does not make a review attended

- **WHEN** a task is under review with an agent named on it, no turn is running on it, and the only input naming it is queued for a different agent
- **THEN** the firing does not report the task as in flight
- **AND** the recorded reason names the task and the agent whose name is on it

#### Scenario: Input past the hop budget does not make a review attended

- **WHEN** a task is under review with an agent named on it, no turn is running on it, and the only input naming it that is queued for that agent is past the project's hop budget
- **THEN** the firing does not report the task as in flight

#### Scenario: Input whose delivery was refused does not make a review attended

- **WHEN** a task is under review with an agent named on it, no turn is running on it, and the only input naming it that is queued for that agent was refused on its last delivery
- **THEN** the firing does not report the task as in flight
- **AND** the recorded reason contains the refusal's own sentence

#### Scenario: The named agent's own input is found whichever agent's input is read first

- **WHEN** an assigned task has input naming it queued for its assignee, and input naming it is also queued for an agent whose name sorts before the assignee's
- **AND** the flow fires three times
- **THEN** no further input is queued for the assignee
- **AND** the task is reported in flight on every firing

#### Scenario: An idle assignee whose queued turn cannot start is not briefed again

- **WHEN** an assigned task's agent is running no turn, is not held, and has input naming the task queued within the hop budget that the scheduler has not started
- **AND** the flow fires three times
- **THEN** no further input is queued for that agent
- **AND** the task is reported in flight

#### Scenario: An assignee whose input was refused is briefed as before

- **WHEN** an assigned task's agent is running no turn, and the only input naming the task queued for it was refused on its last delivery
- **THEN** the firing briefs the agent on the task, as it resumes any assigned task

#### Scenario: A busy flow is still not reported as stalled

- **WHEN** every candidate in a loop's queue is held by a running turn
- **THEN** the firing reports in flight rather than stalled
