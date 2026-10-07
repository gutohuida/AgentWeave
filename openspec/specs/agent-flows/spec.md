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

**Where an agent is recorded as completing the task, the Hub SHALL NOT allow it to be claimed by an
agent recorded as having produced evidence for it either** (F505). Author/reviewer separation
refuses an evidence author's verdict whoever completed the task, and an offer the guard would then
refuse is a review that cannot end.

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
with it — its recorded transitions, the agent it is assigned to, the runs recorded as bound to it,
and the agents recorded as having produced evidence for it — and SHALL NOT be determined from any of
those alone.** Each names a different fact and each is incomplete. The history is required because
who holds a task is overwritten by every reassignment, so a task returned for revision and picked up
by a second agent has two authors and only the history names both. The assignee is required because
an agent takes a transition only when it *changes* a task's status: an agent working a task that is
already in progress records nothing, so a task the operator started by hand and then marked finished
can carry a full history that names no agent while an agent produced all of the work. The bound runs
are required because the assignee holds one name and is not overwritten by a later agent, so the
*second* agent to work an already-started task is named by neither of the other two — and it is that
agent, not the first, that the other two terms would offer its own work to review.

**The evidence is required because it is the only one of the four in which the agent states its own
authorship.** The other three are circumstantial: this agent moved the task, holds it, or ran about
it. Evidence recorded against a task is the agent asserting that this is its work, and it carries the
commit the reviewer is then given to read. An agent whose turn was never bound to a task, that was
never assigned it and that took no transition on it — the ordinary shape when an operator drives an
agent from the composer — is named by nothing else, and it is the agent whose work the operator then
marks finished.

**Evidence SHALL exclude its author whatever the state of its review.** An agent whose evidence was
rejected, or whose evidence is still awaiting a decision, still produced the work the row records.
Keying the exclusion on a review decision would reintroduce the gap one status value along, and would
make who may review a task depend on the outcome of the review being staffed.

**Evidence recorded by the operator SHALL NOT exclude any agent.** A person recording what
demonstrates the work is not an agent claiming authorship of it, and a task whose evidence came only
from the operator has no agent-authored record at all — so every agent remains eligible to review it,
which is the case this rule must not take away.

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

#### Scenario: An agent that recorded evidence may not take a task another agent completed

- **WHEN** a flow fires and a queued task is `completed` by agent A, and agent B recorded evidence
  for it
- **THEN** B is not fired for that task

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

#### Scenario: The agent that recorded the evidence is excluded although no other record names it

- **WHEN** a task's most recent completion was recorded by the operator, and an agent recorded
  evidence for that task from a run that was never bound to it, having taken no transition on it and
  never held its assignment
- **THEN** that agent is not fired for it

#### Scenario: Evidence still awaiting a decision excludes its author

- **WHEN** the only record naming an agent on an operator-completed task is evidence whose review is
  still awaiting a decision, or whose review rejected it
- **THEN** that agent is not fired for it

#### Scenario: Evidence the operator recorded excludes nobody

- **WHEN** an operator-completed task's only evidence was recorded by the operator
- **THEN** an agent that no other record associates with that task may be fired for it

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

**Where approval of the task is refused for a reason only the operator can remove, a review that gave no verdict SHALL NOT be answered by resolving a second reviewer**, whether the reviewer that failed was declared or selected by availability. The Hub SHALL surface the review instead, as *A review no reviewer can approve is handed to the operator* states. A reason only the operator can remove is one whose remedy is a decision on evidence, where the agent the resolution would select has not been granted that decision; a drift candidate, which only the operator resolves whatever an agent is granted; a requirement that cannot be satisfied as written; or the Hub being unable to ask the project's repository whether the work would merge, which a second reviewer's approval would meet in the same repository. A second reviewer meets the identical refusal, so resolving one spends a review turn on a conclusion that has nowhere to go and tells the operator about staffing instead of about the decision waiting for them. Where the agent the resolution selects has been granted the decision on evidence, it can remove the reason itself, and the resolution SHALL proceed as above.

**The Hub SHALL NOT resolve, as a task's reviewer, an agent that could not record a verdict on it.**
An agent is barred from judging work it completed, and from judging work it recorded evidence for
whoever completed it (F505), so naming either would produce a review refused on arrival; the
resolution SHALL exclude both rather than discover the refusal afterwards. This SHALL hold for the
first resolution and for the one that answers a failed review alike.

#### Scenario: The author is not offered the work by the second resolution either

- **WHEN** a reviewer staffed for a task the operator moved to `completed` ends its turn without
  recording a verdict, and the Hub resolves a replacement
- **THEN** an agent that any record associates with that task is not selected
- **AND** the agent that gave no verdict is not selected

#### Scenario: An evidence author is excluded where another agent completed the task

- **WHEN** a flow resolves a reviewer for a task agent A completed, first or after a review that gave
  no verdict, and agent B recorded evidence for it
