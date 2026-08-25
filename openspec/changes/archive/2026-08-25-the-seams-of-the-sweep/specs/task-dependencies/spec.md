## ADDED Requirements

### Requirement: The operator can declare a dependency between existing tasks

An operator SHALL be able to declare that one task depends on another, for tasks they created,
without authoring a specification document.

Today dependency rows are written in exactly one place, reached only when an approved document
carries ordering keys. The task-update surface refuses the field and no dependency route exists. So
an operator cannot say "B needs A" about two tasks they made, and the whole subsystem — the gate,
the board tab, two tables, and the prerequisite and dependent fields on every task — is reachable
only if an agent happens to author the right keys into a document that is then approved. In the
sweep the agent authored no ordering at all, so the graph came out empty and the gate was never
exercisable.

Both paths SHALL write dependencies through one shared writer, so the graph cannot be built two
different ways.

#### Scenario: An operator declares a dependency
- **WHEN** the operator declares that task B depends on task A
- **THEN** the dependency SHALL be recorded
- **AND** the existing gate SHALL apply to B unchanged

#### Scenario: The dependency would form a cycle
- **WHEN** a declared dependency would create a cycle
- **THEN** it SHALL be refused, naming the cycle

#### Scenario: A named task does not exist
- **WHEN** a declared dependency names a task that does not exist
- **THEN** it SHALL be refused, naming which one

#### Scenario: The document path is unchanged
- **WHEN** an approved document declares ordering between its own tasks
- **THEN** the dependencies SHALL be recorded exactly as before

#### Scenario: An operator removes a dependency
- **WHEN** the operator removes a declared dependency
- **THEN** it SHALL no longer gate the dependent task
