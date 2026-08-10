# run-task-binding

## Purpose

Which task a run is working on, who decides that, what binding does to the task's status, and what
happens when a run ends holding work nobody moved.

Established by `openspec/changes/2026-08-10-run-task-binding/`. Before it, `Run` carried project,
agent, session, conversation, pid and heartbeat and nothing about the work, so a task's status
stayed current only if an agent remembered to say so — not a discipline problem but a missing edge
in the data model.

Where `task-lifecycle-governance` governs **validity** — that a recorded transition is legal,
attributed, and made by an entitled actor — this capability governs **liveness**: that a transition
happens at all when reality changes. B1 made it impossible to record a wrong transition and could
do nothing about a missing one, because an agent that does the work and never touches the ledger
asks for nothing and so passes every check.

Both mechanisms sit at boundaries AgentWeave owns for every runner — process start and process end
— rather than inside any agent, which is what makes them enforcement rather than instruction, and
why no part of this depends on a runner hook.

It is also the prerequisite for B3: evidence is produced *by a run*, about *a task*, and that edge
did not exist.

## Requirements

### Requirement: A run carries at most one task binding

The system SHALL record, on each run, the single task that run was started for, or nothing. A run
SHALL NOT be bound to more than one task.

A run with no binding is legitimate: exploration, conversation, questions, and scheduled work are
real work with no task.

#### Scenario: A run started for a task records it

- **WHEN** a run is started from a cause that names a task
- **THEN** the run durably identifies that task
- **AND** the binding is readable for the run's whole life and after it ends

#### Scenario: A run started without a cause naming a task is unbound

- **WHEN** the operator starts a run by talking to an agent, or a scheduled job triggers one
- **THEN** the run records no task
- **AND** the run is not subject to any check that depends on a binding

#### Scenario: A second task cannot be added to a bound run

- **WHEN** anything attempts to bind a second task to a run that is already bound
- **THEN** no such path exists

### Requirement: Only the runtime binds a run to a task

The system SHALL set a run's binding itself, from the cause that started the run. No agent-facing
operation — over HTTP or MCP — SHALL create, change, or remove a run's binding.

An enforcement mechanism its subject can decline is not enforcement: an agent able to bind itself is
an agent able to never bind, and an unbound run is never divergent.

#### Scenario: The agent surface offers no binding operation

- **WHEN** an agent enumerates the operations available to it
- **THEN** no operation binds a run to a task, rebinds it, or clears a binding

#### Scenario: An agent cannot escape a binding the runtime made

- **WHEN** a run is bound and the agent attempts to remove or change that binding by any available
  means
- **THEN** the binding is unchanged

### Requirement: A delegation that names a task binds the run that receives it

The system SHALL carry a task named on an agent-to-agent delegation through the receiving agent's
inbound queue and onto the run that delivers it.

The task id SHALL be validated against the sending run's project when the delegation is made. A task
id that does not resolve SHALL be refused with a message naming the problem, and the delegation
SHALL still be deliverable without a binding rather than lost.

#### Scenario: A delegated task reaches the receiving run

- **WHEN** an agent delegates work naming a task in its project
- **AND** the receiving agent's next turn delivers that item
- **THEN** the receiving run is bound to that task

#### Scenario: An unresolvable task id is refused, not silently dropped

- **WHEN** a delegation names a task that does not exist or belongs to another project
- **THEN** the caller receives an error naming which task id failed and why

#### Scenario: Several delivered items naming different tasks resolve deterministically

- **WHEN** one turn delivers several queued items and more than one names a task
- **THEN** the run is bound to the task named by the earliest queued item that names one
- **AND** the same delivery always produces the same binding

### Requirement: The operator can start a bound run from a task

The system SHALL let the operator start work on a task directly from the task, producing a run bound
to it.

#### Scenario: Starting work from a task binds the run

- **WHEN** the operator starts work on a task and names the agent
- **THEN** a run for that agent is started bound to that task

#### Scenario: The binding is visible to the operator

- **WHEN** the operator views a run
- **THEN** the task it is bound to is shown, or its absence is evident

### Requirement: Binding advances the task without asking the agent

The system SHALL, when binding a run to a task from whose current status an agent run may reach
`in_progress`, move the task to `in_progress` and attribute the move to the binding run.

The move SHALL be applied through the same transition machine that governs every other status
change, so no legality rule, actor rule, or later gate is bypassed by the runtime path.

#### Scenario: A pending task starts when a run binds to it

- **WHEN** a run binds to a task in `pending` or `assigned`
- **THEN** the task moves to `in_progress`
- **AND** the transition is recorded naming the binding run and its agent
- **AND** the agent was not asked to make it

#### Scenario: A task already in progress is not moved again

- **WHEN** a run binds to a task already in `in_progress`
- **THEN** no transition is recorded

#### Scenario: Binding a task with no legal path to in_progress still binds

- **WHEN** a run binds to a task in a status from which an agent run cannot reach `in_progress`
- **THEN** the run is bound
- **AND** no transition is recorded
- **AND** the binding is not refused

#### Scenario: The runtime cannot make a move an agent run could not

- **WHEN** the runtime attempts the automatic move
- **THEN** it is subject to the same legality check as an agent-requested move

### Requirement: A run that ends without moving its task is divergent

The system SHALL determine, when a bound run ends, whether that run caused any status transition of
its bound task other than the runtime's own automatic one. A bound run that caused none SHALL be
recorded as divergent.

The determination SHALL be made at the run boundary — which the system owns for every runner —
rather than inside the agent, and SHALL NOT depend on any runner-specific mechanism.