- **THEN** neither A nor B is selected

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

#### Scenario: A review whose approval waits on the operator is not given to a second reviewer

- **WHEN** a review by an agent selected on availability ends without recording a verdict
- **AND** approving the task is refused because evidence naming a commit is waiting to be decided, and no other agent's approved work would merge
- **AND** the agent the resolution would select has not been granted the decision on evidence
- **THEN** no other agent is fired for that review
- **AND** the task's holder is unchanged

#### Scenario: A reviewer granted the evidence decision is still resolved

- **WHEN** a review by an agent selected on availability ends without recording a verdict, approving the task is refused because evidence is waiting to be decided, and the agent the resolution selects has been granted the decision on evidence
- **THEN** that agent is fired for the review

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

### Requirement: A review turn is told how to record its verdict

The turn context for a review SHALL name the transitions available to the reviewer for both
outcomes — that the work is correct, and that it needs revision — and those transitions SHALL be
legal from the status the task is in when the reviewer receives it.

A review turn's context SHALL NOT name a transition that the task's status does not offer.

Where a requirement the task serves has only rejected evidence, both review channels SHALL say that
`approved` will be refused for it, naming the requirement, and that `revision_needed` is the
verdict that returns the task to its author (F497). The rejected requirement refuses approval at
every rigor and its remedy is the author's, so a reviewer not told this approves into a refusal it
cannot clear. The approval refusal itself SHALL end with the same reviewer move.

#### Scenario: Both verdicts are stated and both are legal

- **WHEN** an agent is given a review turn
- **THEN** the context names how to record that the work is correct
- **AND** names how to record that it needs revision
- **AND** both are transitions the task can actually make

#### Scenario: A reviewer is told a rejected requirement refuses approval

- **WHEN** a review turn is given for a task serving a requirement whose evidence is all rejected
- **THEN** its briefing names that requirement and says `approved` will be refused
- **AND** says `revision_needed` returns the task to its author

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

**An agent that recorded evidence for the task SHALL be among those excluded.** This is not an
addition to the boundary but the boundary reaching the record that states authorship most directly:
the ladder is already forbidden from resolving an agent that could not record a verdict on the task,
and author/reviewer separation refuses such an agent's verdict. A ladder that staffed it would name
a reviewer whose review is refused on arrival.

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

#### Scenario: The agent that recorded the evidence is not resolved as its reviewer

- **WHEN** a flow resolves a reviewer for a task the operator moved to `completed`, and one eligible
  agent recorded that task's evidence while another did not
- **THEN** the agent that recorded the evidence is not selected
- **AND** the other agent is fired for the review

#### Scenario: A single-agent project surfaces rather than self-approving

- **WHEN** the only agent in the project is one recorded on that task's transitions
- **THEN** no agent is fired for the review
- **AND** the flow surfaces that it could not staff the review, naming the task

#### Scenario: A project whose only other agent recorded the evidence surfaces rather than self-approving

- **WHEN** every agent free to review an operator-completed task recorded evidence for it
- **THEN** no agent is fired for the review
- **AND** the flow surfaces that it could not staff the review, naming the task
- **AND** the surfaced reason does not state that any agent completed it

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

**A work briefing for a task returned for revision SHALL say why it came back** (F504): the agent
that moved it to `revision_needed` and the notes it left, and whether the task's own branch still
merges into the main branch, measured when the briefing is composed, naming the conflicting paths
and the remedy (merge the main branch into the task's branch, keep both sides, run the tests, and
record evidence again on the resolved commit) where it does not. Where no notes were left and
nothing conflicts, it SHALL say so and name the task's history as where to look. Failing to measure
SHALL NOT withhold the briefing. A brief that carried only the original description sent an author
whose task came back over a merge conflict to re-run its green tests, complete the same commit, and
meet the same refusal.

#### Scenario: A task sent back for revision is told why

- **WHEN** a firing claims for work a task a reviewer moved to `revision_needed` with notes, and the
  task's branch no longer merges into the main branch
- **THEN** the briefing names that reviewer and quotes its notes
- **AND** it names the conflicting paths and the remedy of merging the main branch into the task's
  branch and recording evidence again on the resolved commit

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
wrong in exactly the cases where its author had thought hardest. The message's words SHALL NOT be
rewritten either, because it is the durable record of what its author said. The one change its
delivery makes is the one `agent-run-sandboxing` requires of every firing's text (*Text the operator
did not write reaches a run without a file mention its harness would expand*): each at-sign in it is
neutralised so that it attaches no file. The stored message keeps the text as its author wrote it.

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
- **AND** the loop's message itself is delivered with its words unchanged, its at-signs neutralised as
  every firing's text is

#### Scenario: An implementation firing is unaffected

- **WHEN** a firing is not staffed as a review
- **THEN** the briefing instructs the agent to do the task's work
- **AND** names the transition that finishes it

#### Scenario: A loop's message that mentions a file is delivered without attaching it

