## ADDED Requirements

### Requirement: A run may only complete the task it holds

Moving a task to `completed` as a run actor SHALL require that the acting run is bound to that task.
A run bound to a different task, or to none, SHALL be refused. The operator SHALL be unaffected.

This closes the only path by which unearned work reaches the default branch. Because `completed`
sits in the awaiting-handoff band, a task falsely marked complete is offered to another agent as
reviewable work; that reviewer finds the code correct — it is, because a different agent really did
it — approves, and integration merges. No human is on that path and no single statement along it is
false.

The gate SHALL live where the dependency and requirement gates already live, so that every surface
— operator route, agent HTTP, tool surface, scheduled jobs and the runtime binding — is covered
without knowing it exists.

Completion SHALL NOT begin requiring evidence. Evidence is accepted after review and review follows
completion, so requiring it here would deadlock the ordinary path. The question this gate asks is
*who*, not *how much proof*.

#### Scenario: An unbound run tries to complete a task
- **WHEN** a run carrying no task binding moves a task to `completed`
- **THEN** the transition SHALL be refused
- **AND** the refusal SHALL state that the run is not bound to that task

#### Scenario: A run completes a task it holds
- **WHEN** a run bound to a task moves that task to `completed`
- **THEN** the transition SHALL be permitted

#### Scenario: A run tries to complete a peer's task
- **WHEN** a run bound to task A moves task B to `completed`
- **THEN** the transition SHALL be refused
- **AND** the refusal SHALL name the task the run is bound to

#### Scenario: The operator completes a task
- **WHEN** the operator moves a task to `completed`
- **THEN** the transition SHALL be permitted with no binding required

#### Scenario: A run that claimed the work can finish it
- **WHEN** a run claims a `pending` task, becoming bound to it, and later completes it
- **THEN** both transitions SHALL be permitted
