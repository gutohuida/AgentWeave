## ADDED Requirements

### Requirement: An active task makes its assignee unavailable only while something will move it

A flow SHALL count an agent as holding work only for a task in an active status that belongs to a loop that has neither ended nor been archived, or on which the agent has a turn running or queued within the project's hop budget.

An assignee is a record of who holds a task, not evidence that anything will ever work it. A loop
walks only its own queue, so a task that belongs to no loop is never started, moved or closed by any
firing. Counting such a task as holding work withdraws its assignee from every flow in the project
for as long as the task exists, which nothing but working the task can end. That is a ratchet: each
follow-up an agent files outside a loop and assigns to a colleague costs the project that colleague.

A task in a loop that has not ended is a real queue its loop will reach, and it SHALL hold its
assignee, so that an agent with work waiting in one loop is not given more by another. This holds
while the loop's job is paused, because a pause can be undone and an ending cannot. A task in a loop
that has ended SHALL NOT hold its assignee, because no firing will walk that loop again. A task in a
loop the operator has archived SHALL NOT hold its assignee either, whether or not the loop ended
first: archiving retires the loop and hides it from the listing that would show why its agents were
held.

A turn running or queued for the task's assignee, naming that task, SHALL make the task hold its
assignee whether or not the task belongs to a loop, and input naming the same task that is queued
for other agents SHALL NOT prevent it. A turn queued for a different agent SHALL NOT make the task
hold its assignee. Input queued past the project's hop budget SHALL NOT count as a turn queued,
because it is delivered only if the operator releases it.

The firing's refusal while its job's agent is busy, the agents a firing may give new work to, and
the agents a review may be given to SHALL all use this one definition. A firing refused because
nobody else is free, when the walk it refuses would have staffed somebody, is two answers to one
question.

This requirement changes only which agents a flow may staff. It SHALL NOT change a task's status, its
assignee or its loop, and it SHALL NOT change what the roster reports an agent as holding.

#### Scenario: A task outside every loop does not make its assignee busy for review

- **WHEN** an agent is assigned a task in an active status that belongs to no loop, and no turn is running or queued for it on that task
- **AND** a flow fires with a completed task to review, declaring no reviewer, whose author is another agent
- **THEN** the agent may be selected for the review

#### Scenario: A task outside every loop does not make its assignee busy for new work

- **WHEN** a flow fires with a startable unassigned task, its job's agent is already selected or busy, and the only other agent is assigned only tasks that belong to no loop
- **THEN** that other agent is staffed onto the startable task

#### Scenario: A task in a loop that has not ended holds its assignee

- **WHEN** an agent is assigned a task in an active status that belongs to a loop that has not ended
- **THEN** it is not counted among the agents free for new work or for review

#### Scenario: A paused loop's task still holds its assignee

- **WHEN** an agent is assigned a task in an active status that belongs to a loop whose job the operator has paused
- **THEN** it is not counted among the agents free for new work or for review

#### Scenario: An ended loop's task holds nobody

- **WHEN** an agent is assigned a task in an active status that belongs only to a loop that has ended
- **THEN** that task does not stop the agent being counted free

#### Scenario: A turn queued on a task outside every loop holds its assignee

- **WHEN** an agent is assigned a task that belongs to no loop, and input naming that task is queued for that agent
- **THEN** it is not counted among the agents free for new work or for review

#### Scenario: A turn queued for someone else does not hold the assignee

- **WHEN** an agent is assigned a task that belongs to no loop, and input naming that task is queued only for a different agent
- **THEN** that task does not stop the assignee being counted free

#### Scenario: Input for someone else does not hide the assignee's own

- **WHEN** an agent is assigned a task that belongs to no loop, input naming that task is queued for that agent, and input naming the same task is also queued for a different agent
- **THEN** it is not counted among the agents free for new work or for review, whichever agent's input the Hub reads first

#### Scenario: Input past the hop budget does not hold the assignee

- **WHEN** an agent is assigned a task that belongs to no loop, and the only input naming that task queued for it is past the project's hop budget
- **THEN** that task does not stop the agent being counted free

#### Scenario: An archived loop's task holds nobody

- **WHEN** an agent is assigned a task in an active status that belongs only to a loop the operator archived without ending it
- **THEN** that task does not stop the agent being counted free

#### Scenario: The busy refusal agrees with the walk

- **WHEN** a flow's job agent is running a turn, and the only other agent is assigned only tasks that belong to no loop
- **AND** the flow has a startable task
- **THEN** the firing is not refused as busy
- **AND** the other agent is staffed

#### Scenario: The roster still reports the task

- **WHEN** an agent is assigned a task in an active status that belongs to no loop
- **THEN** the roster still counts that task among the agent's active tasks

## MODIFIED Requirements

### Requirement: A flow resolves a reviewer by declaration, then by availability

Where a task declares a reviewer, the Hub SHALL attempt to resolve that declaration to an agent in
this project, and SHALL do so by the same resolution the rest of the product already uses for a
declared reviewer, never a second one.

**Where a declaration exists and does not resolve, the Hub SHALL NOT substitute a different agent.**
It SHALL surface the declaration and the reason it failed, and the review falls to the operator. A
declaration that named someone is not the same fact as no declaration at all: quietly running the
review under a different name tells the operator that the agent they named checked the work when it
did not.

