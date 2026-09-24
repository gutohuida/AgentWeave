## ADDED Requirements

### Requirement: A move a scheduled firing makes is recorded as that firing's job

A transition made by a loop or flow firing SHALL be recorded with the operator as its actor and a cause that names the scheduled job which made it, and SHALL NOT be recorded as a transition the operator asked for.

A flow claims work and stages reviews with the operator's authority, because the operator created
it; that authority is what the transition map and the separation rules need, and it does not change.
What the history must not say is that the operator *asked*: an operator reading how a task came to
be assigned or put under review would otherwise be told they did it, at an hour they were asleep.

There SHALL remain exactly two actor kinds. The distinction is a recorded cause, alongside the
existing distinction between an actor's request and the runtime acting for a run, and the job SHALL
be identified by a reference that outlives the firing's own records.

A transition the operator makes by hand — including dispatching a review themselves — SHALL continue
to be recorded as the operator's request.

#### Scenario: A flow claims a task

- **WHEN** a flow's firing moves a pending task to assigned for one of its agents
- **THEN** the recorded transition has the operator as its actor kind
- **AND** its cause names a scheduled job, and the job it names is that flow's
- **AND** the operator's view of the task's history attributes the move to that flow, not to the operator

#### Scenario: A flow stages a review

- **WHEN** a flow's firing moves a completed task to under review for a reviewer
- **THEN** the recorded transition's cause names that flow's job

#### Scenario: A flow's review delivered after its task came back

- **GIVEN** a flow queued a review of a task and staged it under review
- **AND** before the review was delivered the task left review and was completed again
- **WHEN** the queued review is delivered and moves the task to under review
- **THEN** the recorded transition's cause names that flow's job

#### Scenario: The operator's own dispatch is still the operator's

- **WHEN** the operator dispatches a review by hand and the task moves to under review
- **THEN** the recorded transition's cause is an actor's request and names no job

#### Scenario: No guard moves

- **WHEN** a transition recorded as a scheduled job's would be refused for the operator
- **THEN** it is refused on exactly the same grounds

## MODIFIED Requirements

### Requirement: The system may cause a transition without becoming an actor

The system SHALL be able to move a task as a consequence of an event it observes, acting **as** the
responsible run rather than as an actor of its own kind. Such a transition SHALL be subject to every
legality and actor rule that governs a transition the run itself requests, and SHALL be refused on
the same grounds.

A scheduled job's firing SHALL likewise act **as the operator**, whose authority it holds because the
operator created the job, and not as an actor of its own kind. Its moves SHALL be subject to every
legality and actor rule that governs a transition the operator requests, and SHALL be refused on the
same grounds; only the recorded cause says a scheduled job made them.

There SHALL NOT be a third actor kind for the system. Actor kind is what the transition map and
author/reviewer separation are keyed on; a system actor would require every edge to declare whether
the system may take it, and would admit moves for which no one is accountable.

#### Scenario: An automatic move obeys the map

- **WHEN** the system would move a task automatically
- **AND** that move is not an edge available to the responsible run
- **THEN** no transition occurs
- **AND** the task is unchanged

#### Scenario: Author and reviewer separation is unaffected

- **WHEN** a transition is made automatically on behalf of a run
- **THEN** the agent recorded is that run's agent
- **AND** later review of that task is judged against that agent exactly as if the agent had asked

#### Scenario: A scheduled job's move is the operator's authority

- **WHEN** a loop or flow firing moves a task
- **THEN** the recorded actor kind is operator
- **AND** the move is allowed or refused exactly as the same move requested by the operator would be

#### Scenario: The actor kinds remain unchanged

- **WHEN** the set of actor kinds is enumerated
- **THEN** it contains agent run and operator, and nothing else
