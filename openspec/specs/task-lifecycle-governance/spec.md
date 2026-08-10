# task-lifecycle-governance

## Purpose

Which task status transitions are legal, who may perform them, how an illegal one is refused, and
the durable append-only record of every accepted transition.

Established by `openspec/changes/2026-08-10-task-transition-machine` (roadmap change **B1**). Before
it, a task's status was whatever the last writer said: `update_task_for_actor` applied
`task.status = body.status` with no adjacency and no actor rule, and the MCP `update_task` tool
handed that to every bound agent — so a run could move its own work from `in_progress` to
`approved` in one call, and `Task.updated_by_run_id`, being a single mutable column, could not even
record that the author and the approver were the same.

This capability governs **validity**: that a recorded transition is legal, attributed, and made by
an entitled actor. It does not govern **liveness** — whether a transition happens at all when
reality changes — which needs the run-to-task binding explored in
`openspec/explorations/2026-08-10-enforcing-the-development-cycle.md`. The completion gates of B3
and B4 land inside this capability's transition service rather than beside it.

## Requirements
### Requirement: Task status moves only along declared transitions

The system SHALL define, in one place, the set of legal moves between task statuses, and SHALL
refuse any status change that is not a member of that set. The eight statuses
(`pending`, `assigned`, `in_progress`, `completed`, `under_review`, `revision_needed`, `approved`,
`rejected`) remain as they are; what changes is that adjacency becomes declared rather than absent.

A refusal MUST name the task's current status and the statuses reachable from it, so a caller can
correct itself without guessing. A refused transition MUST leave the task and its history
unchanged.

Re-declaring the status a task already holds SHALL be accepted as a no-op and MUST NOT append a
history entry, so a retried or duplicated call does not manufacture a transition that never
happened.

#### Scenario: A legal move is accepted

- **WHEN** a caller moves a task from `in_progress` to `completed`
- **THEN** the task's status becomes `completed`
- **AND** the transition is recorded

#### Scenario: A skipped stage is refused

- **WHEN** an agent run moves a task from `in_progress` directly to `approved`
- **THEN** the request is refused with a typed error
- **AND** the error names `in_progress` as the current status and the statuses reachable from it
- **AND** the task's status is unchanged
- **AND** no transition is recorded

#### Scenario: Restating the current status changes nothing

- **WHEN** a caller sets a task's status to the status it already holds
- **THEN** the request succeeds
- **AND** no transition is recorded

#### Scenario: The transition map has a single definition

- **WHEN** the legal-transition map is read by the API, the MCP adapter, or a test
- **THEN** all of them resolve to the same declaration
- **AND** adding a status in one place without declaring its transitions fails a test rather than
  silently producing an unreachable status

### Requirement: A task may only be created in an entry status

The system SHALL restrict the status a task may be created with to the declared entry statuses
`pending` and `assigned`, and SHALL refuse creation in any other status. A lifecycle that can be
entered anywhere is not a lifecycle: without this, a caller reaches `approved` by creating a task
there rather than by transitioning to it, and no rule about transitions can prevent it.

This restriction SHALL hold identically over direct HTTP and MCP. Where one transport currently
exposes a status field that the other does not, the transports are brought into agreement by
narrowing the wider one, not by widening the narrower.

Creation SHALL NOT record a transition — a task's history begins with its first *move*, and its
entry status is already stated by the task itself.

#### Scenario: Creation in a non-entry status is refused

- **WHEN** a caller creates a task with status `approved`, `completed`, `under_review`,
  `revision_needed` or `rejected`
- **THEN** the request is refused
- **AND** no task is created

#### Scenario: Creation in an entry status succeeds

- **WHEN** a caller creates a task with status `pending` or `assigned`, or states no status
- **THEN** the task is created
- **AND** no transition is recorded

#### Scenario: Both transports refuse alike

- **WHEN** creation in a non-entry status is attempted over direct HTTP and through MCP
- **THEN** neither transport creates the task
- **AND** neither exposes a status field the other lacks

### Requirement: The operator can perform every transition reserved to them

Every transition the map reserves to the operator SHALL be reachable by the operator through the
application, not only through the API. A rule that grants the operator exclusive authority while
providing no surface on which to exercise it grants nothing.

The control SHALL offer only those transitions legal for the operator from the task's current
status, so an illegal move is not presented and then refused.

#### Scenario: The offered moves match the map

- **WHEN** the operator views a task in a given status
- **THEN** the transitions offered are exactly those the map declares legal for an operator from
  that status
- **AND** transitions reserved to no one, or legal only for agent runs, are not offered

