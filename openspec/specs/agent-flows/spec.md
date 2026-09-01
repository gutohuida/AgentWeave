# agent-flows Specification

## Purpose

A flow is a loop that declares a specification document. Where a loop pokes one agent on a schedule,
a flow executes a declared decomposition: each firing determines both the task and the agent, so the
work can cross agents — implementer to reviewer — without an agent choosing its own next step. This
capability owns firing-time agent resolution, reviewer resolution, review dispatch and its handover
briefings, flow width, and the checkpoint lineage a flow shares across the agents it fires.
## Requirements
### Requirement: A flow is a loop that declares a specification document

The Hub SHALL treat a loop that declares a specification document as a flow, and SHALL apply the
requirements in this capability to it. A loop that declares no document SHALL be unaffected by them
and SHALL behave exactly as it does today.

No separate record SHALL be introduced for a flow. The distinction SHALL be the presence of the
declared document and nothing else.

#### Scenario: A loop with a document is a flow

- **WHEN** a loop declares a specification document
- **THEN** its firings select an agent as well as a task

#### Scenario: A loop without a document is unchanged

- **WHEN** a loop declares no specification document
- **THEN** every firing fires the job's own agent, as before

#### Scenario: A flow with one agent and no declared reviewers behaves as a loop

- **WHEN** a flow's project holds exactly one agent and its document declares no reviewers
- **THEN** every firing fires that agent
- **AND** the observable behaviour is identical to the same queue run as a loop

### Requirement: A firing determines both the task and the agent

Each firing of a flow SHALL determine deterministically which task or tasks are worked and which
agent works each of them. No firing SHALL leave either choice to a firing agent's own judgement.

The agent determined for a task SHALL be one the Hub can actually start. A firing SHALL NOT select an
agent with no runner bound, and SHALL treat such an agent as unavailable rather than failing the
firing.

#### Scenario: The agent is chosen by the Hub, not the agent

- **WHEN** a flow fires and a task needs an agent other than the one that produced it
- **THEN** the Hub determines which agent is fired
- **AND** no agent is asked to nominate one

#### Scenario: An agent with no runner is not selected

- **WHEN** the only otherwise-eligible agent has no runner bound
- **THEN** that agent is not fired
- **AND** the firing reports that it could not staff the step

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

**The agents that have worked a task SHALL be determined from every record that associates an agent
with it — its recorded transitions, the agent it is assigned to, and the runs recorded as bound to
it — and SHALL NOT be determined from any of those alone.** Each names a different fact and each is
incomplete. The history is required because who holds a task is overwritten by every reassignment,
so a task returned for revision and picked up by a second agent has two authors and only the history
names both. The assignee is required because an agent takes a transition only when it *changes* a
task's status: an agent working a task that is already in progress records nothing, so a task the
operator started by hand and then marked finished can carry a full history that names no agent while
an agent produced all of the work. The bound runs are required because the assignee holds one name
and is not overwritten by a later agent, so the *second* agent to work an already-started task is
named by neither of the other two — and it is that agent, not the first, that the other two terms
would offer its own work to review.

Because no completion is recorded, no record proves which agent authored the work, and the Hub SHALL
NOT act as though one does. The determination SHALL therefore be over-inclusive by construction: a
record that associates an agent with a task SHALL be sufficient to exclude it, and a source that
fails to record an agent SHALL NOT be taken as evidence that the agent did not work the task. The
cost of excluding an agent that did nothing is a review the flow reports it could not staff, which
the operator sees and resolves; the cost of including an agent that wrote the work is a self-approval
nobody sees.

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

#### Scenario: A second agent that worked the task is excluded although it holds neither the history nor the assignment

- **WHEN** a task's most recent completion was recorded by the operator, and an agent's run was
  bound to that task while another agent was recorded on its transitions and held its assignment
- **THEN** that agent is not fired for it

#### Scenario: A task with no recorded completion stays claimable by nobody

