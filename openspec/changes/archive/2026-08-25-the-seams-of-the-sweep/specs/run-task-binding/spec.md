## ADDED Requirements

### Requirement: Claiming an unheld task binds the run to it

A run that moves a task it does not hold into `in_progress` SHALL become bound to that task. A run
that already holds a different task SHALL be refused, preserving the existing invariant that a run
carries at most one task binding.

This is what makes "go and find waiting work" — the behaviour the Developer charter asks for — a
claim rather than an observation. Without it, the one fact that separates *"I finished this"* from
*"I noticed this"* is never recorded.

#### Scenario: An unbound run claims a waiting task
- **WHEN** a run carrying no task binding moves a `pending` task to `in_progress`
- **THEN** the run SHALL become bound to that task
- **AND** the transition SHALL be permitted

#### Scenario: A run that already holds a task tries to claim a second
- **WHEN** a run bound to task A moves task B to `in_progress`
- **THEN** the transition SHALL be refused
- **AND** the refusal SHALL name the task the run is already bound to

#### Scenario: The operator is unaffected
- **WHEN** the operator moves a task to `in_progress`
- **THEN** no binding SHALL be required or created
- **AND** the transition SHALL be permitted

#### Scenario: The runtime binding path is unchanged
- **WHEN** the runtime binds a run to a task and starts it
- **THEN** the run SHALL already be bound when the transition is evaluated
- **AND** the transition SHALL be permitted
