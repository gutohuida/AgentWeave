## MODIFIED Requirements

### Requirement: A completed task is claimable by an agent that did not complete it

The Hub SHALL allow a task in `completed` to be claimed by an agent other than the one recorded as moving it to `completed`, and SHALL NOT allow it to be claimed by that agent.

This SHALL use the same determination of who completed a task that author/reviewer separation uses
for reaching a review outcome, so that a task the Hub offers to an agent is never one that agent
would then be refused for approving.

**Where the recorded completion names no agent, the Hub SHALL distinguish a completion made by the
operator from no recorded completion at all.** These are different facts about a task and only one of
them is an absence. A task the operator moved to `completed` has provenance — a person did it — and
treating it as unattributable withholds review from precisely the work the operator involved
themselves in.

Where the operator is recorded as completing a task, the Hub SHALL allow it to be claimed by any
agent that has not worked on that task, and SHALL NOT allow it to be claimed by an agent that has. No
agent completed such a task, so no agent's own sign-off is at stake; but an agent may still have
produced the work, and offering it that work to review is self-approval reached by a different route.

**The agents that have worked a task SHALL be determined from its recorded transitions together with
the agent it is assigned to, and SHALL NOT be determined from either alone.** The history is required
because who holds a task is overwritten by every reassignment, so a task returned for revision and
picked up by a second agent has two authors and only the history names both. The assignee is required
because an agent takes a transition only when it *changes* a task's status: an agent working a task
that is already in progress records nothing, so a task the operator started by hand and then marked
finished can carry a full history that names no agent while an agent produced all of the work. Either
term alone leaves a task whose author the Hub can rule out and does not.

Where no completion is recorded at all, the task SHALL remain claimable by nobody. Nothing rules any
agent out, so nothing rules the author out either.

#### Scenario: A different agent may take a completed task

- **WHEN** a flow fires and a queued task is `completed`, and an eligible agent is not the one that
  completed it
- **THEN** that agent may be fired for it

#### Scenario: The author may not take back its own completed task

- **WHEN** the only available agent is the one that completed the task
- **THEN** it is not fired for that task
- **AND** the firing reports that it could not staff the review

#### Scenario: Claimability and the approval guard agree

- **WHEN** an agent is fired for a task in `completed`
- **THEN** that agent moving the task to a review outcome is not refused by author/reviewer
  separation

#### Scenario: An agent that did not work operator-completed work may take it

- **WHEN** a task's most recent completion was recorded by the operator, and an agent has no
  recorded transition on that task
- **THEN** that agent may be fired for it

#### Scenario: An agent that worked operator-completed work may not take it

- **WHEN** a task's most recent completion was recorded by the operator, and an agent is recorded on
  one of that task's earlier transitions
- **THEN** that agent is not fired for it

#### Scenario: An agent that worked the task without moving it may not take it either

- **WHEN** a task's most recent completion was recorded by the operator, and the task is assigned to
  an agent that no transition on that task names
- **THEN** that agent is not fired for it

#### Scenario: A task with no recorded completion stays claimable by nobody

- **WHEN** a task is `completed` and no transition into that status is recorded for it
- **THEN** no agent is fired for it

## ADDED Requirements

### Requirement: A task a flow declines to staff for review is named to the operator

A flow SHALL record a staffing outcome naming the task for every task it considers for review and does not staff, and SHALL NOT drop such a task from its firing without recording anything.

A firing that drops a task silently leaves the operator with a description of the queue in place of a
description of the task. The stall is then attributed to how many tasks are open and in which
statuses, which is a fact about the queue and not the thing the operator can act on. Measured live: a
flow whose only task the operator had marked finished reported *"no claimable task among 1 open (1
completed)"* on every firing, forever, while the actual cause was a property of that one task and had
a remedy.

The recorded outcome SHALL name what the operator can do about it. Where a task carries no recorded
completion, the outcome SHALL say so and SHALL name reviewing it directly as the way forward, because
nothing a flow can do will give that task provenance it never had.

