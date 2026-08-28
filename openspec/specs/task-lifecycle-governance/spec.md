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

### Requirement: A task entering review must not still name its author as its holder

The system SHALL refuse a transition to `under_review` when the task's assignee is the **agent**
recorded as having moved it to `completed`. Where the task has no assignee, or no completer is
recorded, the transition SHALL be permitted.

This rule binds **every actor, including the operator**, and that is what distinguishes it from
author/reviewer separation above. That rule is about authority — who is entitled to sign work off —
and exempts the operator because a single-operator project must be able to approve anything. This
rule is about the state the move produces, which misdescribes the world whoever writes it: it
asserts that a reviewer holds the task while naming its author. An operator who intends to review
the work themselves SHALL do so by clearing or reassigning the assignee, which the refusal states.

The permitted cases are deliberate. An unassigned task claims that nobody holds it, so nothing is
false and no work is stranded. An unattributable one follows the same asymmetry the offer rule uses
— refuse to *offer* finished work whose author cannot be ruled out, but permit an actor to *act* on
it — because a rule that blocked every move it could not attribute would strand tasks completed
before transitions were recorded.

Because the assignee is read at the moment of the transition, any surface that sets both a status
and an assignee in one operation SHALL apply the assignee first, so that a single request naming a
reviewer and sending the task to review is accepted rather than refused on the assignee it replaces.

#### Scenario: Sending a task to review without reassigning it is refused

- **WHEN** a task is moved to `under_review` while still assigned to the agent that completed it
- **THEN** the request is refused with a typed error naming the remedy
- **AND** the task remains in its pre-request status

#### Scenario: The operator is bound by the same rule

- **WHEN** the operator makes that same move
- **THEN** it is refused on the same grounds

#### Scenario: Naming a reviewer in the same request succeeds

- **WHEN** one request sets the assignee to a different agent and the status to `under_review`
- **THEN** the request succeeds

#### Scenario: A task with no assignee may enter review

- **WHEN** a completed task with no assignee is moved to `under_review`
- **THEN** the request succeeds

#### Scenario: A task whose completer is unknown may enter review

- **WHEN** a completed task with no recorded completer is moved to `under_review`
- **THEN** the request succeeds

### Requirement: A review a flow cannot staff is not reported as staffed

A flow SHALL NOT treat a task in `under_review` as held by a reviewer when that task's assignee is
the agent recorded as completing it. It SHALL instead resolve a reviewer for it through the ordinary
reviewer ladder, which excludes the author, and record the result as a staffing outcome.

Such a task is claimable by nobody and its assignee counts as holding active work, so left
unrecognised it is never reviewed and its assignee is unavailable to review anything else in the
project, with nothing reporting either fact. This rule is what lets a task recorded that way before
the refusal above existed recover, rather than remaining stuck behind a rule that arrived later.

Recovery SHALL be a reassignment and SHALL NOT move the task to another status: the task is already
in review, and only who holds it was wrong.

#### Scenario: A task in review held by its own author is restaffed

- **WHEN** a flow fires on a queue holding such a task and an eligible reviewer exists
- **THEN** the task's assignee becomes that reviewer
- **AND** the task remains in `under_review`
- **AND** a review turn is dispatched to the new reviewer

#### Scenario: The author is never restaffed onto it

- **WHEN** a reviewer is resolved for such a task
- **THEN** the agent that completed the work is not among the candidates

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

### Requirement: A task can be waiting on a person

The system SHALL provide a status meaning that work began and cannot proceed until someone outside
the run supplies something. A task in that status SHALL be reachable only from the status meaning
work is under way, so that a task nobody has started is never described as waiting.

The status SHALL NOT have a direct edge to any status meaning the work is finished. Work that was
waiting and is now done SHALL pass back through the in-progress status first, so that no recorded
history states a task was completed while still waiting on a person who never answered.

#### Scenario: Work under way can become waiting

- **WHEN** a task whose work is under way is moved to the waiting status
- **THEN** the transition is accepted and recorded

#### Scenario: Work not yet started cannot be waiting

- **WHEN** a task that has not been started is moved to the waiting status
- **THEN** the move is refused as illegal
- **AND** the refusal names what is reachable instead

#### Scenario: A waiting task cannot be completed directly

- **WHEN** a task in the waiting status is moved directly to completed
- **THEN** the move is refused
- **AND** the task must return to the in-progress status first

#### Scenario: Waiting work can be redirected or abandoned

- **WHEN** the operator reassigns or rejects a task that is waiting
- **THEN** the transition is accepted

### Requirement: A task is recorded as waiting because the system observed it

The system SHALL move a task into the waiting status as a consequence of observing that the run
working on it ended with an unanswered question outstanding, attributed to that run and recorded as
system-caused.

The system SHALL move it back out when that question is answered.

A task SHALL NOT enter or leave the waiting status because an agent asserted that it should. An
agent that could declare itself blocked could claim to be waiting on a person it never asked, which
is the one claim a completion gate would most reward.

#### Scenario: A run that ends with a question outstanding leaves its task waiting

- **WHEN** a run bound to a task ends
- **AND** a blocking question it asked has not been answered
- **THEN** the task is recorded as waiting
- **AND** the transition names the run and is recorded as system-caused

#### Scenario: Answering releases the task

- **WHEN** the question that caused a task to be recorded as waiting is answered
- **THEN** the task returns to the in-progress status
- **AND** the transition is recorded

#### Scenario: An agent cannot declare itself waiting

- **WHEN** an agent requests the waiting status for its own task
- **THEN** the request is refused

#### Scenario: The operator may block and release directly

- **WHEN** the operator moves a task into or out of the waiting status
- **THEN** the transition is accepted and recorded as an operator action

### Requirement: A waiting task names what it is waiting for

