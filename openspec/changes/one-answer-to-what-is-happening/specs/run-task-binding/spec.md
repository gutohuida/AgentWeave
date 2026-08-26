## ADDED Requirements

### Requirement: A run started to review a task binds to that task

The system SHALL bind a run started to review a task to the task under review, by the same binding
the runtime already performs for a run started to work a task, and SHALL NOT require a second
mechanism to do it.

A review turn is not one of the causes for which an unbound run is legitimate. Exploration,
conversation, questions and scheduled work have no task; a review has exactly one, and it is the
task whose work is being judged.

The instruction that gives a review turn its workspace SHALL remain distinct from the binding.
Selecting which commit a reviewer checks out and recording which task a run is about are different
questions, and a single value answering both would make an entry's two purposes inseparable.

Binding a review SHALL NOT move the task. The transitions available to a run from a task under
review do not include starting it, so binding records the association and changes no status.

Where a turn delivers both an item of work and a review, the binding SHALL be determined
deterministically by the same ordering already used to select among several items naming a task.

#### Scenario: A review run records the task it is reviewing

- **WHEN** a run is started to review a task
- **THEN** the run durably identifies that task
- **AND** the binding is readable for the run's whole life and after it ends

#### Scenario: Binding a review does not start the task

- **WHEN** a run binds to a task that is under review
- **THEN** the task's status is unchanged
- **AND** the task's assignee is unchanged

#### Scenario: A review turn is subject to the run boundary

- **WHEN** a run bound to a task under review ends
- **THEN** the boundary determination is performed for it, as for any other bound run

#### Scenario: The workspace instruction and the binding stay separate

- **WHEN** a review turn is prepared
- **THEN** the value selecting the commit to check out and the value recording the bound task are
  distinct
- **AND** neither is derived by reinterpreting the other

#### Scenario: A turn carrying both work and a review binds deterministically

- **WHEN** a turn delivers an item naming a task for work and an item naming a task for review
- **THEN** the run binds to exactly one of them
- **AND** the same input always produces the same binding

## MODIFIED Requirements

### Requirement: The response to a divergence is a policy set per task

The system SHALL let each task carry a divergence policy of `surface`, `retry`, or `escalate`, and
an escalation agent. A task with no policy set SHALL be treated as `surface`.

`surface` SHALL record and display the divergence and start nothing. `retry` SHALL start one further
run of the same agent, bound to the same task. `escalate` SHALL reassign the task to its escalation
agent and start a run of that agent, bound to the same task.

Defaulting to `surface` is required, not incidental: shipping this capability SHALL NOT cause any
existing task to start runs nobody asked for.

**The policy governs runs started to work a task, and SHALL NOT govern runs started to review one.**
A task carries one policy and, once review runs bind, can be the subject of two different failures —
work that was not done and a judgement that was not given — whose remedies are not the same. Applying
a policy chosen for the first to the second would act on the operator's behalf in a way they did not
ask for, and nothing would say it had happened.

`retry` is additionally redundant for a review: a run whose input was returned to the queue is
already re-delivered, and that is what answers a review whose process died. What remains for `retry`
to act on is a reviewer that completed its turn and gave no verdict, where running the same reviewer
against the same work is the least likely response to change the outcome.

How a review that records no verdict is answered is stated by the capability that owns flows, not
here.

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

#### Scenario: A review is not retried by the task's policy

- **WHEN** a run started to review a task whose policy is `retry` ends without recording a verdict
- **THEN** no further run is started by that policy

#### Scenario: A review is not escalated by the task's policy

- **WHEN** a run started to review a task whose policy is `escalate` ends without recording a verdict
- **AND** the task names an escalation agent
- **THEN** the task is not reassigned to that agent by that policy
- **AND** no run is started by that policy