- **WHEN** a task is `completed` and no transition into that status is recorded for it
- **THEN** no agent is fired for it

### Requirement: A review turn that records no verdict is divergent

A flow SHALL record a divergence where a review turn ends without recording a verdict on the task
it was given, naming the run, the reviewer, the task, and the run's exit status. A review turn's
output is a verdict; a turn that produced none produced nothing.

The fact SHALL be recorded rather than inferred from absence. A surface that reasons "no run is
alive, therefore nobody is reviewing" is deducing from what it cannot find; the run that ended
without judging is a positive fact and SHALL be held as one.

Recording it SHALL NOT move the task. A review that gave no verdict has produced no judgement, and
the system SHALL NOT supply one on its behalf.

#### Scenario: A review that records a verdict is not divergent

- **WHEN** a review turn moves its task to approved, rejected, or revision needed, and ends
- **THEN** no divergence is recorded

#### Scenario: A review that ends silently is recorded as divergent

- **WHEN** a review turn ends having recorded no verdict on the task it was given
- **THEN** a divergence is recorded naming the run, the reviewer, the task, and the exit status
- **AND** the task's status is unchanged

#### Scenario: The record is durable and readable

- **WHEN** a review turn's divergence has been recorded
- **THEN** it is readable afterwards without consulting whether any run is currently alive

### Requirement: A response to a failed review is given the work under review

Where a flow starts any further run in response to a review that gave no verdict, that run SHALL be
given the same checkout of the work under review that the original review turn was given.

A reviewer fired into its own workspace cannot see the author's unmerged work, which is the defect
the review checkout exists to prevent. A response path that omits it would reproduce that defect at
precisely the moment the system is trying to recover from a failed review.

#### Scenario: A responding reviewer sees the work

- **WHEN** a flow starts a run in response to a review that recorded no verdict
- **THEN** that run's workspace is the checkout of the work under review

#### Scenario: A response to a work run is unaffected

- **WHEN** a flow starts a run in response to a run that was not a review
- **THEN** no review checkout is prepared for it

### Requirement: A flow resolves a reviewer by declaration, then by availability

Where a task declares a reviewer, the Hub SHALL attempt to resolve that declaration to an agent in
this project, and SHALL do so by the same resolution the rest of the product already uses for a
declared reviewer, never a second one.

**Where a declaration exists and does not resolve, the Hub SHALL NOT substitute a different agent.**
It SHALL surface the declaration and the reason it failed, and the review falls to the operator. A
declaration that named someone is not the same fact as no declaration at all: quietly running the
review under a different name tells the operator that the agent they named checked the work when it
did not.

Where **no** reviewer is declared, the Hub SHALL select any agent that is not running a turn and
holds no task in an active status.

Where no declaration exists and no agent is available, the flow SHALL surface that it could not
staff the step, naming the task. The flow's job SHALL remain enabled and SHALL remain scheduled.

**This resolution SHALL also answer a review that was staffed and then gave no verdict**, so that a
failed review is met by the same rule that staffed it rather than by a second mechanism. Where the
reviewer that failed had been **declared**, the Hub SHALL surface it and SHALL NOT substitute
another agent — the reasoning above does not weaken because the declared agent ran and said nothing.
Where the reviewer that failed had been selected by **availability**, the Hub SHALL resolve again,
excluding the agent that failed.

**The Hub SHALL NOT resolve, as a task's reviewer, an agent that could not record a verdict on it.**
An agent is barred from judging work it completed, so naming it would produce a review refused on
arrival; the resolution SHALL exclude it rather than discover the refusal afterwards.

#### Scenario: A declared reviewer that resolves is used

- **WHEN** a task declares a reviewer that resolves to an eligible agent
- **THEN** that agent is fired for the review

#### Scenario: An unresolvable declaration is surfaced, never substituted