A task in the waiting status SHALL carry a human-readable statement of what it is waiting for. Where
the system recorded the block, that statement SHALL be derived from the question asked. Where the
operator sets it directly, the system SHALL require the statement and SHALL refuse the transition
without one.

The statement SHALL be cleared whenever the task leaves the waiting status, by any route.

A status alone leaves the operator working out what they are holding up, which is the position they
were already in when the task said work was under way and nothing was happening. The status answers
"why is nothing moving"; only the statement answers "what do you need from me".

#### Scenario: A system-recorded block explains itself

- **WHEN** a run ends with an unanswered question and its task is recorded as waiting
- **THEN** the task states what it is waiting for
- **AND** that statement identifies the question asked

#### Scenario: An operator block without a statement is refused

- **WHEN** the operator moves a task to the waiting status without saying what it is waiting for
- **THEN** the transition is refused
- **AND** the task is unchanged

#### Scenario: Leaving the waiting status clears the statement

- **WHEN** a waiting task moves to any other status
- **THEN** it no longer states what it is waiting for

#### Scenario: A control offering the waiting status collects the statement

- **WHEN** an operator surface offers a move to the waiting status
- **THEN** it obtains the statement before requesting the move

### Requirement: Only an unanswered blocking question makes a task wait

The system SHALL record a task as waiting only on account of a question that is unanswered, marked
as blocking, and asked by the run whose end is being evaluated.

A question that does not block is the agent leaving a note and continuing; a task parked on one would
make the status mean that an agent mentioned something. A question left open by a different run is
not evidence that this run stopped for it.

#### Scenario: A non-blocking question does not make a task wait

- **WHEN** a run ends having asked a non-blocking question and without moving its task
- **THEN** the task is not recorded as waiting
- **AND** the run is divergent as normal

#### Scenario: An answered question does not make a task wait

- **WHEN** a run ends having asked a question that was answered, without moving its task
- **THEN** the task is not recorded as waiting

#### Scenario: Another run's open question does not make this task wait

- **WHEN** a run ends without moving its task
- **AND** the only unanswered blocking question was asked by a different run
- **THEN** the task is not recorded as waiting

### Requirement: Declining a question releases the task it parked

Where a question caused a task to be recorded as waiting, declining that question SHALL return the
task to the in-progress status and clear what it was waiting for, as an operator-caused transition.

The operator has stated the answer is not coming, so the task is no longer waiting on them. A task
left waiting would claim to be held up by a question that has been closed — a block with nothing
behind it, which is the state the requirement that a block names what it is waiting for exists to
prevent.

A declined question SHALL NOT cause a task to be recorded as waiting. Otherwise the run-boundary
check would park the task again on the question the operator just closed, and the release would be
undone by the mechanism it was meant to satisfy.

#### Scenario: Declining frees the task

- **WHEN** the operator declines the question that caused a task to be recorded as waiting
- **THEN** the task returns to the in-progress status
- **AND** it no longer states what it is waiting for

#### Scenario: A declined question does not park a task

- **WHEN** a run ends without moving its task
- **AND** the only outstanding blocking question it asked has been declined
- **THEN** the task is not recorded as waiting

#### Scenario: The boundary check applies again once released

- **WHEN** a task released by a decline is later dropped by a bound run
- **THEN** that run is divergent as normal

#### Scenario: Declining a question that parked nothing changes no task

- **WHEN** the operator declines a question that never caused a task to wait
- **THEN** no task changes status

### Requirement: Approval integrates the approved work

The transition into `approved` SHALL merge the approved work into the project's configured main branch, in the same operation that records the transition. Approval is what places work in the product, and a lifecycle whose terminal state carries no such meaning cannot answer whether anything it approved was ever shipped.

What is merged SHALL be the commit named by the task's accepted evidence footprints — the newest such commit per distinct branch — and SHALL NOT be the agent's branch.

**What actually lands SHALL be the approved task's work and nothing else.** Merging a commit brings that commit's whole ancestry, so naming a commit rather than a branch narrows the tip and nothing more. It is therefore not sufficient for the system to name a commit: the commit's ancestry SHALL correspond to the task, which is what per-task isolation of the work provides. Where a task's work was produced before that isolation existed and sits on a branch shared with other tasks, the system SHALL record which commits landed alongside it rather than claiming none did.

Evidence that is awaiting review or has been rejected SHALL NOT contribute a commit to integrate.

The merge SHALL be performed against the local repository only. The system SHALL NOT contact any remote, SHALL NOT push, and SHALL NOT require any credential.

Integration SHALL occur regardless of the rigor of any document the task's requirements belong to. Rigor governs who may bring a task to `approved`; integration is what reaching `approved` means. Were the two coupled, lowering a document's rigor to get past a blocked task would also silently stop that work being shipped.

#### Scenario: Approving a task puts its work on the main branch

- **WHEN** a task with accepted evidence naming a git commit is approved, and the project has a
  configured main branch
- **THEN** that commit is merged into the main branch
- **AND** coverage reports the served requirements as `integrated` rather than
  `verified, not integrated`

#### Scenario: Only the accepted evidence's commit is integrated

- **WHEN** a task is approved whose branch carries commits made after the commit its accepted
  evidence names
- **THEN** the later commits are not merged

#### Scenario: Another task's work does not land

- **WHEN** a task is approved while a different task, held by the same agent, has unreviewed commits
- **THEN** none of that other task's commits are on the main branch
- **AND** the integration record names no commits as having ridden along

#### Scenario: The approved task's own earlier work does land

- **WHEN** a task is approved whose work is several commits, the newest of which its accepted
  evidence names
- **THEN** every one of those commits is on the main branch

#### Scenario: A sketch document's task still integrates

- **WHEN** a task whose linked requirements belong to a `sketch`-rigor document is approved
- **THEN** the work is integrated exactly as it would be for a `gate`-rigor document

