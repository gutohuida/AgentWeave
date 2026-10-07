## MODIFIED Requirements

### Requirement: A dispatched review leaves the reviewable pool

Where a flow staffs a review, the firing SHALL take the task out of the pool a review may be staffed from by the review turn it queues, in the same commit, and SHALL NOT move the task or record a holder for it. A task with a review turn waiting for any agent, and a task a reviewer already holds, SHALL NOT be offered to any agent, including the agent the turn waits for.

The move into review and the holder are recorded by the dispatch of that turn, as
`task-lifecycle-governance` *Dispatching a review staffs the task, whichever path dispatched it*
requires. A firing that recorded them itself, before the dispatch, left a task held by a reviewer
that never ran whenever the dispatch was then refused, and every other reviewer the operator sent
was refused behind it. The waiting turn is what keeps the task out of the pool until then.

Where the review turn waiting for a task was refused on its last delivery, the firing SHALL NOT
staff another review for it, and SHALL surface the task, naming the agent and containing the
refusal's own sentence. A second review turn would be delivered behind the refused one and meet the
same refusal. Where that turn is given up on, or the operator withdraws it, the task SHALL return to
the pool on the next firing.

The flow SHALL NOT rely on the reviewer performing that move. A review turn that ends without
recording a verdict SHALL leave the task visible as held by its reviewer, and SHALL NOT return it
to the pool.

A task held by a reviewer SHALL remain visible as the flow's current work, naming the agent holding
it, for as long as it is held.

#### Scenario: A finished review is not staffed a second time

- **WHEN** a flow staffs an agent to review a completed task
- **AND** that review turn ends without moving the task
- **THEN** the next firing does not staff a review for that task
- **AND** the task is not offered to any other agent either

#### Scenario: A held task is still the flow's current work

- **WHEN** a flow has staffed a review and nothing else is ready
- **THEN** the flow does not report itself stalled
- **AND** the task is shown as current, naming the agent holding it

#### Scenario: A waiting review turn keeps the task out of the pool

- **WHEN** a flow staffs an agent to review a completed task, and that agent's review turn has not started
- **THEN** the task is still awaiting review, with its holder unchanged
- **AND** the next firing does not staff a review for that task
- **AND** the task is shown as the flow's current work, naming the agent the review turn waits for

#### Scenario: A refused flow review leaves the task awaiting review

- **WHEN** a flow staffs a review and the dispatch of that review turn is refused
- **THEN** the task is still awaiting review, with its holder and its transitions as they were before the firing
- **AND** the next firing surfaces the task, naming the agent and containing the refusal's own sentence
- **AND** the next firing does not staff another review for it

#### Scenario: A refused flow review does not stop another reviewer being sent

- **WHEN** a flow's review dispatch has been refused
- **AND** the operator then requests a review of the same task naming a different reviewer
- **THEN** that request is not refused on the ground that the task is already under review

#### Scenario: A review turn given up on returns the task to the pool

- **WHEN** a flow's review turn for a task is given up on after repeated refusals, or withdrawn by the operator
- **THEN** the next firing may staff a review for that task

#### Scenario: A held task is never re-staffed as ordinary work

- **WHEN** a task is held by a reviewer
- **THEN** no firing staffs that task as ordinary work
- **AND** no agent is fired at it in a workspace other than the review checkout

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

A review turn queued for an agent, within the hop budget, SHALL make that agent unavailable, whether
or not the agent is yet named on the task and whatever the task's status. The dispatch names the
reviewer, so until the turn starts the task names someone else; an agent the flow has already given
a review to is not free for another, and counting it free would queue a second review behind the
first.

The firing's refusal while its job's agent is busy, the agents a firing may give new work to, and
the agents a review may be given to SHALL all use this one definition. A firing refused because
nobody else is free, when the walk it refuses would have staffed somebody, is two answers to one
question. So is the converse: a firing let through because somebody is free, when its queue holds
nothing anybody could be given. `agent-loops`' *A firing is refused while its loop's agent is
already running* refuses that firing, and an agent freed by this requirement SHALL NOT be the reason
it proceeds.

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

#### Scenario: A freed agent does not let a busy agent's empty loop through

- **WHEN** a loop's job agent is running a turn, the only other agent is assigned only tasks that belong to no loop, and the loop's queue holds no task in a non-terminal status
- **AND** the loop's job fires
- **THEN** the firing is refused as busy
- **AND** no input is queued for the job's agent

#### Scenario: A reviewer whose review turn is waiting is not free

- **WHEN** a flow has staffed an agent to review a completed task, and that agent's review turn has not started
- **THEN** that agent is not counted among the agents free for new work or for review

#### Scenario: The roster still reports the task

- **WHEN** an agent is assigned a task in an active status that belongs to no loop
- **THEN** the roster still counts that task among the agent's active tasks