- **WHEN** a task declares a reviewer that resolves to no agent in this project
- **THEN** no other agent is fired for that review
- **AND** the declared name and the reason it did not resolve are surfaced to the operator

#### Scenario: An undeclared review falls back to availability

- **WHEN** a task declares no reviewer at all
- **THEN** an agent that is not running and holds no active task is fired for the review

#### Scenario: A busy agent is not selected

- **WHEN** an otherwise eligible agent is running a turn, or holds a task in an active status
- **THEN** it is not selected while another eligible agent is available

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

### Requirement: An agent fired to review a completed task is given a review turn

Where a flow fires an agent for a task in `completed`, that firing SHALL be a review turn: the agent
SHALL be given the workspace and the turn context that reviewing already means in this product,
naming the task under review and the commit its most recent evidence cites.

A firing that staffs a review SHALL NOT deliver an ordinary turn. An ordinary turn places the agent
in its own working checkout, where work that has not been integrated does not exist — so a reviewer
given one cannot see what it was fired to review.

This guarantee SHALL hold over the turn the agent is delivered, not only over the firing that staged
it. A turn may be assembled from the input of more than one firing, so a firing that correctly stages
a review alone can still reach an agent alongside another firing's work. Where that happens the turn
SHALL be refused rather than delivered as a mixture — batching two firings SHALL NOT be able to
produce what a single firing is forbidden to produce.

Where a review turn cannot be prepared, the flow SHALL surface the stated reason and SHALL NOT fire
the agent into an ordinary turn instead.

#### Scenario: A reviewer sees the work it was fired to review

- **WHEN** a flow fires an agent for a task another agent completed
- **AND** that task's evidence cites a commit that exists only on the author's branch
- **THEN** the reviewing agent's workspace contains that commit's content

#### Scenario: The reviewer is told it is reviewing

- **WHEN** a flow fires an agent for a task in `completed`
- **THEN** the turn context states that this is a review, of which task, at which commit

#### Scenario: A review turn that cannot be prepared is not downgraded

- **WHEN** a flow would fire an agent for a review and the review turn cannot be prepared
- **THEN** the agent is not fired with an ordinary turn
- **AND** the reason is surfaced to the operator

#### Scenario: Two firings cannot combine into a mixed turn

- **GIVEN** one firing that staged a review for an agent and another that staged ordinary work for
  the same agent
- **WHEN** both are still queued and a turn is started
- **THEN** the turn is refused
- **AND** the reviewing agent is not delivered an ordinary turn alongside its review

### Requirement: A flow may start every task whose dependencies are met

A firing of a flow MAY start more than one task, and SHALL start only tasks whose dependencies are
met and for which an agent was resolved. The number started SHALL be bounded by the graph and by the
agents available, and SHALL NOT be read from any configured limit.

An agent SHALL NOT be started for two tasks in the same firing.

#### Scenario: Two independent tasks start together

- **WHEN** a flow fires, two queued tasks have all their dependencies met, and two eligible agents
  are available
- **THEN** both tasks are started

#### Scenario: Width is bounded by available agents

- **WHEN** three tasks are startable and one eligible agent is available
- **THEN** one task is started
- **AND** the others keep their status and gain no assignee

#### Scenario: A dependent task does not start alongside its prerequisite

- **WHEN** one queued task depends on another and neither has been approved
- **THEN** only the prerequisite is started

#### Scenario: One agent is not started twice in one firing

- **WHEN** two tasks would both resolve to the same agent
- **THEN** that agent is started for one of them only

### Requirement: A flow's checkpoint lineage belongs to the flow

The Hub SHALL maintain one checkpoint lineage per flow, shared by every agent the flow fires, and
each checkpoint SHALL record which agent wrote it.

A firing SHALL be briefed with the most recent checkpoint of its flow regardless of which agent
recorded it.

#### Scenario: A reviewer is briefed with the implementer's checkpoint

- **WHEN** a flow fires an agent for a task another agent completed, and that agent recorded a
  checkpoint
