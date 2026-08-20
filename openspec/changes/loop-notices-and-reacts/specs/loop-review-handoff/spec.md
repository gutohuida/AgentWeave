## ADDED Requirements

### Requirement: The Hub derives whether a finished task has a review in flight

The Hub SHALL determine whether a review is in flight for a task, without asking any agent and
without interpreting any free text. An agent may not sign off work it produced, so a task it
finishes needs a different actor before it can reach `approved`.

A review SHALL be considered in flight when either holds:

- the task is `completed` and a `Message` exists naming that task with type `"review"`; or
- the task is `under_review` and the agent recorded as moving it there is not the agent recorded as
  moving it to `completed`.

A review SHALL be considered **not** in flight in every other case where the task is `completed` or
`under_review`. The determination SHALL read only persisted rows and SHALL NOT parse an agent's
output.

#### Scenario: A completed task with a review message has a review in flight

- **WHEN** a task is `completed` and a message of type `"review"` naming that task exists
- **THEN** the Hub reports a review in flight for that task

#### Scenario: A completed task with no review message has none

- **WHEN** a task is `completed` and no message of type `"review"` names it
- **THEN** the Hub reports no review in flight for that task

#### Scenario: A message of another type does not count as a handoff

- **WHEN** a task is `completed` and the only message naming it has a type other than `"review"`
- **THEN** the Hub reports no review in flight for that task

#### Scenario: A task another agent moved to under_review has a review in flight

- **WHEN** a task is `under_review` and the agent that moved it there differs from the agent recorded
  as moving it to `completed`
- **THEN** the Hub reports a review in flight for that task

#### Scenario: A task its own author moved to under_review has none

- **WHEN** a task is `under_review` and the agent that moved it there is the same agent recorded as
  moving it to `completed`
- **THEN** the Hub reports no review in flight for that task

#### Scenario: The operator moving a task to under_review counts as a review in flight

- **WHEN** a task is `under_review` and the operator moved it there
- **THEN** the Hub reports a review in flight for that task

### Requirement: A firing re-briefs its own agent when a handoff did not happen

A firing SHALL spend its turn asking its own agent to perform the handoff, rather than claiming any
other task, when it finds the queue's most recently finished task has no review in flight.

The briefing SHALL name the task and state that it was completed without being sent for review. The
firing SHALL NOT choose a reviewer, SHALL NOT send a review message on the agent's behalf, and SHALL
NOT change the task's status.

A re-brief SHALL occupy the whole firing. No other queue item SHALL be claimed by the same firing.

#### Scenario: A finished task with no handoff is re-briefed instead of new work being claimed

- **WHEN** a loop fires, its queue holds a `completed` task with no review in flight and also holds a
  claimable `pending` task
- **THEN** the firing briefs its agent about the un-handed-off task
- **AND** the `pending` task is not claimed by that firing and keeps its status

#### Scenario: A re-brief does not alter the task

- **WHEN** a firing re-briefs its agent about an un-handed-off task
- **THEN** that task's status and assignee are unchanged by the firing

#### Scenario: A finished task with a review in flight is not re-briefed

- **WHEN** a loop fires and its queue's finished task has a review in flight
- **THEN** no re-brief is issued for that task

### Requirement: The re-brief is bounded and its count is recorded per task

The Hub SHALL record how many times a given task has been re-briefed. The count SHALL be held per
task, not per loop.

A firing SHALL NOT issue a re-brief for a task whose recorded count has reached the configured
maximum.

When a task is re-briefed and the handoff subsequently occurs, its recorded count SHALL be reset, so
that a task legitimately reaching `completed` again after a revision cycle starts from zero.

#### Scenario: Re-briefing stops at the maximum

- **WHEN** a task has been re-briefed the maximum number of times and the loop fires again
- **THEN** no further re-brief is issued for that task

#### Scenario: The count is per task

- **WHEN** two tasks in one loop each go un-handed-off
- **THEN** each carries its own re-brief count

#### Scenario: A successful handoff resets the count

- **WHEN** a task that was re-briefed acquires a review in flight, and later returns to `completed`
  with no review in flight after a revision cycle
- **THEN** its re-brief count starts again from zero

### Requirement: An exhausted re-brief is surfaced to the operator

The Hub SHALL make an exhausted re-brief visible to the operator, naming the task and the number of
attempts, when a task's count reaches its maximum and the handoff still has not happened.

The loop SHALL NOT be stopped or disabled by this condition. The operator resolving the situation —
by reviewing the task themselves, or by prompting a reviewer — SHALL be sufficient for the loop to
resume on a later firing with no further operator action.

#### Scenario: Exhaustion is surfaced

- **WHEN** a task's re-brief count reaches the maximum without a review in flight
- **THEN** the operator is notified, and the notification names the task and the attempt count

#### Scenario: Exhaustion does not end the loop

- **WHEN** a task's re-brief count reaches the maximum
- **THEN** the loop's job remains enabled and remains scheduled

#### Scenario: The loop resumes once the situation is resolved

- **WHEN** a task whose re-brief count was exhausted is subsequently approved by the operator
- **AND** the loop fires again
- **THEN** the firing claims the next claimable task in the queue

### Requirement: A project with no eligible reviewer surfaces rather than re-briefing indefinitely

A loop whose project holds no agent able to review its executor's work SHALL reach the surfacing
behaviour above rather than re-briefing without possibility of success. An agent cannot review its
own work, so a single-agent project has nobody able to advance a finished task.

#### Scenario: A single-agent project surfaces to the operator

- **WHEN** a loop's project contains no agent other than the loop's executor, and the executor
  finishes a task without handing it off
- **THEN** the re-brief bound is reached and the situation is surfaced to the operator
- **AND** the loop's job remains enabled