#### Scenario: No remote is contacted

- **WHEN** any approval integrates work
- **THEN** no push occurs and no remote operation is attempted

### Requirement: Approval is refused when the work cannot be merged cleanly

Where the work to be integrated would conflict with the project's main branch, the system SHALL
refuse the transition into `approved`.

The conflict SHALL be detected before the transition is recorded, by a test merge that modifies
neither the working tree nor the index. A conflict discovered during the merge itself would leave a
task recorded as approved and a repository in a state the operator did not ask for.

The refusal SHALL be carried in the same typed refusal that reports unverified requirements, and
SHALL name the conflicting paths. An operator learning that approval failed SHALL learn why in the
same response, not by inspecting the repository.

This refusal SHALL apply regardless of rigor. It is not an assertion about whether the work is
verified; it is an assertion that the work cannot go where approval says it goes.

The check SHALL live inside the single transition service, and SHALL NOT introduce a second
enforcement point.

#### Scenario: A conflicting branch refuses approval

- **WHEN** approval is requested for a task whose evidence commit conflicts with the main branch
- **THEN** the transition is refused
- **AND** the refusal names the conflicting paths
- **AND** the task's status is unchanged
- **AND** no merge is attempted

#### Scenario: A conflict refuses approval even at sketch rigor

- **WHEN** approval is requested for a task with conflicting work whose documents are all `sketch`
- **THEN** the transition is refused

### Requirement: An integration that cannot proceed does not block approval

The transition into `approved` SHALL still succeed where integration cannot be attempted, and the
integration SHALL be recorded as skipped together with the reason. Integration cannot be attempted
when the project has no configured main branch, when the project is not a repository, when the
primary checkout has uncommitted changes to tracked files, or when the primary checkout is not on
the main branch.

Untracked files SHALL NOT prevent integration. The system writes specification documents into the
project directory, so untracked content is the ordinary state of a working project rather than a
signal that a merge is unsafe.

Where integration is attempted and fails, the transition SHALL NOT be rolled back. The approval is a
judgement that the work is good; a repository failure SHALL NOT reverse it. Coverage SHALL then
report the requirement as `verified, not integrated`, which is a true statement of what happened.

A project that is not a repository SHALL be no less approvable than before this capability existed.

#### Scenario: An unconfigured main branch does not block approval

- **WHEN** a task is approved in a project with no configured main branch
- **THEN** the approval succeeds
- **AND** nothing is merged
- **AND** the skipped integration is recorded with its reason

#### Scenario: A dirty primary checkout skips rather than merges

- **WHEN** a task is approved while the primary checkout has uncommitted changes to tracked files
- **THEN** the approval succeeds, no merge is attempted, and the reason is recorded

#### Scenario: Untracked files do not prevent a merge

- **WHEN** a task is approved while the project directory holds untracked files
- **THEN** the work is integrated

#### Scenario: A failed merge leaves the approval standing

- **WHEN** integration is attempted and the merge fails
- **THEN** the task remains `approved`
- **AND** coverage reports the served requirements as `verified, not integrated`

#### Scenario: A project without a repository approves unchanged

- **WHEN** a task is approved in a project whose evidence footprints record paths rather than commits
- **THEN** the approval succeeds and no integration is attempted

### Requirement: Every integration attempt is recorded

The system SHALL record each integration attempt: the task, the commit and branch integrated, the
target branch, the outcome (`merged`, `skipped` or `failed`), the reason where it did not merge, the
approving actor, and the time.

The record SHALL be append-only, with no update path and no delete path. An integration is a write to
the operator's repository performed by the system, and the account of what was written SHALL NOT be
editable by the thing that wrote it.

The record SHALL state how the integration was performed, so that a later mode which integrates by a
different mechanism is distinguishable in the history rather than conflated with this one.

#### Scenario: A merge is recorded with what it merged

- **WHEN** an approval integrates work
- **THEN** a record names the commit, the source branch, the target branch, the outcome and the
  approving actor

#### Scenario: Integration records cannot be altered

- **WHEN** any interface attempts to update or delete an integration record
- **THEN** no such path exists

### Requirement: Work already in the main line is not reported as merged

Where the work to integrate is already reachable from the target branch, the system SHALL record the
integration as skipped, naming that as the reason, and SHALL NOT record it as merged.

Merging a commit that is already an ancestor of the target succeeds, reports success, and changes
nothing. Recording that as a merge makes a no-op indistinguishable from work reaching the product,
which is the one thing integration reporting exists to distinguish.

This SHALL be determined before any precondition concerning the state of the working tree. Whether a
commit is already present is a fact about the commit and the target alone, and an operator whose
checkout is mid-edit is better told the true reason than told to tidy up for a merge that would
change nothing.

#### Scenario: An already-integrated commit is skipped

- **WHEN** a task is approved whose accepted evidence names a commit already reachable from the
  target branch
- **THEN** the integration is recorded as skipped
- **AND** the reason states the work is already in the target branch
- **AND** the target branch is unchanged

#### Scenario: The true reason wins over a working-tree complaint

- **WHEN** the commit is already in the target branch and the project's checkout also has
  uncommitted changes
- **THEN** the reason given is that the work is already integrated

### Requirement: Approval creates the work its document declares

A document's approval SHALL create the tasks that document declares, each linked to the requirements
it declares that it serves.

A document that declares its own decomposition and produces nothing leaves the operator to
re-describe by hand work the document already contains, and leaves no relationship between the two.

Tasks SHALL be created unassigned and in the lifecycle's entry status. The document states that the
work exists; who performs it is not a decision a specification makes.

Creation SHALL be idempotent per document and declared task, so that re-approving a document after
revision creates only what is new.

A task that already exists for a declared task SHALL NOT be modified, reassigned or reverted by a
later approval. The document declares that work exists, not what has happened to it since.