The outcome SHALL be recorded as one the operator must resolve, and SHALL NOT be recorded as work in
flight or as deferred to a later firing. A task no firing can staff is not held by anybody and is not
picked up by the next tick; recording it as either tells the operator to wait for something that will
not happen.

#### Scenario: A task with no recorded completion is surfaced, naming the task

- **WHEN** a flow fires on a queue holding a `completed` task for which no completion is recorded
- **THEN** the operator is notified, naming the task
- **AND** the notification states that the task has no recorded completion
- **AND** the flow's job remains enabled and scheduled

#### Scenario: The stall reason describes the task rather than the queue

- **WHEN** that firing is refused because nothing in the queue could be claimed
- **THEN** the recorded reason is the one naming the task, not a count of open tasks by status

#### Scenario: Nothing is reported as held by a reviewer

- **WHEN** a flow declines to staff a review for a task
- **THEN** that task is not recorded as being worked by any agent

### Requirement: A flow staffs a review for work the operator finished

A flow SHALL resolve a reviewer, through the ordinary reviewer ladder, for a task whose most recent completion the operator recorded.

The operator marking a task finished is a judgement that the work is done, which is a different
question from whether it is right. Withholding review from it removes the flow's own second half at
the moment the operator involved themselves, and leaves them no way forward: such a task can reach
only `rejected` or `under_review`, and moving it to `under_review` by hand offers it to nobody.

**The ladder SHALL exclude every agent that has worked the task**, and SHALL do so in place of
excluding the agent that completed it, since no agent did. An agent that produced work the operator
then marked finished is that work's author in every sense the review boundary is about, and the
transition guards permit its verdict precisely because they cannot attribute the completion — so an
exclusion derived only from the completion would let two permissive rules agree on a self-approval.
The exclusion SHALL be the same determination claimability uses, or a task the flow offers an agent
is one the flow would then refuse to staff onto it.

Everything else about the resolution SHALL be unchanged: the declaration outranks availability, an
unresolvable declaration is surfaced and never substituted, and a task with nothing to check out is
surfaced with that as its reason rather than with a reason about who completed it.

Where the exclusion leaves nobody, the flow SHALL surface that it could not staff the review, naming
the task, as it does when the author is known.

**A surfaced reason SHALL NOT state that an excluded agent completed the task where no agent
completed it.** The reason a flow surfaces for an unstaffable review is the reason the operator is
shown in place of the queue's status breakdown, so it is the whole of what this specification puts in
front of them; a reason that misattributes the completion trades a fact about the queue for an untrue
fact about the task. Where the exclusion is the set of agents that worked the task, the reason SHALL
say so.

#### Scenario: Operator-completed work is offered to an agent that did not work it

- **WHEN** a flow fires on a queue holding a task the operator moved to `completed`, and an eligible
  agent has no recorded transition on that task
- **THEN** that agent is fired for the review

#### Scenario: The agent that produced the work is not resolved as its reviewer

- **WHEN** a flow resolves a reviewer for a task the operator moved to `completed`
- **THEN** an agent recorded on one of that task's earlier transitions is not selected

#### Scenario: A single-agent project surfaces rather than self-approving

- **WHEN** the only agent in the project is one recorded on that task's transitions
- **THEN** no agent is fired for the review
- **AND** the flow surfaces that it could not staff the review, naming the task

#### Scenario: The surfaced reason does not claim an agent completed the work

- **WHEN** a flow cannot staff a review for a task the operator moved to `completed`
- **THEN** the surfaced reason states that the excluded agents worked on the task
- **AND** it does not state that any of them completed it

#### Scenario: The missing-commit reason still wins where it applies

- **WHEN** a task the operator moved to `completed` has no evidence naming a commit
- **THEN** the surfaced reason is that there is nothing to check out for review