Where **no** reviewer is declared, the Hub SHALL select any agent that is not running a turn, whose
queue is not held by a refusal of the provider's usage allowance (`agent-conversation-workspace`),
and that holds no work, where holding is what *An active task makes its assignee unavailable only
while something will move it* defines. An agent assigned a task that nothing will ever move is not
holding work, and passing it over would leave the review unstaffed for a reason no firing can
clear.

A held agent is passed over for the reason a running one is: the scheduler would refuse to start the
review until the hold ends. Which tasks make an agent unavailable is not changed by this clause.

Where no declaration exists and no agent is available, the flow SHALL surface that it could not
staff the step, naming the task. The flow's job SHALL remain enabled and SHALL remain scheduled.

**This resolution SHALL also answer a review that was staffed and then gave no verdict**, so that a
failed review is met by the same rule that staffed it rather than by a second mechanism. Where the
reviewer that failed had been **declared**, the Hub SHALL surface it and SHALL NOT substitute
another agent — the reasoning above does not weaken because the declared agent ran and said nothing.
Where the reviewer that failed had been selected by **availability**, the Hub SHALL resolve again,
excluding the agent that failed. **That second resolution SHALL exclude the work's author by the
same determination the first one used**, and SHALL NOT substitute a narrower one: where no agent is
recorded as completing the task, it SHALL exclude every agent any record associates with the task,
exactly as the resolution that staffed the review did. A second resolution that rules out only the
reviewer who said nothing offers the work to an agent the first resolution had already excluded as
its author, and the silence of one reviewer is not a fact about who wrote the work.

**Where that second resolution can staff nobody, the reason it surfaces SHALL describe the
exclusion it actually applied.** Widening who is excluded without widening the sentence that
explains the exclusion produces a reason stating that an excluded agent completed the task on a
task no agent completed — which this capability already forbids for the first resolution, and the
second one surfaces its reason to the same operator through the same event. The two resolutions
SHALL NOT come to different accounts of one task.

**The Hub SHALL NOT resolve, as a task's reviewer, an agent that could not record a verdict on it.**
An agent is barred from judging work it completed, so naming it would produce a review refused on
arrival; the resolution SHALL exclude it rather than discover the refusal afterwards.

#### Scenario: The author is not offered the work by the second resolution either

- **WHEN** a reviewer staffed for a task the operator moved to `completed` ends its turn without
  recording a verdict, and the Hub resolves a replacement
- **THEN** an agent that any record associates with that task is not selected
- **AND** the agent that gave no verdict is not selected

#### Scenario: The second resolution's surfaced reason does not claim an agent completed the work

- **WHEN** a reviewer staffed for a task the operator moved to `completed` ends its turn without
  recording a verdict, and no agent is left for the Hub to resolve
- **THEN** the surfaced reason states that the excluded agents worked on the task
- **AND** it does not state that any of them completed it

#### Scenario: A declared reviewer that resolves is used

- **WHEN** a task declares a reviewer that resolves to an eligible agent
- **THEN** that agent is fired for the review

#### Scenario: An unresolvable declaration is surfaced, never substituted

- **WHEN** a task declares a reviewer that resolves to no agent in this project
- **THEN** no other agent is fired for that review
- **AND** the declared name and the reason it did not resolve are surfaced to the operator

#### Scenario: An undeclared review falls back to availability

- **WHEN** a task declares no reviewer at all
- **THEN** an agent that is not running, is not held, and holds no work is fired for the review

#### Scenario: A busy agent is not selected

- **WHEN** an otherwise eligible agent is running a turn, is held by a refusal of the provider's
  usage allowance, or holds work as *An active task makes its assignee unavailable only while
  something will move it* defines
- **THEN** it is not selected while another eligible agent is available

#### Scenario: An agent whose only task is outside every loop is selected

- **WHEN** a task declares no reviewer, and the only agent other than its author is assigned a task
  in an active status that belongs to no loop, with no turn running or queued on it
- **THEN** that agent is fired for the review
- **AND** the flow does not surface that it could not staff the step

#### Scenario: No eligible agent surfaces rather than stalling silently

- **WHEN** no agent can be resolved or found for a task
- **THEN** the operator is notified, naming the task
- **AND** the flow's job remains enabled and scheduled

#### Scenario: A single-agent project reaches the same outcome by the same rule

- **WHEN** a flow's project holds only the agent that completed the task, and no reviewer is
  declared
- **THEN** the flow surfaces that it could not staff the review
- **AND** no special-case path is taken to reach that outcome

#### Scenario: A declared reviewer that gave no verdict is surfaced, not replaced

- **WHEN** a review by a declared reviewer ends without recording a verdict
- **THEN** no other agent is fired for that review
- **AND** the operator is told which declared reviewer gave no verdict, naming the task

#### Scenario: An availability-picked reviewer that gave no verdict is replaced

- **WHEN** a review by an agent selected on availability ends without recording a verdict
- **THEN** the reviewer is resolved again by the same rule
- **AND** the agent that gave no verdict is not selected

#### Scenario: A second failure with nobody left surfaces

- **WHEN** an availability-picked review gives no verdict and no other eligible agent exists
- **THEN** the flow surfaces that it could not staff the review, naming the task
- **AND** the flow's job remains enabled and scheduled

#### Scenario: The agent that completed the work is never resolved as its reviewer

- **WHEN** a reviewer is resolved for a task
- **THEN** the agent that moved that task to completed is not selected
- **AND** this holds whether the reviewer is being resolved for the first time or after a failure