- **WHEN** a review firing delivers a loop message that mentions a file in the harness's mention syntax
- **THEN** the message reaches the run with that mention neutralised and no file is attached for it
- **AND** the stored message keeps the mention as its author wrote it

### Requirement: A review nobody is doing is named, whatever its history

Where a task is under review with an agent named on it and that agent is not working it, as `agent-loops` *A task reported as in flight is one an agent is actually working* defines, the flow SHALL surface that review, naming the task and the named agent, and SHALL do so regardless of how the task reached that state and regardless of whether any run has ever been bound to it.

This SHALL hold for a task no run has ever touched. A task an operator moved into review by hand has no run boundary to have diagnosed it, so the surfacing that answers a review turn ending without a verdict cannot reach it; the operator SHALL be told the same thing by the same words either way.

Input naming the task that is queued for some other agent SHALL NOT keep the review from being surfaced. A message a third agent is sent about the task is not the named agent reviewing it. Where input naming the task is queued for the named agent and its last delivery was refused, the surfaced sentence SHALL contain that refusal's own words, because it, not the absence of a turn, is why nothing is happening.

The surfaced sentence SHALL NOT state that no input is queued, because input the flow does not count may be.

Where the agent named on the task is the agent that produced its work, and some agent's turn on the task is running or waiting to be delivered, the flow's recovery of that task waits for the turn, and the task SHALL NOT be surfaced as a review that agent is not doing. Such an agent is not reviewing it, and a sentence naming it as the reviewer would be false while the recovery is only waiting.

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

#### Scenario: A third agent's message about the task does not hide the review

- **WHEN** a task is under review with an agent named on it, no turn is running on it, and a message naming the task is queued for a different agent
- **THEN** the flow surfaces that review, naming the task and the named agent

#### Scenario: A refused review delivery is surfaced with its refusal

- **WHEN** a task is under review with an agent named on it, and the review input queued for that agent was refused on its last delivery
- **THEN** the flow surfaces that review
- **AND** the sentence contains the refusal's own words

#### Scenario: An author left holding a review, while another agent's turn is on the task, is not named as its reviewer

- **WHEN** a task is under review with the agent that produced its work named on it, and a message naming the task is queued for a different agent
- **THEN** the flow reports the task as in flight and does not surface it as a review nobody is doing
- **AND** no sentence names the author as the task's reviewer

#### Scenario: No substitution happens on this path

- **WHEN** the flow surfaces a review nobody is doing
- **THEN** no other agent is fired for that review by this path
- **AND** the assignee on the task is not changed by it

### Requirement: A flow treats an agent whose queue is held as unable to take a turn

A flow SHALL treat an agent whose queue is held by a refusal of the provider's usage allowance as unable to take a turn, wherever a firing asks whether an agent can take one.

The hold is the one `agent-conversation-workspace` defines. The scheduler starts no turn for a held
agent's autonomous input, so a briefing queued for it is as stale by the time it is read as one
queued during a running turn. A flow that asked the question about running agents alone would
re-brief a held agent's assigned task on every firing, and the agent would find a stack of
identical briefings when its hold ended.

A task assigned to a held agent SHALL be reported as in flight while input naming that task is
queued for that agent, and SHALL NOT be briefed again. Input naming the task that is queued for a different agent does not count, and neither does input past the hop budget or input whose last delivery was refused, as `agent-loops` *A task reported as in flight is one an agent is actually working* defines. Where the input the held agent's next turn would start with was refused on its last delivery, the task SHALL be surfaced with that refusal's words and SHALL NOT be briefed again, as that requirement also defines: a held agent's pass returns before any delivery, so a briefing queued behind the refused input would wait for the hold and then for the refusal. Where no input naming it is queued for the held agent, the firing
SHALL brief it once, as it resumes any assigned task, and the task is in flight from then on. A held agent is
working nothing, so its assignment alone is not the in-flight condition: that condition is the one
`agent-loops` *A task reported as in flight is one an agent is actually working* already states.

A held agent SHALL NOT be chosen as a firing's default agent, and SHALL NOT be recruited for new
work. A reviewer the task declares is unaffected: the declaration names who reviews, and the review
waits for the hold. A reviewer chosen by availability follows *A flow resolves a reviewer by
declaration, then by availability*.

Where a review cannot be staffed and an agent was passed over because its queue is held, the reason
surfaced SHALL name the hold among the grounds, and SHALL NOT state that every agent is running a
turn, holding work or excluded.

This concerns only whether an agent can take a turn now. Which tasks an agent holds, and which of
them make it unavailable, is unchanged.

#### Scenario: A held assignee whose briefing is queued is not re-briefed

- **WHEN** an agent's queue is held, it is assigned a task, input naming that task is queued for it, and another agent in the project is free
- **AND** the flow fires three times
- **THEN** no further input is queued for the held agent
- **AND** its task is reported in flight

#### Scenario: A held assignee whose input was refused is surfaced, not re-briefed

