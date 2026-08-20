## ADDED Requirements

### Requirement: Starting work is gated on its prerequisites, and the gate lives with the other gates

The transition to in-progress SHALL be guarded by the task's dependencies, and that guard SHALL be
applied in the same place as the machine's existing guards — inside the transition service, before
the history row is written.

Placement is the requirement, not an implementation note. The existing gates are positioned there
precisely so that no caller can reach a status write another way, which is what gives every surface —
the operator's route, the agent capability plane, the tool surface, scheduled jobs — the same
enforcement without any of them knowing it exists. A dependency check applied at a route, or in the
board, would be a rule that holds for the callers somebody remembered.

#### Scenario: Every surface is gated identically

- **WHEN** a task with an unmet prerequisite is moved to in-progress through any surface
- **THEN** the move is refused

#### Scenario: The refusal is distinguishable from an illegal transition

- **WHEN** a start is refused for an unmet prerequisite
- **THEN** the refusal identifies the cause as a dependency rather than as an illegal edge

### Requirement: Gating start does not gate assignment

The transition to assigned SHALL NOT be gated by dependencies.

Assigning is a statement about who will do a piece of work; starting is a statement that it is being
done. Gating assignment would make it impossible to assign a wave of work in advance, and would force
whatever performs assignment to run again each time a prerequisite cleared.

#### Scenario: Work can be assigned before it can start

- **WHEN** a task with unmet prerequisites is assigned
- **THEN** the assignment succeeds
- **AND** the task still cannot be started

### Requirement: A task with no declared dependencies is unaffected

Where a task declares no dependencies, its transitions SHALL behave exactly as they did before
dependencies existed.

Every project gains this guard at once. It is safe to do so only because a task with nothing declared
has nothing that can fail, and that property is what makes the change deployable without a migration
of behaviour.

#### Scenario: An existing task is unaffected

- **WHEN** a task created before dependencies existed is moved through its lifecycle
- **THEN** every transition behaves as before