A document declaring no tasks SHALL create none, and this SHALL NOT be an error.

Where a declared task names a requirement the document does not resolve, the task SHALL still be
created and the unresolved reference SHALL be preserved rather than discarded.

#### Scenario: Approving a document creates its declared tasks

- **WHEN** a document declaring tasks is approved
- **THEN** a task is created for each declared task
- **AND** each is linked to the requirements it declared it serves
- **AND** each is unassigned

#### Scenario: Re-approving creates no duplicates

- **WHEN** a document is revised and approved again
- **THEN** tasks already created for its declared tasks are not duplicated
- **AND** tasks declared for the first time are created

#### Scenario: Work already under way is left alone

- **WHEN** a document is approved again after a task it declared has been moved out of its entry
  status
- **THEN** that task's status and assignee are unchanged

#### Scenario: A document declaring no tasks creates none

- **WHEN** a document declaring no tasks is approved
- **THEN** no tasks are created
- **AND** the approval succeeds

### Requirement: An integration that was skipped can be attempted again

The system SHALL offer a way to attempt integration again for an approved task whose work has not been integrated, and SHALL name that way when it reports a skip the operator can put right.

Integration is attempted when a task becomes approved. Where it is skipped, the cause is usually
something the operator can then put right — a main branch that was never named, a checkout with
uncommitted changes, a checkout parked on another branch. Restating the approval does not attempt it
again, because restating a status is deliberately a no-op, so without this the remediation the
system asked for accomplishes nothing.

A skip SHALL NOT instruct the operator to approve the task again. The task is already approved by the
time the skip is read, and following that instruction provably does nothing: the request succeeds,
the status is unchanged, no attempt is recorded, and nothing is merged. An instruction that fails
silently is worse than none, because it spends the operator's confidence as well as their time.

Where a skip names a cause the operator can put right, it SHALL point at the remedy that works —
retrying the integration, or the setting whose absence caused the skip.

Retrying SHALL be available to the operator and to agents, and SHALL be refused for a task that is
not approved.

Retrying a task whose work has already been integrated SHALL be permitted and SHALL merge nothing.
Whether work has reached the main line is a question about the repository, so it is asked again
rather than inferred from what was previously attempted.

Every retry SHALL be recorded exactly as a first attempt is.

An agent able to retry SHALL be able to read what the attempts reported. An agent that can act on an
outcome it cannot see is acting blind.

#### Scenario: Work a skip left behind is merged on retry

- **WHEN** an approved task's integration was skipped
- **AND** the cause is put right and integration is retried
- **THEN** the work is merged into the project's main branch
- **AND** the retry is recorded

#### Scenario: Retrying an unapproved task is refused

- **WHEN** integration is retried for a task that is not approved
- **THEN** the request is refused
- **AND** nothing is merged

#### Scenario: Retrying after a merge merges nothing

- **WHEN** integration is retried for a task whose work is already on the main branch
- **THEN** nothing is merged
- **AND** the attempt is recorded as skipped because the work is already there

#### Scenario: An agent reads and retries

- **WHEN** an agent asks what a task's integration attempts reported
- **THEN** it receives them
- **AND** it may retry the integration

#### Scenario: A skip does not send the operator back to approval

- **WHEN** integration is skipped because the checkout has uncommitted changes
- **THEN** the reason does not instruct the operator to approve the task again

#### Scenario: A skip names the remedy that works

- **WHEN** integration is skipped because the checkout has uncommitted changes or is on another
  branch
- **THEN** the reason directs the operator to retry the integration once the cause is put right

### Requirement: Naming the main branch attempts the integrations that wanted one

The system SHALL attempt integration again, when a project's main branch is set, for approved tasks whose most recent integration was skipped for want of one.

Skipping for want of a main branch tells the operator to choose one in the project's settings.
Discharging that instruction at the moment the operator follows it is what makes the sentence true;
leaving it undischarged means the system asked for something and then ignored it.

Only that cause SHALL be answered this way. Naming a branch says nothing about a checkout with
uncommitted changes or one parked elsewhere, and a merge that failed outright wants a person rather
than a repetition.

Setting the branch SHALL succeed even where the attempt that follows it does not. The operator
changed a setting, and that must stand or fall on its own terms.

#### Scenario: Setting the branch merges the work that was waiting for it

- **WHEN** an approved task's integration was skipped because no main branch was set
- **AND** the operator sets the project's main branch
- **THEN** the work is merged
- **AND** the task is not reopened to achieve it

#### Scenario: Other skips are left alone

- **WHEN** an approved task's integration was skipped because the checkout had uncommitted changes
- **AND** the operator sets the project's main branch
- **THEN** that task's integration is not attempted again

#### Scenario: The setting is saved even when the attempt fails

- **WHEN** setting the main branch triggers an attempt that raises
- **THEN** the main branch is still saved

### Requirement: A task reports the requirement identifiers it was given

A task's representation SHALL report the requirement identifiers linked to it, in the form those identifiers are supplied in.

Identifiers are accepted when a task is created and when it is updated. Reporting them nowhere makes
the field write-only, so a caller cannot confirm what was recorded, and anyone diagnosing why work
did not merge sees a task that appears to be tied to nothing while the links that govern the merge
exist.

The identifiers reported SHALL be the same ones accepted, not the system's internal row identity, so
that what is read back can be submitted again.

Identifiers SHALL be reported in an order that reads as the operator numbered them, comparing the
numeric parts of an identifier by value. Ordering them as plain text places an eleventh requirement
between the first and the second, which reads as a defect in data that is correct and costs a
diagnosis every time someone checks what a task is tied to.

An identifier with no numeric part SHALL still be ordered deterministically. Identifiers are
authored by the operator and nothing constrains their shape.