- **WHEN** an agent's queue is held, it is assigned a task, and the input its next turn would start with was refused on its last delivery
- **AND** the flow fires three times
- **THEN** no further input is queued for the held agent
- **AND** the flow surfaces the task with the refusal's own words

#### Scenario: A held assignee with nothing queued is briefed once

- **WHEN** an agent's queue is held, it is assigned a task, and no input naming that task is queued
- **AND** the flow fires three times
- **THEN** exactly one input naming that task is queued for the agent

#### Scenario: A held job agent is passed over

- **WHEN** a flow's job agent is held and another agent is free
- **AND** an unassigned task is startable
- **THEN** the firing staffs the free agent, not the held one

#### Scenario: A held agent is not free

- **WHEN** an agent is held, running no turn and holding no task
- **THEN** it is not counted among the agents free for new work or for review

#### Scenario: An unstaffed review names the hold

- **WHEN** no reviewer is declared, and the only agent that could review a task is held, running no turn and holding no task
- **THEN** the flow surfaces that it could not staff the review
- **AND** the surfaced reason names the provider's usage limit among the grounds

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

### Requirement: A review nobody is free to take names who holds what

Where no agent can be resolved for a review because none is available, the Hub SHALL surface a reason naming every agent on the project's roster and the reason that agent could not take it.

A sentence that says every agent is *"either running a turn, already holding active work, or is the
one that completed this task"* names nobody. It is the whole of what the operator is shown in place
of the queue. Measured on the operator's own flow, it stood for most of a night. The agent asked to
diagnose it blamed finished tasks, and the operator could not see that the holdings were follow-up
work outside the flow.

For each non-archived agent, the reason SHALL state the first of these that applies:
1. it is excluded from this review, stated with the reason the resolution applied to that agent;
2. it has no runner bound;
3. its queue is held by a refusal of its provider's usage allowance;
4. it holds tasks that still make it unavailable, naming each such task by identifier and status,
   where a bounded number MAY be named and the rest counted;
5. it is running a turn.

Clause 3 is not optional and SHALL NOT be folded into clause 5. An agent whose queue is held is not
running a turn, and saying that it is states a false cause for a condition that clears on its own
schedule rather than on the operator's. Naming every agent's reason individually is what satisfies
*"the reason surfaced SHALL name the hold among the grounds"*; a sentence built only from clauses
1, 2, 4 and 5 would violate that requirement in the ordinary case.

Clause 3 SHALL take precedence over clause 4. An agent whose queue is held and which also holds
tasks was passed over because its queue is held, and the hold SHALL be named for it. Naming its
tasks in the hold's place would drop a required ground, and would offer a way to free it that does
not: rejecting its tasks leaves its queue held.

Where agents are counted rather than named and any agent counted is held, the count SHALL name the
hold among the grounds it summarises.

A task in an active status that nothing will move SHALL NOT be named as a reason an agent could not
take the review. Such a task does not make its assignee unavailable, so naming it would state a
cause that is not one. The set named here SHALL be the set the availability determination actually
used.

The count of held tasks named here MAY therefore differ from the count of active tasks the roster
shows for the same agent. The two answer different questions — what an agent holds, and what
prevents a flow giving it work — and the reason SHALL be worded so that a reader is not told the two
disagree about the same fact.

The facts SHALL come from the same determination that found the agent unavailable, never from a
second one. A reason built separately could name an agent the resolution considered free.

The reason SHALL NOT describe an agent as having completed the work when the resolution excluded
that agent for a different reason, such as having reviewed the task without recording a verdict.

Where the reason names a way to free a held agent, that way SHALL have the stated effect for every
agent the reason named. Rejecting a task that is no longer wanted frees whoever held it, and the
operator can reach `rejected` from every status that makes an agent unavailable. Where no agent is
unavailable because of the tasks it holds, the reason SHALL NOT offer rejecting a task as a way
forward.

The reason SHALL NOT name pausing, which does not free an agent: a paused loop still holds, because
resuming it briefs the assignee on the same task again. Naming a control that does not have the
stated effect is the defect this requirement exists to end, and it is not cured by the control
being easy to reach or by the effect being usual rather than certain.

The reason SHALL NOT claim that ending or archiving a loop frees the agents holding its tasks. A
task can make its assignee unavailable either because a live loop still walks it **or** because a
queued turn names it, and retiring the loop withdraws only the first. An agent held through the
second arm stays held, so the claim would be false exactly when the operator acted on it.

The reason SHALL name an action that exists for the task in its present status:
- for a `completed` task, the landing action as the operator's way to review it themselves. It
  SHALL NOT promise that landing approves it. Landing is subject to the approval gate, and at this
  point the task's evidence names a commit and is often not yet judged, so the gate may refuse;
- for an `under_review` task, the operator's own decision on it. It SHALL NOT name the landing
  action, which refuses a task in that status.

