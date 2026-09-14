## MODIFIED Requirements

### Requirement: A surfaced step is recorded once, not once per tick

The Hub SHALL surface a step a firing could not take when that fact is new or has changed for the task, and SHALL NOT persist a further record of it on each subsequent firing that finds the same fact unchanged.

A condition an operator must resolve can outlive many firings, and one that only the operator can clear outlives all of them. Repeating it every tick buries the records of the firings that did work, which is the same harm the loop's own execution history is already required to avoid.

**"Unchanged" SHALL be judged against that task's own most recent record**, never against the loop's most recent record of any task. A loop holding two steps it cannot take surfaces both on every firing. Comparing each against whichever was recorded last always finds the other task, so every firing records both again. Measured on the operator's own flow, 347 of 357 such records repeated their task's previous reason word for word. The rule held only during the one stretch when a single step was stuck.

#### Scenario: An unchanged surfaced step is recorded once

- **WHEN** a loop fires repeatedly and each firing finds the same step unsurfaceable for the same reason
- **THEN** exactly one record of that surfacing exists

#### Scenario: Two steps surfaced by one loop are each recorded once

- **WHEN** a loop fires repeatedly, and each firing finds the same two steps unsurfaceable, each for an unchanged reason
- **THEN** exactly one record exists for each of the two steps

#### Scenario: A changed reason for one step does not re-record the other

- **WHEN** a loop surfaces two steps, and between firings the reason changes for one of them only
- **THEN** a further record is persisted for the step whose reason changed
- **AND** no further record is persisted for the other

#### Scenario: A changed reason is recorded again

- **WHEN** the reason a step cannot be taken changes between firings
- **THEN** a further record is persisted, carrying the new reason

#### Scenario: The first firing still surfaces it

- **WHEN** a firing is the first to find a step it cannot take
- **THEN** that surfacing is recorded and broadcast