References that resolved to no requirement SHALL NOT be reported among them. They are already
reported as unresolved, and repeating them here would invite a caller to resubmit a reference that
has already failed.

#### Scenario: A task reports the identifiers it was created with

- **WHEN** a task is created naming requirement identifiers
- **AND** the task is read back
- **THEN** it reports those identifiers

#### Scenario: Unresolved references are not reported as links

- **WHEN** a task names a requirement identifier that matches nothing
- **THEN** the identifier is reported as unresolved
- **AND** it is not reported among the task's linked identifiers

#### Scenario: Identifiers are ordered by number

- **WHEN** a task is linked to requirements numbered 1, 2 and 11
- **THEN** they are reported in that order

#### Scenario: An identifier without a number is still ordered

- **WHEN** a task is linked to a requirement whose identifier has no numeric part
- **THEN** the reported order is deterministic

### Requirement: Approval is refused while a gated requirement is unverified

Where a task links requirements whose document rigor is `gate`, the system SHALL refuse the
transition into `approved` while any of those requirements is not verified.

The check SHALL run inside the same transition service every status write already passes through,
and SHALL NOT exist as a second enforcement point. A second point is a second thing to bypass, and
the rule that no route may assign a task's status directly is what makes one point sufficient.

Verification SHALL be determined by the same coverage computation the document and project surfaces
use. A gate that computed its own answer could refuse a task while the document beside it reported
everything satisfied, and nothing would establish which was wrong.

`sketch` and `contract` requirements SHALL report their state and SHALL NOT block the transition.
A requirement that is structurally invalid or carries no identifier SHALL prevent a gate from
passing, and SHALL be reported as the diagnostic it is rather than as an unverified requirement.

The refusal SHALL be typed, and SHALL name each requirement that caused it together with what would
satisfy it — no linked evidence, evidence awaiting review, or evidence that no longer applies to the
current wording. A refusal that does not say what to do about it cannot be acted on, and an
unactionable gate is turned off.

The refusal SHALL hold identically across every access path: the operator's interface, an agent's
HTTP action, the tool surface, and a scheduled job.

#### Scenario: An unverified gated requirement refuses approval

- **WHEN** approval is requested for a task linking a `gate`-rigor requirement with no accepted
  evidence for its current wording
- **THEN** the transition is refused
- **AND** the task's status is unchanged
- **AND** no transition is recorded

#### Scenario: The refusal says what would satisfy it

- **WHEN** approval is refused by the gate
- **THEN** the response names each blocking requirement's identifier and why it is not verified

#### Scenario: Accepting the evidence opens the gate

- **WHEN** the evidence for the blocking requirement is accepted
- **AND** approval is requested again
- **THEN** the transition succeeds

#### Scenario: A sketch does not block

- **WHEN** approval is requested for a task whose linked requirements are all `sketch` rigor and
  unverified
- **THEN** the transition succeeds

#### Scenario: A contract does not block

- **WHEN** approval is requested for a task whose linked requirements are `contract` rigor and
  unverified
- **THEN** the transition succeeds
- **AND** their state is still reported

#### Scenario: A task linking nothing is unaffected

- **WHEN** approval is requested for a task with no linked requirements
- **THEN** the transition succeeds

#### Scenario: Completion is not blocked by the gate

- **WHEN** a task serving an unverified `gate` requirement is moved to `completed`
- **THEN** the transition succeeds

#### Scenario: The gate holds over every access path

- **WHEN** approval of a blocked task is attempted through the tool surface or a scheduled job
- **THEN** it is refused on the same terms as through the operator's interface

#### Scenario: A broken requirement blocks a gate rather than passing it

- **WHEN** a `gate`-rigor document contains a requirement with no identifier
- **AND** approval is requested for a task linking that document's requirements
- **THEN** the transition is refused, reporting the diagnostic

### Requirement: A transition records the policy that governed it

Every recorded transition SHALL carry the policy in force when it was decided.

Which rigor a document holds is editable by the operator. Without recording what governed a
decision, a gate that passed last month cannot be explained today — and the policy being editable is
what turns that from a theoretical concern into a live one.

#### Scenario: A passed gate stays explicable

- **WHEN** a task is approved under a gate
- **AND** the document's rigor is later changed
- **THEN** the recorded transition still states the policy that applied when it was approved

### Requirement: A task list can be scoped to one loop's queue

The Hub SHALL let a caller of the task list scope the result to exactly the tasks that name one
loop, and SHALL apply no other filter to that scoped result — an explicit loop scope SHALL show
every task naming it, regardless of that task's own status.

A scope naming a loop with no queued tasks SHALL return an empty list, and this SHALL NOT be an
error.

#### Scenario: Scoping to a loop returns exactly its queued tasks

- **WHEN** the task list is requested scoped to one loop
- **THEN** every task naming that loop is returned
- **AND** no task naming a different loop, or naming none, is returned

#### Scenario: A loop-scoped view hides nothing regardless of status

- **WHEN** the task list is scoped to a loop that owns a task in a terminal status
- **THEN** that task is included in the scoped result

### Requirement: A task list can be scoped to one specification document's declared work

The Hub SHALL let a caller of the task list scope the result to exactly the tasks one specification
document declared, and SHALL apply no other filter to that scoped result — an explicit scope SHALL
show every task the document declared, regardless of that task's own status or its declaring
document's phase.

A scope naming a document with no declared tasks SHALL return an empty list, and this SHALL NOT be
an error.

#### Scenario: Scoping to a document returns exactly its declared tasks

- **WHEN** the task list is requested scoped to one specification document
- **THEN** every task whose declaring document is that document is returned
- **AND** no task whose declaring document is a different document is returned

#### Scenario: A scoped view hides nothing regardless of status or phase

- **WHEN** the task list is scoped to a document that is itself archived
- **AND** that document declared a task whose own status is terminal
- **THEN** that task is included in the scoped result