A run's exit status SHALL NOT affect whether it is checked. A run that crashed, failed, or was
interrupted is still a run that ended holding a task nobody moved; the record SHALL name the exit
status so that a crash is distinguishable from a completed run that forgot.

A run whose queued input was returned to the queue SHALL NOT be recorded as divergent. That input
is about to be delivered to a new run bound to the same task, so nothing has been dropped —
recording a divergence would misdescribe it, and under an active policy would start a run racing
the redelivery.

#### Scenario: A run that completes its task is not divergent

- **WHEN** a bound run moves its task to `completed` and ends
- **THEN** no divergence is recorded

#### Scenario: A run that ends having moved nothing is divergent

- **WHEN** a bound run ends and the only transition it caused was the automatic one made when it was
  bound
- **THEN** a divergence is recorded naming the run, the task, the task's status at run end, and the
  run's exit status

#### Scenario: An unbound run is never divergent

- **WHEN** a run with no binding ends
- **THEN** no divergence is recorded

#### Scenario: A crashed run is checked like any other

- **WHEN** a bound run's process dies and the run is later reconciled to an ended state
- **AND** it had no queued input to return
- **THEN** the divergence check is performed
- **AND** the record names the exit status

#### Scenario: Work handed back to the queue is not a divergence

- **WHEN** a bound run ends and its delivered input is returned to the agent's queue
- **THEN** no divergence is recorded
- **AND** no run is started in response

#### Scenario: A divergence closes when the work reaches the ledger

- **WHEN** an open divergence exists for a task and any actor later moves that task
- **THEN** the divergence is recorded as resolved
- **AND** the record of it having occurred is retained

### Requirement: Every divergence is recorded durably

The system SHALL persist one immutable record per divergence, naming the run, the task, the policy
applied, the outcome, and the run started in response where one was. Records MUST NOT be updated
except to mark resolution, and MUST NOT be deleted by any application path.

Broadcasting a divergence is not sufficient: the operator SHALL be able to see divergences that
occurred while they were not watching, and to ask how often an agent has diverged.

#### Scenario: A divergence survives the session it happened in

- **WHEN** a divergence occurs and the operator later opens the project
- **THEN** the divergence is visible with its task, run, policy, and outcome

#### Scenario: Ordering is exact

- **WHEN** several divergences are recorded within the same instant
- **THEN** reading them back yields the order in which they occurred

### Requirement: The response to a divergence is a policy set per task

The system SHALL let each task carry a divergence policy of `surface`, `retry`, or `escalate`, and
an escalation agent. A task with no policy set SHALL be treated as `surface`.

`surface` SHALL record and display the divergence and start nothing. `retry` SHALL start one further
run of the same agent, bound to the same task. `escalate` SHALL reassign the task to its escalation
agent and start a run of that agent, bound to the same task.

Defaulting to `surface` is required, not incidental: shipping this capability SHALL NOT cause any
existing task to start runs nobody asked for.

#### Scenario: The default starts nothing

- **WHEN** a run bound to a task with no policy set diverges
- **THEN** the divergence is recorded and displayed
- **AND** no run is started

#### Scenario: Retry runs the same agent again

- **WHEN** a run bound to a task whose policy is `retry` diverges
- **THEN** one further run of the same agent is started bound to that task
- **AND** that run is given the task, its current status, and the transitions available to it

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

### Requirement: A divergence response runs at most one hop

The system SHALL record, on a run started in response to a divergence, the run whose divergence
caused it. A run carrying that reference SHALL NOT itself trigger a retry, and SHALL NOT trigger an
escalation unless it was itself started by a retry.

A `retry` whose own run diverges SHALL fall through to `escalate` when the task names an escalation
agent, and to `surface` otherwise. No sequence of divergences SHALL be able to start an unbounded
number of runs: a chain SHALL start at most one retry and at most one escalation before surfacing.

The escalation limit is required, not incidental. An escalated run's task still carries the same
policy and the same escalation agent, so without it a divergence of that run escalates to the same
agent again, and does so forever.

The bound applies to a chain, not to a task's lifetime: a run that makes real progress ends the
chain, and a later independent run that diverges may retry again.

#### Scenario: A retry that also diverges does not retry again

- **WHEN** a run started in response to a divergence itself diverges
- **THEN** no further retry is started

#### Scenario: A retry that diverges escalates when it can

- **WHEN** a run started by `retry` diverges
- **AND** the task names an escalation agent
- **THEN** the work is escalated to that agent

#### Scenario: An escalated run that diverges does not escalate again

- **WHEN** a run started by `escalate` itself diverges
- **AND** the task still names the same escalation agent
- **THEN** the divergence is surfaced
- **AND** no further run is started

#### Scenario: Progress resets the chain

- **WHEN** a run started in response to a divergence moves its task
- **AND** a later independent run bound to the same task diverges
- **THEN** that later divergence is answered by the task's policy in full, including retry

### Requirement: The operator sets and sees divergence handling where the task is

The system SHALL let the operator read and change a task's divergence policy and escalation agent
from the task itself, and SHALL show on the task that a divergence has occurred and whether it is
still open.

#### Scenario: Policy is editable from the task

- **WHEN** the operator opens a task
- **THEN** its divergence policy and escalation agent are visible and changeable there

#### Scenario: An escalation agent is chosen from the project's agents

- **WHEN** the operator sets an escalation agent
- **THEN** the choices offered are agents that exist in the project

#### Scenario: An open divergence is visible on the task

- **WHEN** a task has an unresolved divergence
- **THEN** the task shows it
- **AND** the indicator clears when the divergence resolves