- **THEN** the fired agent's briefing includes that checkpoint's content

#### Scenario: A checkpoint names its author

- **WHEN** a checkpoint is read from a flow whose firings involved more than one agent
- **THEN** the agent that wrote it is identifiable

### Requirement: A firing's briefing states which tier the agent is working inside

The briefing of each firing SHALL state whether the agent is working inside a flow or a loop, and
SHALL state what follows for the agent — in particular that an agent in a flow completes its task and
stops, because routing the work onward is the flow's responsibility and not the agent's.

#### Scenario: A flow's briefing says routing is not the agent's job

- **WHEN** a flow fires an agent
- **THEN** the briefing states that the flow routes the work onward

#### Scenario: A loop's briefing does not claim a flow's behaviour

- **WHEN** a loop with no document fires its agent
- **THEN** the briefing does not state that anything will route its work onward

### Requirement: A dispatched review leaves the reviewable pool

Where a flow staffs a review, the firing SHALL move the task out of the statuses a review may be
claimed from, in the same commit that queues the review turn. A task a reviewer already holds SHALL
NOT be offered to any agent, including the reviewer holding it.

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

#### Scenario: A held task is never re-staffed as ordinary work

- **WHEN** a task is held by a reviewer
- **THEN** no firing staffs that task as ordinary work
- **AND** no agent is fired at it in a workspace other than the review checkout

### Requirement: A review turn is told how to record its verdict

The turn context for a review SHALL name the transitions available to the reviewer for both
outcomes — that the work is correct, and that it needs revision — and those transitions SHALL be
legal from the status the task is in when the reviewer receives it.

A review turn's context SHALL NOT name a transition that the task's status does not offer.

#### Scenario: Both verdicts are stated and both are legal

- **WHEN** an agent is given a review turn
- **THEN** the context names how to record that the work is correct
- **AND** names how to record that it needs revision
- **AND** both are transitions the task can actually make

### Requirement: A flow generates the author's handover briefing

The Hub SHALL generate an agent's checkpoint at the boundary of the run that completed a task,
whenever that agent works inside a flow and has recorded notes for whoever reviews the work, and
that checkpoint SHALL be attributed to the flow.

The Hub SHALL NOT require a context-usage threshold or an operator action for this to happen: a
flow firing's conversation reaches neither, so a briefing that depends on either is a briefing that
is never delivered.

Where the agent recorded no notes, the Hub SHALL generate nothing.

Where the project has chosen no runner for checkpoint generation, the Hub SHALL generate nothing
and SHALL NOT substitute another runner.

#### Scenario: An agent that briefed its reviewer has that briefing generated

- **WHEN** an agent in a flow completes its task having recorded notes for its reviewer
- **THEN** a checkpoint is generated for that agent's conversation
- **AND** the checkpoint is attributed to the flow
- **AND** the agent's notes are consumed by it

#### Scenario: An agent that recorded nothing costs nothing

- **WHEN** an agent in a flow completes its task having recorded no notes
- **THEN** no checkpoint is generated
- **AND** no generation is spawned

#### Scenario: A run that finished no task is not a handover

- **WHEN** a run ends without having completed the task it held
- **THEN** no handover checkpoint is generated

### Requirement: A reviewer is briefed by the author of the work it is reviewing

When a flow gives an agent a review turn, the briefing SHALL carry the checkpoint of the agent that
completed **the task under review**, and SHALL NOT substitute another agent's merely because it is
more recent.

A turn that is not a review SHALL continue to be briefed with the flow's most recent checkpoint.

Where the author left no checkpoint, the flow SHALL fall back to its most recent rather than
briefing with nothing.

#### Scenario: The newest checkpoint belongs to someone else

- **WHEN** a reviewer is given a task whose author is not the last agent to have finished
- **THEN** the briefing carries the author's checkpoint
- **AND** does not carry the more recent one