Where an agent is excluded for more than one reason, the reason SHALL state the most specific:
- having been recorded as completing the task outranks having reviewed it without a verdict;
- having reviewed it without a verdict outranks having recorded evidence for it (F505);
- having reviewed it without a verdict outranks having merely worked on it.

The broader set of agents that may have authored a task includes whoever holds it and whoever ran
on it, and a silent reviewer is both.

The reason SHALL fit every surface that carries it. Where naming every agent would exceed that, the
remaining agents SHALL be counted rather than omitted without a count, and the action SHALL still be
named. Where the roster has any agent, the reason SHALL name at least one: an agent's held tasks are
counted before the agent itself is. Task identifiers may be chosen by whoever creates the task, and
a few long ones held by the first agent would otherwise leave a reason that names nobody, which is
the defect this requirement exists to end.

This requirement changes what the Hub **says** at the unstaffed rung. It does not change which
agents are available. *"A flow resolves a reviewer by declaration, then by availability"* still
decides that.

#### Scenario: Every agent that holds work is named with what it holds

- **WHEN** a flow cannot staff a review of a completed task, and the agents other than its author
  each hold tasks in active statuses
- **THEN** the surfaced reason names each of those agents
- **AND** it names each agent's held tasks by identifier and status, up to the bound, and counts the
  rest

#### Scenario: A task nothing will move is not named as a reason

- **WHEN** a flow cannot staff a review, and an agent other than the author is assigned a task in an
  active status that no live loop walks and no queued turn names
- **THEN** that agent is not described as held by that task
- **AND** the task's identifier does not appear in the surfaced reason

#### Scenario: An agent whose queue is held and which holds tasks is named as held

- **WHEN** a flow cannot staff a review and an agent whose queue is held by a refusal of its
  provider's usage allowance is also assigned a task that a live loop still walks
- **THEN** the surfaced reason names that agent's hold as its reason
- **AND** it does not name that task as the agent's reason

#### Scenario: A counted held agent still has its hold named

- **WHEN** so many agents are unavailable that some are counted rather than named, and one of those
  counted is held by a refusal of its provider's usage allowance
- **THEN** the surfaced reason still names the provider's usage limit among the grounds

#### Scenario: No task-rejecting remedy is offered when no agent holds work

- **WHEN** a flow cannot staff a review and no agent is unavailable because of the tasks it holds
- **THEN** the surfaced reason does not offer rejecting a task as a way forward

#### Scenario: An agent whose queue is held is named as held, not as running

- **WHEN** a flow cannot staff a review and an agent was passed over because its queue is held by a
  refusal of its provider's usage allowance
- **THEN** the surfaced reason names that agent's hold as its reason
- **AND** it does not state that the agent is running a turn

#### Scenario: The reason offers no remedy that would not free the agents it named

- **WHEN** a flow cannot staff a review because every other agent holds work
- **THEN** the way forward it offers names rejecting an unwanted task
- **AND** it does not offer pausing as a way to free an agent
- **AND** it does not claim that ending or archiving a loop frees them

#### Scenario: The author is named as excluded, not as busy

- **WHEN** the author of the task also holds other tasks in active statuses
- **THEN** the reason states the author's exclusion for this task
- **AND** it does not list the author's other holdings in its place

#### Scenario: A reviewer that gave no verdict is not said to have completed the work

- **WHEN** a review selected on availability ends without a verdict, and the second resolution finds
  nobody
- **THEN** the reason states that the agent which gave no verdict reviewed the task without
  recording one
- **AND** it does not state that this agent completed the task

#### Scenario: On operator-completed work the silent reviewer is still named as silent

- **WHEN** the operator completed the task, a review selected on availability ends without a
  verdict, and the second resolution finds nobody
- **THEN** the reason states that the agent which gave no verdict reviewed the task without
  recording one
- **AND** it does not describe that agent only as having worked on the task

#### Scenario: A completed task's reason does not promise approval

- **WHEN** the unstaffed task is `completed`
- **THEN** the reason names the landing action as the operator's own review
- **AND** it does not state that landing approves the task

#### Scenario: An empty roster is stated

- **WHEN** a flow cannot staff a review and the project has no non-archived agent
- **THEN** the reason states that the roster has no agent
- **AND** it still names the action

#### Scenario: An under-review task's reason does not name an action that refuses it

- **WHEN** the unstaffed task is `under_review`
- **THEN** the reason names approving, rejecting, or returning it for revision
- **AND** it does not name the landing action

#### Scenario: A large roster still produces a reason every surface accepts

- **WHEN** so many agents are unavailable that naming each would exceed the length the loop's run
  history accepts
- **THEN** the reason counts the agents it does not name
- **AND** it still names the action
- **AND** the job's run history is returned successfully

#### Scenario: Long task identifiers still leave an agent named

- **WHEN** the first agent in name order holds several tasks whose identifiers are as long as a
  task identifier may be
- **THEN** the reason names that agent, with as many of its held tasks as fit, and counts the rest
- **AND** it still names the action

