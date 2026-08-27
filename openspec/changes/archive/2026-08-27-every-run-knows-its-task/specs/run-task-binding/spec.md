## ADDED Requirements

### Requirement: A flow firing that claims a task binds the run it starts

Where a flow firing claims a task and starts a run to work it, the system SHALL bind that run to the
claimed task. The binding SHALL be carried on the queue entry the firing stages, so that the run that
delivers the entry is bound by the same mechanism as every other cause that names a task.

This SHALL apply to a firing that staffs ordinary work. A firing that staffs a review already names
the task under review, and SHALL continue to name it as a review rather than as work — the two are
distinct facts about the turn and SHALL NOT be written to the same field.

A firing that claims no task SHALL start an unbound run, as before. There is no task for such a run
to have neglected.

#### Scenario: A flow work firing starts a bound run

- **WHEN** a flow firing claims a task and stages an ordinary work turn for an agent
- **THEN** the queued entry names that task
- **AND** the run that delivers the entry is bound to that task

#### Scenario: The claimed task starts when the run does

- **GIVEN** a flow firing has claimed a task and moved it to `assigned`
- **WHEN** the run it started is bound to that task
- **THEN** the task moves to `in_progress` without the agent being asked to move it

#### Scenario: A flow work run that moves nothing is divergent

- **GIVEN** a flow firing that claimed a task and started a bound run
- **WHEN** that run ends having caused no status transition of the task beyond the automatic one
- **THEN** a divergence is recorded naming the run and the task

#### Scenario: A review firing binds as a review, not as work

- **WHEN** a flow firing staffs a review of a completed task
- **THEN** the queued entry names that task as the task under review
- **AND** the entry does not name it as ordinary work

#### Scenario: A firing that claims nothing starts an unbound run

- **WHEN** a flow fires with no task available to claim
- **THEN** the run it starts is bound to no task
- **AND** no divergence is recorded when that run ends

### Requirement: A divergence announces itself according to whether it needs attention

The system SHALL derive the severity of the event announcing a divergence from whether the condition
is one the operator can act on, rather than emitting every divergence at a fixed severity.

A divergence whose task is still held by the same agent, under a flow that will fire again, SHALL be
announced as information. Such a turn is work that is not finished yet, which is the condition the
system already relies on when it closes an open divergence on the next actor transition — announcing
it as a warning states a problem the system does not believe it has.

A divergence whose task has been released by its agent, whose run did not end cleanly, or whose task
has reached a terminal status SHALL be announced as a warning. Nothing further is coming for that
task without the operator.

#### Scenario: An intermediate turn of unfinished work is information

- **GIVEN** a task held by an agent under a flow that has not stopped
- **WHEN** a run bound to that task ends having moved nothing, and the task is still held by the same
  agent
- **THEN** the divergence is announced at information severity

#### Scenario: An agent that walked away is a warning

- **GIVEN** a task whose assignee was cleared, or whose run ended in a failed state
- **WHEN** the divergence for that run is recorded
- **THEN** the divergence is announced at warning severity

#### Scenario: Severity does not change what is recorded

- **WHEN** a divergence is announced at information severity
- **THEN** the durable divergence record is written exactly as it is for a warning
- **AND** it names the run, the task, the policy applied, and the outcome

### Requirement: Resolving a divergence is as visible as opening one

The system SHALL emit an event when an open divergence is resolved, naming the task and how many
open divergences were closed.

An announced condition whose answer is silent cannot be read: an operator scrolling back sees a
divergence that was never withdrawn, and has no way to tell a resolved condition from a standing
one. Resolution SHALL be visible in the same place the divergence was announced.

#### Scenario: Work reaching the ledger closes visibly

- **GIVEN** one or more open divergences on a task
- **WHEN** any actor moves that task
- **THEN** the divergences are recorded as resolved
- **AND** an event is emitted naming the task and the number closed

#### Scenario: Nothing open emits nothing

- **WHEN** a task is moved and it has no open divergences
- **THEN** no resolution event is emitted

## MODIFIED Requirements

### Requirement: The response to a divergence is a policy set per task

The system SHALL let each task carry a divergence policy of `surface`, `retry`, or `escalate`, and
an escalation agent. A task with no policy set SHALL be treated as `surface`.

`surface` SHALL record and display the divergence and start nothing. `retry` SHALL start one further
run of the same agent, bound to the same task. `escalate` SHALL reassign the task to its escalation
agent and start a run of that agent, bound to the same task.

`retry` SHALL NOT answer the divergence of a run that a live flow firing started on ordinary work.
A flow fires the task again on its next tick, so the flow is already the retry; starting one on top
of it produces two runs for one task, each unaware of the other. Such a divergence SHALL be surfaced
instead, and SHALL be recorded as having been governed by the flow rather than by the task's policy,
so that the record never shows `retry` beside an outcome nothing retried. `escalate` and `surface`
SHALL continue to apply to flow work unchanged: an escalation moves the work to a different agent,
which is not something the flow's next firing does.

Defaulting to `surface` is required, not incidental: shipping this capability SHALL NOT cause any
existing task to start runs nobody asked for.

#### Scenario: The default starts nothing

- **WHEN** a run bound to a task with no policy set diverges
- **THEN** the divergence is recorded and displayed
- **AND** no run is started

#### Scenario: Retry runs the same agent again

- **WHEN** a run bound to a task whose policy is `retry` diverges
- **AND** that run was not started by a flow firing on ordinary work
- **THEN** one further run of the same agent is started bound to that task
- **AND** that run is given the task, its current status, and the transitions available to it

#### Scenario: A flow's own work turn is not retried on top of the flow

- **GIVEN** a task whose divergence policy is `retry`, worked under a flow that has not stopped
- **WHEN** a run that flow started on ordinary work for that task diverges
- **THEN** no further run is started in response
- **AND** the divergence is surfaced
- **AND** the record names the flow as what governed it, not `retry`

#### Scenario: Escalation still applies to a flow's work turn

- **GIVEN** a task whose divergence policy is `escalate` and which names an escalation agent, worked
  under a flow
- **WHEN** a run that flow started on ordinary work for that task diverges
- **THEN** the task is reassigned to the escalation agent
- **AND** a run of that agent is started bound to the task

#### Scenario: Escalation routes the work to another agent

- **WHEN** a run bound to a task whose policy is `escalate` diverges
- **AND** the task names an escalation agent
- **THEN** the task is reassigned to that agent
- **AND** a run of that agent is started bound to the task
- **AND** the previous assignee is recorded

#### Scenario: Escalation with no agent named falls back

- **WHEN** a task whose policy is `escalate` names no escalation agent
- **THEN** the divergence is surfaced
- **AND** no run is started