#### Scenario: Ordinary work still reads the flow's latest

- **WHEN** an agent is given a turn that is not a review
- **THEN** the briefing carries the flow's most recent checkpoint

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

### Requirement: A firing's briefing names how its claimed task is finished

A firing's briefing SHALL name the call that moves the claimed task to the status that means the work is finished, SHALL name that status, and SHALL state what a turn that ends without it costs.

The briefing SHALL state the status the task is in at the moment the agent receives it, and the
transitions it names SHALL be legal from that status. A firing claims a task from any status in
which firing an agent makes progress possible, which includes one returned for revision; the status
that means the work is finished is not reachable in one step from every one of them, so a briefing
that names only the target describes a call that is refused.

This SHALL be stated for every firing that claims a task, whether or not the loop declares a
specification document. A task's lifecycle is the same in both, and a queue drains on the same band
in both; a document-less loop whose task never leaves an active status re-claims that task on every
subsequent firing for exactly the reason a flow's does.

What completing **causes** SHALL be stated only where it is true of that firing. A flow SHALL state
that finished work is offered for review by another agent; a loop that declares no document SHALL
NOT state that anything routes its work onward.

Where the claimed task serves requirements of record, the briefing SHALL name those requirements by
their identifiers and SHALL name how evidence is recorded against them. Where the task serves none,
the briefing SHALL say nothing about evidence — an instruction to record evidence against a
requirement that does not exist is refused when followed, which is worse than silence.

The turn context's inventory of callable tools SHALL NOT be read as satisfying this. An inventory
states that a capability exists; this states that using it is how the firing's work is concluded.
Measured, agents in a flow called the tool the briefing named and did not call the tool named only in
the inventory, and the flow re-briefed them for finished work on every subsequent firing.

A briefing that asks an agent to record something for a later reader SHALL name what makes that
record reach one. Notes recorded for a reviewer are consumed at the boundary of a run that moved its
task to the finished status; a briefing that asks for the notes and not for the transition asks for a
record nobody will ever read.

#### Scenario: The briefing names the transition that finishes the work

- **WHEN** a firing claims a task and briefs an agent for it
- **THEN** the briefing names the call that moves that task
- **AND** names the status that means the work is finished
- **AND** names the status the task is in now

#### Scenario: A flow says what completing causes and a loop does not

- **WHEN** a flow fires an agent for a task
- **THEN** the briefing states that finished work is offered for review by another agent
- **WHEN** a loop that declares no document fires an agent for a task
- **THEN** the briefing still names how the task is finished
- **AND** does not state that anything routes its work onward

#### Scenario: What is recorded for a later reader is asked for together with what delivers it

- **WHEN** a briefing asks an agent to record notes for whoever reviews the work
- **THEN** it also names the transition that causes those notes to be delivered

#### Scenario: A turn that ends without moving the task is named as a cost

- **WHEN** a firing claims a task and briefs an agent for it
- **THEN** the briefing states what happens if the turn ends with the task unmoved

#### Scenario: Evidence is named only where there is a requirement to name

- **WHEN** a firing claims a task that serves requirements of record
- **THEN** the briefing names those requirements by identifier
- **AND** names how evidence is recorded against them
- **WHEN** a firing claims a task that serves no requirement of record
- **THEN** the briefing says nothing about recording evidence

#### Scenario: A task returned for revision is told the step it must actually take first

- **WHEN** a firing claims a task that was returned for revision
- **THEN** the briefing names the transition that is legal from that status
- **AND** does not name the finished status as reachable in one step

#### Scenario: A firing that claims no task states no completion contract

- **WHEN** a firing proceeds with no task claimed
- **THEN** the briefing names no task, no transition and no requirement

### Requirement: A review firing's briefing is a review briefing

Where a firing is staffed as a review, its briefing SHALL state that the turn is a review, SHALL NOT instruct the agent to carry out the task's work, and SHALL name both verdicts available to the reviewer.