### Requirement: A review no reviewer can approve is handed to the operator

Where a review turn ends without recording a verdict and approving the task is refused for a reason only the operator can remove, the Hub SHALL surface the review to the operator with that refusal's own sentence, and SHALL NOT surface it as a failure to staff a reviewer.

The refusal is the approval gate's, and its sentence already names what the operator must do. A
surfaced reason about who was free, or about which agents were excluded, sends the operator to the
roster, where nothing they change moves the task.

The flow's surfacing of the same task on later firings SHALL say the same thing. A task left under
review with its silent reviewer named is *a review nobody is doing*; where approving it is refused
for a reason only the operator can remove, the sentence the operator reads SHALL name that reason
and its remedy first, and SHALL NOT offer asking the same reviewer again as a way forward, because
that reviewer meets the same refusal.

A review whose reason can be removed by a reviewer is unaffected. Where the only refusal is one the
work's author can repair, a reviewer can still record that the work needs revision, and the review
is answered as before.

#### Scenario: The operator is told about the evidence, not about staffing

- **WHEN** a review turn ends without a verdict, and approving the task is refused because evidence naming a commit is waiting to be decided
- **THEN** the review is surfaced with the approval refusal's own sentence
- **AND** the surfaced reason does not state that no agent is free, and does not list which agents were excluded

#### Scenario: A drift only the operator resolves is not given to a second reviewer

- **WHEN** a review selected on availability ends without a verdict, and approving the task is refused because a requirement it serves has an unresolved drift candidate
- **AND** the agent the resolution would select has been granted the decision on evidence
- **THEN** no second reviewer is resolved
- **AND** the review is surfaced with the approval refusal's own sentence

#### Scenario: A later firing names the same reason

- **WHEN** a flow fires while that task is still under review with the silent reviewer named, and approving it is still refused for the same reason
- **THEN** the sentence the flow records names that reason and the decision waiting for the operator
- **AND** it does not offer asking the same reviewer again

#### Scenario: A review whose approval could not ask git is not given to a second reviewer

- **WHEN** a review selected on availability ends without a verdict, and asking the project's repository whether the task's work would merge fails or does not answer in time
- **THEN** no second reviewer is resolved
- **AND** the review is surfaced with a sentence saying the Hub could not ask git, and its reason

#### Scenario: Any other failure to evaluate the gate leaves the review answered as before

- **WHEN** a review selected on availability ends without a verdict, and evaluating approval fails for a reason other than the repository
- **THEN** the reviewer is resolved again as *A flow resolves a reviewer by declaration, then by availability* states
- **AND** the failure is logged as a warning

#### Scenario: A refusal the author can repair is answered as before

- **WHEN** a review selected on availability ends without a verdict, and approving the task is refused only because the work cannot be merged cleanly
- **THEN** the reviewer is resolved again as *A flow resolves a reviewer by declaration, then by availability* states

### Requirement: An approved document offers the operator its flow, or a way to start one

Where the app shows an approved change document, it SHALL show the flow that declares that document
when an unarchived one exists, and SHALL let the operator open it. When none exists, it SHALL offer to
start one, asking for the flow's name, default agent, message, stop condition and cadence, with the
defaults stated, and SHALL create it as a flow declaring that document. The first firing SHALL happen
at the next scheduled time, and the offer SHALL say so.

The offer SHALL NOT be shown for a document that is not approved, nor for any document that is not a
change document. A flow that has ended but is not archived still declares its document, so the app
SHALL show that flow rather than the offer. After a flow is started, the document SHALL name it
without the operator reopening the document.

#### Scenario: A document with a flow links to it

- **GIVEN** an approved change document declared by an unarchived flow
- **WHEN** the operator opens the document
- **THEN** the flow is named on the document, and opening it shows the flow's own view

#### Scenario: A document without a flow offers to start one

- **GIVEN** an approved change document that no unarchived flow declares
- **WHEN** the operator starts a flow from it, choosing an agent and keeping the other defaults
- **THEN** a flow is created that declares the document, stops when its queue empties, and fires every 5 minutes
- **AND** it has not fired yet; its first firing is at the next scheduled time
- **AND** the document now names the flow instead of offering to start one

#### Scenario: A document whose flow has ended but is not archived links to that flow

- **GIVEN** an approved change document declared by a flow that has ended and is not archived
- **WHEN** the operator opens the document
- **THEN** the ended flow is named on the document, and no offer to start one is shown

#### Scenario: The offer refuses to start a flow with no stop condition

- **WHEN** the operator clears every stop condition in the offer and tries to start the flow
- **THEN** nothing is sent, and the offer says a flow needs a stop condition

#### Scenario: A document already claimed is refused with the reason

- **GIVEN** a document another unarchived loop already declares
- **WHEN** a flow is started from it
- **THEN** the start is refused with a reason naming the loop that holds it

