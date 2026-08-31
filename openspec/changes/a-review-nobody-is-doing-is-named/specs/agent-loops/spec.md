## ADDED Requirements

### Requirement: A task reported as in flight is one an agent is actually working

A firing SHALL classify a task as in flight only where an agent is actually working it: a turn bound to that task is running, or input naming that task is queued for delivery and has not yet been delivered. A name written in the task's assignee SHALL NOT by itself be sufficient.

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

#### Scenario: A busy flow is still not reported as stalled

- **WHEN** every candidate in a loop's queue is held by a running turn
- **THEN** the firing reports in flight rather than stalled

### Requirement: A surfaced step is recorded once, not once per tick

The Hub SHALL surface a step a firing could not take when that fact is new or has changed for the task, and SHALL NOT persist a further record of it on each subsequent firing that finds the same fact unchanged.

A condition an operator must resolve can outlive many firings, and one that only the operator can clear outlives all of them. Repeating it every tick buries the records of the firings that did work, which is the same harm the loop's own execution history is already required to avoid.

#### Scenario: An unchanged surfaced step is recorded once

- **WHEN** a loop fires repeatedly and each firing finds the same step unsurfaceable for the same reason
- **THEN** exactly one record of that surfacing exists

#### Scenario: A changed reason is recorded again

- **WHEN** the reason a step cannot be taken changes between firings
- **THEN** a further record is persisted, carrying the new reason

#### Scenario: The first firing still surfaces it

- **WHEN** a firing is the first to find a step it cannot take
- **THEN** that surfacing is recorded and broadcast