### Requirement: The task list's default view retires completed work from archived documents

The Hub SHALL offer a task list mode that excludes a task if, and only if, the task's declaring
document has reached the `archived` phase and the task's own status is terminal. This exclusion
SHALL NOT be applied unless the caller asks for it, so a caller that does not ask for it — including
every caller that existed before this exclusion was added — SHALL see every task exactly as before.

A task with no declaring document SHALL NOT be excluded by this mode, regardless of its status.

An open (non-terminal) task whose declaring document is archived SHALL NOT be excluded by this
mode — work someone still has to do is not retired because the document that described it was
tidied away.

This exclusion SHALL NOT alter any task's status, assignee, or any other field. It changes only
what a request that asks for it is shown.

#### Scenario: A completed task from an archived document is excluded

- **WHEN** the exclusion mode is requested
- **AND** a task's declaring document is archived
- **AND** that task's own status is terminal
- **THEN** that task is absent from the result

#### Scenario: An open task from an archived document is not excluded

- **WHEN** the exclusion mode is requested
- **AND** a task's declaring document is archived
- **AND** that task's own status is not terminal
- **THEN** that task is present in the result

#### Scenario: A task with no declaring document is never excluded

- **WHEN** the exclusion mode is requested
- **AND** a task has no declaring document
- **THEN** that task is present in the result regardless of its status

#### Scenario: The exclusion is opt-in

- **WHEN** the task list is requested without asking for the exclusion mode
- **THEN** every task is returned, including ones the exclusion mode would have hidden

#### Scenario: Exclusion never mutates a task

- **WHEN** the exclusion mode causes a task to be absent from one request's result
- **THEN** a subsequent unscoped request for that same task returns it with every field unchanged

### Requirement: A task's requirement links are visible where the operator manages the task

The interface presenting a task to the operator SHALL show which specification requirements, if any,
the task is linked to, without requiring the operator to open the task's full detail first.

Where a linked requirement's only current evidence was rejected, that MUST be visually distinguished
from a link to a requirement with no such rejection, so a task that looks approvable does not hide a
refused claim inside it.

#### Scenario: A task's linked requirements are visible on the board

- **WHEN** a task linked to one or more specification requirements is shown on the task board
- **THEN** the identifiers of its linked requirements are visible without expanding the task

#### Scenario: A rejected requirement's link is visually distinct

- **WHEN** a task is linked to a requirement whose only current evidence was rejected
- **THEN** that link is shown with a treatment distinct from a link carrying no such rejection

### Requirement: A task's full detail opens in a view sized to hold it

The interface SHALL present a task's full detail — description, acceptance criteria, deliverables,
notes, and requirement links — in a view sized independently of the task board's column layout, not
constrained to the width of a board column.

#### Scenario: A task with substantial detail is fully readable when opened

- **WHEN** the operator opens a task carrying a long description, multiple acceptance criteria, and
  requirement links
- **THEN** every one of those is rendered without being clipped or requiring the board column's own
  width

### Requirement: Navigating from a task's requirement link reaches that requirement in its document

Following a task's link to one of its requirements SHALL open the specification document that
declares it, scrolled to that requirement, not merely to the top of the document.

#### Scenario: Following a requirement link reaches the requirement itself

- **WHEN** the operator follows a task's link to a specific requirement
- **THEN** the specification document opens with that requirement in view

### Requirement: A task's loop is set by a named writer when the task is created

The Hub SHALL set a task's loop only at creation, and only from one of two writers: the approval of a
specification document bound to that loop, or the loop's creator adding the task directly.

A task's loop SHALL NOT be changed after creation, by any actor. Moving finished or in-flight work
between loops would make a loop's queue history — and therefore its stop condition, which is derived
from that history — unable to answer what work the loop was ever given.

#### Scenario: A task created outside either writer has no loop

- **WHEN** a task is created by any path other than a bound document's approval or its loop's creator
- **THEN** the task has no loop
- **AND** it does not appear in any loop's queue

#### Scenario: A task's loop cannot be reassigned

- **GIVEN** a task that belongs to a loop's queue
- **WHEN** any actor attempts to change which loop it belongs to
- **THEN** the attempt is refused
- **AND** the task's loop is unchanged

#### Scenario: A terminal task remains in its loop's queue history

- **GIVEN** a task in a loop's queue that has reached a terminal status
- **WHEN** the loop's queue history is retrieved
- **THEN** the task is included

### Requirement: Starting work is gated on its prerequisites, and the gate lives with the other gates

The transition to in-progress SHALL be guarded by the task's dependencies, and that guard SHALL be
applied in the same place as the machine's existing guards — inside the transition service, before
the history row is written.

Placement is the requirement, not an implementation note. The existing gates are positioned there
precisely so that no caller can reach a status write another way, which is what gives every surface —
the operator's route, the agent capability plane, the tool surface, scheduled jobs — the same
enforcement without any of them knowing it exists. A dependency check applied at a route, or in the
board, would be a rule that holds for the callers somebody remembered.

#### Scenario: Every surface is gated identically

- **WHEN** a task with an unmet prerequisite is moved to in-progress through any surface
- **THEN** the move is refused

#### Scenario: The refusal is distinguishable from an illegal transition

- **WHEN** a start is refused for an unmet prerequisite
- **THEN** the refusal identifies the cause as a dependency rather than as an illegal edge

### Requirement: Gating start does not gate assignment

The transition to assigned SHALL NOT be gated by dependencies.

Assigning is a statement about who will do a piece of work; starting is a statement that it is being
done. Gating assignment would make it impossible to assign a wave of work in advance, and would force
whatever performs assignment to run again each time a prerequisite cleared.

#### Scenario: Work can be assigned before it can start