The task's own description and acceptance criteria SHALL be presented as the standard the finished
work is checked against, under a heading that says so. They SHALL NOT be presented under an
instruction to complete them.

The verdicts named SHALL be legal from the status the task is in when the reviewer receives it, and
SHALL agree with what the turn context states. Naming them on both channels is required rather than
merely permitted: a reviewer that is told how to end only on the channel the briefing contradicts is
the condition under which no flow-dispatched review had ever recorded a verdict.

A review briefing SHALL still state the tier the agent is working inside, and SHALL still state that
the turn ends rather than continuing into other work.

Where text the firing did not compose is delivered after the briefing in the same turn, a review
briefing SHALL identify it as the loop's standing message, delivered on every firing and not written
for this turn in particular. It SHALL NOT instruct the agent to disregard that text: a loop's message
may itself be written to address a review, and a briefing that told the agent to ignore it would be
wrong in exactly the cases where its author had thought hardest. The message SHALL NOT be rewritten
either, because it is the durable record of what its author said.

#### Scenario: A reviewer is not told to build what it is reviewing

- **WHEN** a flow staffs an agent to review a completed task
- **THEN** the briefing states that the turn is a review
- **AND** does not instruct the agent to finish or complete the task
- **AND** presents the task's description as what the work is checked against

#### Scenario: Both verdicts are named in the briefing

- **WHEN** an agent is briefed for a review turn
- **THEN** the briefing names how to record that the work is correct
- **AND** names how to record that it needs revision
- **AND** both are transitions the task can make from the status it is in

#### Scenario: The two channels agree

- **WHEN** an agent is briefed for a review turn
- **THEN** the briefing and the turn context do not give contradictory instructions about whether
  the agent is doing the work or checking it

#### Scenario: The loop's standing message is not mistaken for this turn's instruction

- **WHEN** an agent is briefed for a review turn and the loop's own message follows the briefing
- **THEN** the briefing identifies the text following it as the loop's standing message
- **AND** does not instruct the agent to disregard it
- **AND** the loop's message itself is delivered unchanged

#### Scenario: An implementation firing is unaffected

- **WHEN** a firing is not staffed as a review
- **THEN** the briefing instructs the agent to do the task's work
- **AND** names the transition that finishes it

### Requirement: A review nobody is doing is named, whatever its history

Where a task is under review with an agent named on it and no turn is being taken on that task, the flow SHALL surface that review, naming the task and the named agent, and SHALL do so regardless of how the task reached that state and regardless of whether any run has ever been bound to it.

This SHALL hold for a task no run has ever touched. A task an operator moved into review by hand has no run boundary to have diagnosed it, so the surfacing that answers a review turn ending without a verdict cannot reach it; the operator SHALL be told the same thing by the same words either way.

The flow SHALL NOT substitute another agent as part of this surfacing. Replacing a reviewer is governed by the resolution that already runs at a review turn's end, and a second path that also replaced one could reach a different answer than the first.

#### Scenario: An operator-walked review with no run is surfaced

- **WHEN** an operator moves a task to under review by hand, naming an agent, and no run is ever bound to that task
- **THEN** the flow surfaces that review, naming the task and that agent

#### Scenario: A surfaced review that was diagnosed at a run boundary stays surfaced

- **WHEN** a review turn ends without recording a verdict and the resolution finds no agent left to substitute
- **THEN** the task remains under review with the silent reviewer named
- **AND** the flow surfaces that review on each firing rather than reporting the queue as busy

#### Scenario: The surfacing names the agent, not only the task

- **WHEN** a review nobody is doing is surfaced
- **THEN** the sentence the operator reads names the agent whose name is on the task

#### Scenario: No substitution happens on this path

- **WHEN** the flow surfaces a review nobody is doing
- **THEN** no other agent is fired for that review by this path
- **AND** the assignee on the task is not changed by it