### Requirement: Approving a document creates the flow its delivery declares

When the operator approves a change document whose delivery declares a flow, the Hub SHALL create a
flow declaring that document, with the operator as the actor, named after the document, using the
delivery's default agent, stop condition and schedule, and owning the tasks the approval created. The
flow's first firing SHALL be at its next scheduled time. Creating it SHALL NOT depend on the project
allowing agents to create scheduled work, since the operator is the actor.

A delivery's agent is usable only when it is an open agent on the project. The Hub SHALL NOT create a
flow naming an agent that is archived or that the project does not have, whatever else it knows of
that name. When the delivery's agent is not usable, the operator MAY name another agent, or no flow,
at approval. That choice SHALL apply to the flow alone and MUST NOT edit the document.

Where an unarchived flow already declares the document, as on a re-approval after a reopen, the Hub
SHALL NOT create a second one, and the approval SHALL report the existing flow rather than a refusal,
whatever the delivery says. The report SHALL state whether that flow is running, disabled or ended,
and SHALL NOT report a flow that has ended or is disabled as building the document, since no one
works the tasks the approval gave it. An agent the operator chose at such an approval SHALL NOT be
applied, and the report SHALL say that it was not applied because the existing flow already declares
the document. Where the existing flow's agent differs from the delivery's, the report SHALL say so.

The Hub SHALL NOT create a flow whose delivery names no agent or no stop condition, or whose stop
time has already passed, and SHALL report why.

The Hub SHALL NOT create a flow that would own no open task once the approval's tasks are adopted,
as when creating the board failed or every declared task was already served by existing work, since
a flow whose queue was never filled fires an agent turn on every tick and never stops. The approval
SHALL report that no flow was started because it gave the flow no tasks.

If the flow cannot be created, the document SHALL still be approved and its board still created, and
the reason SHALL be reported with the approval.

#### Scenario: Approval starts the declared flow at its next tick

- **GIVEN** a proposed document whose delivery is a flow with agent dev, stopping when its queue empties, every 5 minutes
- **WHEN** the operator approves it
- **THEN** a flow declaring the document exists, naming dev, and holds the tasks the approval created
- **AND** it has not fired; its next run is the next 5-minute boundary

#### Scenario: A flow that cannot be created does not block approval

- **GIVEN** a proposed document whose delivery names an agent that has since been archived
- **WHEN** the operator approves it without choosing another agent
- **THEN** the document is approved and its board is created
- **AND** no flow is created, and the approval reports that the agent is archived

#### Scenario: An agent the project does not have is not given a flow

- **GIVEN** a proposed document whose delivery names an agent that is not one of the project's agents
- **WHEN** the operator approves it
- **THEN** the document is approved and no flow is created
- **AND** the approval reports that the agent is not on the project

#### Scenario: The operator replaces a stale agent at approval

- **GIVEN** a proposed document whose delivery names an archived agent
- **WHEN** the operator approves it choosing agent dev
- **THEN** the flow is created naming dev
- **AND** the document still names the archived agent, and the approval records the replacement

#### Scenario: Re-approval does not create a second flow

- **GIVEN** an approved document whose delivery created flow F, reopened and proposed again
- **WHEN** the operator approves it
- **THEN** no second flow is created, and the tasks the approval created belong to F
- **AND** the approval reports that F already builds the document

#### Scenario: Re-approval after the flow has ended says the new tasks wait

- **GIVEN** an approved document whose flow F stopped when its queue emptied and is not archived
- **WHEN** the document is reopened, revised with a new task, proposed and approved
- **THEN** no second flow is created
- **AND** the approval reports that F has ended and that the new task waits for it

#### Scenario: A replacement agent is not applied to an existing flow

- **GIVEN** an approved document whose flow F names agent dev, reopened and proposed again, whose delivery now names an archived agent
- **WHEN** the operator approves it choosing agent qa
- **THEN** no flow is created and F still names dev
- **AND** the approval reports that qa was not applied because F already declares the document

#### Scenario: An approval that gives the flow no tasks starts no flow

- **GIVEN** a proposed document whose delivery is a flow, and whose board cannot be created
- **WHEN** the operator approves it
- **THEN** the document is approved and no flow is created
- **AND** the approval reports that no flow was started because the approval gave it no tasks

#### Scenario: A delivery of no flow creates none

- **GIVEN** a proposed document whose delivery says no flow
- **WHEN** the operator approves it
- **THEN** its board is created and no flow is created

### Requirement: A Copilot reviewer may be told to consult Copilot's review agents

Where an agent bound to a `copilot` runner is given a review turn and the operator has chosen Copilot review agents for that agent, the review turn's context SHALL name those agents and the changes to hand them, and SHALL state that the verdict remains the reviewer's to record.

The reviewer remains an agent on the roster, resolved as every reviewer is. A Copilot review agent is
a tool that reviewer may use, not a reviewer. It cannot record a verdict, and resolving it as one
would be a second reviewer resolution.

