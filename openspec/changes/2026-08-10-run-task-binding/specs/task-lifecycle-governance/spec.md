# Task lifecycle governance — deltas

## MODIFIED Requirements

### Requirement: Every accepted transition is recorded append-only

The system SHALL persist one immutable record per accepted status transition, identifying the task,
the status moved from, the status moved to, the responsible run and **agent** where they exist, the kind of
actor (agent run or operator), **what caused the transition to be requested**, and the time. Records MUST NOT be updated or deleted by any application
path; a correction is a further transition, not an edit.

`Task.status` MAY remain as the materialised current value for reads, but MUST NOT be the only
durable statement of how the task reached it.

The recorded cause SHALL distinguish a transition an actor asked for from one the system made on
that actor's behalf. Without that distinction, a transition the runtime performs automatically is
indistinguishable from work the agent did, and any check asking "did this run advance its task?" is
satisfied by the system's own bookkeeping.

#### Scenario: Completion and approval both survive

- **WHEN** one run moves a task to `completed` and a different run later moves it to `approved`
- **THEN** the history contains both transitions
- **AND** each names its own responsible run
- **AND** neither record has been overwritten by the other

#### Scenario: Operator action is recorded without a run

- **WHEN** the operator changes a task's status
- **THEN** a transition is recorded with an actor kind of operator and no responsible run
- **AND** it is distinguishable from a transition caused by an agent run

#### Scenario: History is not editable through the application

- **WHEN** any application path attempts to modify or remove an existing transition record
- **THEN** no such path exists

#### Scenario: Pre-existing tasks start their history where it becomes knowable

- **WHEN** a task that existed before this capability shipped undergoes its first transition
- **THEN** that transition is recorded
- **AND** no transitions are invented for the period before the capability existed

#### Scenario: A transition the system made is distinguishable from one an actor asked for

- **WHEN** the system moves a task automatically as a consequence of an event it observed
- **THEN** the record identifies the cause as the system rather than the actor
- **AND** it still names the run and agent on whose behalf it was made

#### Scenario: Records written before causes were distinguished read as actor-caused

- **WHEN** a transition recorded before this distinction existed is read
- **THEN** it reads as actor-caused
- **AND** no cause is invented for it

## ADDED Requirements

### Requirement: The system may cause a transition without becoming an actor

The system SHALL be able to move a task as a consequence of an event it observes, acting **as** the
responsible run rather than as an actor of its own kind. Such a transition SHALL be subject to every
legality and actor rule that governs a transition the run itself requests, and SHALL be refused on
the same grounds.

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

#### Scenario: The actor kinds remain unchanged

- **WHEN** the set of actor kinds is enumerated
- **THEN** it contains agent run and operator, and nothing else

### Requirement: A task carries how its neglect should be answered

The system SHALL let each task carry a policy describing what happens when work bound to it ends
without the task moving, and the agent to route the work to when that policy escalates.

A task that states no policy SHALL be treated as stating the passive one, so that introducing this
capability changes the behaviour of no existing task.

#### Scenario: An existing task acquires the passive policy

- **WHEN** a task created before this capability existed is read
- **THEN** its policy is the passive one
- **AND** nothing was written to that task to make it so

#### Scenario: The policy is part of the task, not of the project

- **WHEN** two tasks in one project state different policies
- **THEN** each is answered according to its own