#### Scenario: A reserved transition is reachable

- **WHEN** the operator wishes to reject a task at `pending`, or reopen an `approved` task
- **THEN** the application provides a way to do it

### Requirement: Some transitions are the operator's alone

The transition map SHALL declare, per edge, which kinds of actor may take it. The operator SHALL
have edges no agent run has; the operator SHALL NOT have permission to make a move the map does not
declare. Operator authority is expressed as additional legal transitions rather than as a bypass, so
every recorded history describes a legal sequence.

Specifically:

- Moving a task to `rejected` from any non-terminal status other than `under_review` SHALL be
  permitted to the operator only. An agent run MAY move a task to `rejected` from `under_review`,
  where rejection is a review outcome rather than a decision to abandon the work.
- `approved` and `rejected` SHALL be reopenable — `approved` to `revision_needed`, `rejected` to
  `pending` — by the operator only. No agent run may leave either status.

#### Scenario: An agent cannot abandon work in progress

- **WHEN** an agent run moves a task from `in_progress` to `rejected`
- **THEN** the request is refused
- **AND** the task's status is unchanged

#### Scenario: The operator can reject work at any point

- **WHEN** the operator moves a task from `pending`, `assigned`, `in_progress`, `completed` or
  `revision_needed` to `rejected`
- **THEN** the request succeeds
- **AND** the transition is recorded as an operator action

#### Scenario: An agent may reject at review

- **WHEN** an agent run other than the one that completed the task moves it from `under_review` to
  `rejected`
- **THEN** the request succeeds

#### Scenario: The operator can reopen a decided task

- **WHEN** the operator moves a task from `approved` to `revision_needed`, or from `rejected` to
  `pending`
- **THEN** the request succeeds
- **AND** the task's earlier transitions remain in its history

#### Scenario: An agent cannot reopen a decided task

- **WHEN** an agent run attempts to move a task out of `approved` or `rejected`
- **THEN** the request is refused

#### Scenario: The operator cannot make an undeclared move

- **WHEN** the operator attempts a transition the map does not declare for any actor
- **THEN** the request is refused on the same grounds as it would be for an agent run

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

### Requirement: An agent cannot approve the work it produced

The system SHALL refuse a transition to `approved` requested by an agent when that same **agent**
recorded the task's transition into `completed`. Author and reviewer MUST be distinct **agents**.

Distinctness is on agent identity, not run identity. Every turn an agent takes is a new run, so a
rule requiring only "a different run" is satisfied by an agent continuing its own work and forbids
nothing — observed in live use on 2026-08-10, when an agent completed a task on one run and
approved it on the next.

This rule binds agent runs only. The operator SHALL be permitted to approve work regardless of who
produced it — a single-operator project would otherwise be unable to approve anything — and the
history states that an operator did so.

#### Scenario: Self-approval by the completing agent is refused

- **WHEN** the agent that moved a task to `completed` requests the move to `approved`
- **THEN** the request is refused with a typed error stating that approval requires a different
  actor
- **AND** the task remains in its pre-request status
- **AND** no transition is recorded

#### Scenario: A new run of the same agent is still refused

- **WHEN** the agent that completed a task requests `approved` on a later run
- **THEN** the request is refused
- **AND** the refusal states that starting a new run does not make it a different actor

#### Scenario: A different agent may approve

- **WHEN** an agent other than the one that completed the task requests `approved`
- **AND** the transition is otherwise legal
- **THEN** the request succeeds

#### Scenario: The operator may approve any work

- **WHEN** the operator approves a task, including one they moved to `completed` themselves
- **THEN** the request succeeds
- **AND** the transition is recorded as an operator action

#### Scenario: Rejection and revision carry the same separation

- **WHEN** the agent that completed a task requests `rejected` or `revision_needed` on it
- **THEN** the request is refused on the same grounds as self-approval

### Requirement: Governance holds identically over HTTP and MCP

Transition validation, actor separation, and history recording SHALL be enforced at the shared
application layer, so the same rules apply whether a run acts over direct HTTP or through the MCP
adapter. The adapter MUST surface a refusal as a typed failure and MUST NOT convert it into an
empty or successful result.

#### Scenario: The same illegal move fails both ways

- **WHEN** an illegal transition is attempted over direct HTTP and the equivalent is attempted
  through MCP
- **THEN** both are refused
- **AND** both refusals carry the same meaning

#### Scenario: A refusal is not reported as success

- **WHEN** the MCP adapter receives a refused transition
- **THEN** the tool call reports a failure naming the reason
- **AND** it does not return a success payload

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