The review agents on offer SHALL be those Copilot lets its main agent run as subagents: code review,
security review, and the critic. The choice SHALL be off by default, because each consultation is a
further billed model call.

The changes named SHALL run from where the work under review diverged from the branch approval merges
into, to the commit under review. Where that point cannot be determined, or is the commit itself,
the context SHALL name the commit alone and say to review that commit's own changes, and the review
turn SHALL still take place.

The choice SHALL be shown to the operator as it is stored, and SHALL be presented only for an agent
bound to a `copilot` runner. A stored choice SHALL be read as a list of offered agents: anything else
it holds SHALL NOT be named in the context.

Nothing else in the review context SHALL change. In particular, the verdict instruction SHALL stay as
it is.

#### Scenario: A reviewer with review agents chosen is told to consult them

- **WHEN** a Copilot agent whose operator chose code review is given a review turn
- **THEN** its context names the code-review agent by the exact name Copilot dispatches it by,
  and the range of changes to hand it
- **AND** says how to recover when the agent's model is not available on the operator's plan
- **AND** says not to describe a review the agent did not give
- **AND** says that the verdict is the reviewer's own and is recorded only by updating the task

#### Scenario: Without a choice the review context is unchanged

- **WHEN** a Copilot agent with no review agents chosen is given a review turn
- **THEN** its review context is the same as it is without this change

#### Scenario: An ordinary turn never names review agents

- **WHEN** a Copilot agent with review agents chosen is given a turn that is not a review
- **THEN** no review agent is named

#### Scenario: A reviewer on another runner is unaffected

- **WHEN** an agent bound to a runner other than `copilot` is given a review turn
- **THEN** no Copilot review agent is named, whatever its configuration holds

#### Scenario: Only the offered agents can be chosen

- **WHEN** an operator chooses a Copilot agent that is not among those offered
- **THEN** the choice is refused

#### Scenario: A stored choice outside the offer is not named

- **WHEN** an agent's stored configuration names a review agent that is not offered, or is not a list,
  because it was written by a route that does not check it
- **THEN** the review context names only the offered agents it holds, and none when it is not a list

#### Scenario: A review goes ahead without a divergence point

- **WHEN** a Copilot reviewer with review agents chosen is given a review turn for a project with no
  branch that approval merges into
- **THEN** the review turn takes place
- **AND** its context names the commit alone

#### Scenario: A divergence point that cannot be computed does not stop the review

- **WHEN** determining the divergence point fails for any reason, including the version-control
  command timing out
- **THEN** the review turn takes place with its context naming the commit alone
- **AND** nothing prepared for the review is left behind unreleased

#### Scenario: The choice is shown as stored

- **WHEN** the operator chooses code review for a Copilot agent and reopens its settings
- **THEN** code review is shown as chosen

### Requirement: A Copilot review turn records which review agents actually ran

Where a Copilot review turn's context named Copilot review agents, the run's stream SHALL record at the end of the turn which Copilot subagents ran in it, including that none did, as an event that stays visible when diagnostics are hidden.

A reviewer's own words about what its review agents found are not evidence that they ran: a
reviewer can claim a consultation that never happened. The Hub SHALL NOT judge the reviewer's prose;
it SHALL state, from the subagent events Copilot reported in that turn, what ran and what was named
but did not run, so that a claim and the record of what happened are read side by side.

#### Scenario: A review agent that was named but not run is reported

- **WHEN** a Copilot review turn whose context named the code-review agent ends without Copilot
  reporting any subagent
- **THEN** the run's stream records that the code-review agent was asked for and that no subagent ran

#### Scenario: A review agent that ran is reported with its outcome

- **WHEN** a Copilot review turn whose context named the code-review agent ends after Copilot
  reported that agent completing
- **THEN** the run's stream records that it ran, how it ended and the model it ran on

#### Scenario: The report is made when the turn fails too

- **WHEN** a Copilot review turn whose context named review agents fails or is stopped after Copilot
  was given the turn
- **THEN** the run's stream still records which subagents ran

#### Scenario: Without named review agents nothing is reported

- **WHEN** a Copilot turn ends whose context named no review agent, including every turn that is not
  a review
- **THEN** no report of review agents is recorded

### Requirement: A review turn is told the task's check result
In a project with checks, both review channels (the flow's review briefing and the review turn context) SHALL state the task's latest check result: passed, failed (naming the failing checks), running, or none yet. Where it is not `passed`, they SHALL say that `approved` will be refused until the checks pass, and that `revision_needed` with the failing output is the verdict that returns a failing task to its author.

#### Scenario: A reviewer is told the checks failed
- **WHEN** a review turn is given for a task whose latest check run failed
- **THEN** its briefing names the failing check and says `approved` will be refused and `revision_needed` returns it

#### Scenario: Nothing is said where there are no checks
- **WHEN** a review turn is given in a project with no checks configured
- **THEN** its briefing carries no check sentence