- **WHEN** a task with unmet prerequisites is assigned
- **THEN** the assignment succeeds
- **AND** the task still cannot be started

### Requirement: A task with no declared dependencies is unaffected

Where a task declares no dependencies, its transitions SHALL behave exactly as they did before
dependencies existed.

Every project gains this guard at once. It is safe to do so only because a task with nothing declared
has nothing that can fail, and that property is what makes the change deployable without a migration
of behaviour.

#### Scenario: An existing task is unaffected

- **WHEN** a task created before dependencies existed is moved through its lifecycle
- **THEN** every transition behaves as before

### Requirement: Every task status is classified into exactly one lifecycle band

The Hub SHALL classify every task status the transition machine defines into exactly one lifecycle
band, and SHALL fail to start when a status is classified into none or into more than one.

A status is defined by the transition machine when it appears as an origin or a destination in the
project's task transition map. The classification SHALL be checked against that map rather than
against a hand-maintained list of statuses.

#### Scenario: Every defined status has a band

- **WHEN** the set of statuses in the transition map is compared against the classification
- **THEN** every status appears in exactly one band

#### Scenario: An unclassified status is refused at startup

- **WHEN** a status exists in the transition map and is absent from the classification
- **THEN** the Hub fails to start, naming the unclassified status

#### Scenario: A doubly-classified status is refused at startup

- **WHEN** a status appears in more than one band
- **THEN** the Hub fails to start, naming the status and the bands

### Requirement: Status sets are derived from the classification, not listed independently

Any set of task statuses SHALL be derived from the lifecycle classification rather than enumerated
at its point of use — including every set used to answer whether a task is live, claimable,
terminal, active, or the current item of a queue.

Deriving these sets SHALL NOT change which statuses any of them contains. Each set SHALL contain
exactly the statuses it contained before being derived.

**A derived set SHALL be defined by the question it answers, and two sets answering different
questions SHALL NOT be merged even where their members overlap.** Deriving from one classification
is a requirement about where membership comes from, never a licence to collapse distinct questions
into one set.

#### Scenario: A derived set matches what it replaced

- **WHEN** a status set is derived from the classification
- **THEN** its members are identical to the members it was defined with beforehand

#### Scenario: Two sets that answer the same question are one set

- **WHEN** two call sites need the same classification of task statuses
- **THEN** they read the same derived set rather than each defining one

#### Scenario: Two sets that answer different questions stay distinct

- **WHEN** one call site asks which statuses a firing may claim and another asks which statuses can
  be a queue's current item
- **THEN** they read different derived sets
- **AND** a status that is claimable by neither, yet is a queue's current work, appears in the
  second and not the first

#### Scenario: Deriving a set does not remove a status from a surface that showed it

- **WHEN** a set is replaced by a derivation
- **THEN** no surface that displayed a task before the change stops displaying it

#### Scenario: A new status reaches every derived set

- **WHEN** a status is added to the transition map and classified into a band
- **THEN** every derived set that includes that band includes the new status, with no further edits

### Requirement: A run may only complete the task it holds

Moving a task to `completed` as a run actor SHALL require that the acting run is bound to that task.
A run bound to a different task, or to none, SHALL be refused. The operator SHALL be unaffected.

This closes the only path by which unearned work reaches the default branch. Because `completed`
sits in the awaiting-handoff band, a task falsely marked complete is offered to another agent as
reviewable work; that reviewer finds the code correct — it is, because a different agent really did
it — approves, and integration merges. No human is on that path and no single statement along it is
false.

The gate SHALL live where the dependency and requirement gates already live, so that every surface
— operator route, agent HTTP, tool surface, scheduled jobs and the runtime binding — is covered
without knowing it exists.

Completion SHALL NOT begin requiring evidence. Evidence is accepted after review and review follows
completion, so requiring it here would deadlock the ordinary path. The question this gate asks is
*who*, not *how much proof*.

#### Scenario: An unbound run tries to complete a task
- **WHEN** a run carrying no task binding moves a task to `completed`
- **THEN** the transition SHALL be refused
- **AND** the refusal SHALL state that the run is not bound to that task

#### Scenario: A run completes a task it holds
- **WHEN** a run bound to a task moves that task to `completed`
- **THEN** the transition SHALL be permitted

#### Scenario: A run tries to complete a peer's task
- **WHEN** a run bound to task A moves task B to `completed`
- **THEN** the transition SHALL be refused
- **AND** the refusal SHALL name the task the run is bound to

#### Scenario: The operator completes a task
- **WHEN** the operator moves a task to `completed`
- **THEN** the transition SHALL be permitted with no binding required

#### Scenario: A run that claimed the work can finish it
- **WHEN** a run claims a `pending` task, becoming bound to it, and later completes it
- **THEN** both transitions SHALL be permitted

### Requirement: A finished task's checkout is released, and its branch is not

A task's isolated checkout SHALL be released when the task reaches a terminal status, and its branch SHALL NOT be removed.

Releasing the checkout is what bounds how much of a repository the system occupies. Agents are bounded by the roster; tasks are bounded by nothing, so a checkout per task that is never released grows without limit, and the first symptom would be a git failure in an unrelated turn.

Release SHALL follow the same discipline as releasing any working checkout: any uncommitted change SHALL be committed onto the task's branch first, the branch SHALL be kept, and commits the branch carries beyond the main line SHALL be reported rather than discarded. Nothing an agent produced is destroyed by a release.

Release SHALL happen after the transition's own integration has run, so that what integration merges is never affected by what release commits.

Release SHALL NOT be able to fail a transition. A checkout that cannot be removed is a condition to report, not a reason to reverse a judgement about whether work was good — the same rule integration already follows.

Because a terminal status can be left again, a task whose work resumes SHALL have its checkout re-provisioned with its previous work present. That is what keeping the branch is for.

A task's terminal status SHALL be the only thing that releases its checkout. Removing from the roster the agent that was working a task SHALL release that agent's own checkout and SHALL NOT release the task's. A task outlives whoever held it: its status is unchanged by a roster edit, another agent may be assigned to continue it, and releasing its checkout would take the working tree away from a task for a reason that says nothing about the task. The work would survive on the branch either way — this is about not making a roster edit act on the task lifecycle.

#### Scenario: Removing an agent leaves the checkouts of its tasks alone

- **WHEN** an agent holding a task with its own checkout is removed from the roster
- **THEN** the agent's own checkout is released
- **AND** the task's checkout still exists, and the task's status is unchanged

#### Scenario: An approved task's checkout is released

- **WHEN** a task is approved
- **THEN** its checkout directory no longer exists
- **AND** its branch still exists, at the same commit

#### Scenario: A rejected task's work survives its release

- **WHEN** a task is rejected
- **THEN** its checkout directory no longer exists
- **AND** every commit made on its branch is still reachable

#### Scenario: Integration is unaffected by release

- **WHEN** a task with accepted evidence naming a commit is approved
- **THEN** the commit merged into the main branch is the one the evidence names, not one created
  while releasing the checkout

#### Scenario: A reopened task gets its work back

- **WHEN** an approved task is moved to `revision_needed` and worked again
- **THEN** its checkout is provisioned again, containing the work it had before it was released

#### Scenario: A release that fails does not undo the transition

- **WHEN** releasing a task's checkout fails
- **THEN** the task is still in its terminal status
- **AND** the failure is recorded

### Requirement: Dispatching a review staffs the task, whichever path dispatched it

The system SHALL, when it dispatches a turn to review a task, record that reviewer as the task's
holder and move the task into review, before the reviewing turn begins. This SHALL hold for every
path that dispatches a review, and SHALL NOT depend on which path did.

The holder SHALL be written before the move, so that a task entering review never names its author
as its holder at the moment the move is judged.

Staffing SHALL be idempotent. Where the task is already held by that reviewer and already in review,
dispatching SHALL leave both unchanged and SHALL travel no transition, so that a task does not
accumulate a record of being entered into review more than once for one review.

A review that cannot be staffed SHALL be refused before a turn is started, and the refusal SHALL be
the one the attempted staffing produced rather than a restatement of it. Refusing after a turn has
begun is not sufficient: the cost of the turn has already been paid and the reviewer's conclusion
has nowhere to go.

A review SHALL be refused where the named task is neither awaiting review nor already under review.
Staffing records a holder, and recording a holder for work that is not at a point where it can be
reviewed takes that work from whoever holds it while moving it nowhere. The refusal SHALL name the
status the task is actually in.

A review SHALL be refused where the named task is already under review and held by a different
reviewer. Replacing that holder is a handover, and a handover that travels no transition leaves the
task's recorded history unable to explain who holds it or why it changed. The refusal SHALL name the
current holder.

A refusal SHALL reach the requester as a refusal. Where a review is requested through an interface
that reports success or failure, that interface SHALL report the refusal, and SHALL NOT report the
request as accepted with the refusal carried as a reason for waiting. A request that can never
succeed is not a request that is waiting.

A refused review SHALL leave nothing provisioned. The refusal SHALL be raised before the reviewer's
checkout is created, not compensated for afterwards, and the task SHALL be left exactly as the
refusal found it.

Staffing SHALL NOT be performed when the request to review is recorded. It SHALL be performed when
the turn is dispatched, so that a request that is never delivered leaves no task held by a reviewer
that never ran.

#### Scenario: A review started by hand leaves the reviewer able to record a verdict

- **WHEN** the operator starts a review of a completed task by hand, naming a reviewer that is not
  its author
- **THEN** the task is held by that reviewer and is in review before the turn begins
- **AND** the reviewer can move the task to the outcomes available from review without any further
  operator action

#### Scenario: The holder is recorded before the move is judged

- **WHEN** a review is dispatched for a task whose recorded holder is still the agent that completed
  it
- **THEN** the reviewer replaces that holder before the move into review is judged
- **AND** the move is not refused on account of the holder it had beforehand

#### Scenario: Dispatching a review that is already staffed changes nothing

- **WHEN** a review is dispatched for a task already in review and already held by that same
  reviewer
- **THEN** the task's status and holder are unchanged
- **AND** no additional transition is recorded for it

#### Scenario: A review that cannot be staffed is refused before the turn starts

- **WHEN** a review is requested naming the task's own author as its reviewer
- **THEN** the request is refused
- **AND** no reviewing turn has been started
- **AND** the refusal states what would make the request succeed

#### Scenario: A task that is not awaiting review is refused, and keeps its holder

- **WHEN** a review is requested for a task that is being worked rather than awaiting review
- **THEN** the request is refused, naming the status the task is in
- **AND** the task's holder is unchanged
- **AND** no reviewing turn has been started

#### Scenario: A review already held by another reviewer is not silently taken

- **WHEN** a review is requested for a task already under review and held by a different reviewer
- **THEN** the request is refused, naming the current holder
- **AND** the task's holder is unchanged

#### Scenario: A refusal is reported as a refusal, not as acceptance

- **WHEN** the operator requests a review that cannot be dispatched
- **THEN** the response reports the request as refused, with the reason
- **AND** the request is not reported as accepted or as awaiting anything
- **AND** no queued work remains that would retry it

#### Scenario: A refused review leaves no checkout behind

- **WHEN** a review is requested and refused for any reason
- **THEN** no checkout has been created for the reviewer or the named task
- **AND** the task's status and holder are as they were before the request

#### Scenario: A request that is never delivered leaves the task untouched

- **WHEN** a review is requested and the turn is never dispatched
- **THEN** the task's status and holder are unchanged
