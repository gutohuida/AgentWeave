## MODIFIED Requirements

### Requirement: An agent cannot approve the work it produced

The system SHALL refuse a transition to `approved` requested by an agent when that same **agent**
recorded the task's transition into `completed`. Author and reviewer MUST be distinct **agents**.

Distinctness is on agent identity, not run identity. Every turn an agent takes is a new run, so a
rule requiring only "a different run" is satisfied by an agent continuing its own work and forbids
nothing — observed in live use on 2026-08-10, when an agent completed a task on one run and
approved it on the next.

**Where no agent is recorded as completing the task, the system SHALL refuse the transition when the
requesting agent is recorded as having produced evidence for that task.** An operator completion
records no agent, and a task written straight into `completed` records nothing at all; in both the
comparison this rule is built on has nothing to compare, and permitting on that basis let an agent
approve work it had itself recorded as its own — measured on a live Hub on 2026-09-09, where an
agent recorded implementation evidence for a task, the operator marked the task finished, and the
same agent's approval was accepted with nothing refusing it and nothing recording that it had
happened.

This does not weaken the permission that an unattributable move receives. Refusing every move the
system cannot attribute would stop legitimate work over a missing history row; this refuses on the
strength of a **record that exists** — an evidence row in which the agent named this task as the
subject of its own work.

**That fallback SHALL be the evidence record alone, and SHALL NOT be the wider determination of
which agents may have authored the task.** The wider determination includes the agent the task is
assigned to, and a task dispatched for review is assigned to its reviewer — so comparing against it
would refuse the reviewer the system itself staffed, on every operator-completed task, which is the
whole of the review path this rule exists to protect. Of the records that associate an agent with a
task, the evidence is the one the act of reviewing does not create.

**Evidence SHALL refuse its author whatever the state of its review.** An agent whose evidence was
rejected, or whose evidence is still awaiting a decision, still produced the work the row records.
Keying the refusal on a review decision would make the authority to review a task depend on the
outcome of the review being requested.

**Evidence recorded by the operator SHALL NOT refuse any agent.** A person recording what
demonstrates the work is not an agent claiming authorship of it, so a task whose evidence came only
from the operator remains reviewable by any agent.

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

#### Scenario: The agent that recorded the evidence is refused on operator-completed work

- **WHEN** the operator recorded a task's move to `completed`, and an agent that recorded evidence
  for that task requests `approved`
- **THEN** the request is refused with a typed error naming the evidence as the reason
- **AND** the refusal does not state that any agent completed the task
- **AND** the task remains in its pre-request status
- **AND** no transition is recorded

#### Scenario: The reviewer the flow staffed is not refused

- **WHEN** a flow staffs a reviewer for an operator-completed task, assigning the task to that
  reviewer, and the reviewer requests `approved`
- **AND** that reviewer recorded no evidence for the task
- **THEN** the request succeeds

#### Scenario: Awaiting or rejected evidence refuses its author just the same

- **WHEN** an agent's evidence for an operator-completed task is still awaiting a decision, or was
  rejected, and that agent requests `approved`
- **THEN** the request is refused

#### Scenario: Evidence the operator recorded refuses nobody

- **WHEN** an operator-completed task's only evidence was recorded by the operator, and an agent
  that no other record associates with the task requests `approved`
- **THEN** the request succeeds

#### Scenario: The operator may approve any work

- **WHEN** the operator approves a task, including one they moved to `completed` themselves
- **THEN** the request succeeds
- **AND** the transition is recorded as an operator action

#### Scenario: Rejection and revision carry the same separation

- **WHEN** the agent that completed a task requests `rejected` or `revision_needed` on it
- **THEN** the request is refused on the same grounds as self-approval

#### Scenario: The evidence fallback covers rejection and revision too

- **WHEN** an agent that recorded evidence for an operator-completed task requests `rejected` or
  `revision_needed` on it
- **THEN** the request is refused on the same grounds as its refused approval

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

**A review SHALL be refused where the named reviewer is recorded as having produced evidence for
the named task and no agent is recorded as completing it.** Such a reviewer's verdict is refused by
the rule separating author from reviewer, so dispatching it pays for a turn whose conclusion has
nowhere to go — and leaves the task held by an agent that no transition on it names, which this
capability specifies SHALL be reported as a review genuinely in progress and SHALL NOT be restaffed.
The refusal SHALL name the evidence as its reason and SHALL NOT state that any agent completed the
task. This refusal SHALL be the same rule as the one that refuses the verdict, and SHALL NOT be a
second statement of it that can drift.

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

#### Scenario: A reviewer that recorded the task's evidence is refused before any turn begins

- **WHEN** the operator dispatches a review of a task the operator moved to `completed`, naming an
  agent that recorded evidence for that task
- **THEN** the request is refused, naming the evidence as the reason
- **AND** the refusal does not state that any agent completed the task
- **AND** the task's status and holder are unchanged
- **AND** no reviewing turn has been started and no checkout has been created

#### Scenario: A reviewer that recorded nothing for the task is still dispatched by hand

- **WHEN** the operator dispatches a review of a task the operator moved to `completed`, naming an
  agent that recorded no evidence for it
- **THEN** the task is held by that reviewer and is in review before the turn begins

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

### Requirement: A review a flow cannot staff is not reported as staffed

A flow SHALL NOT treat a task in `under_review` as held by a reviewer when that task's assignee is an agent that produced the work, and SHALL instead resolve a reviewer for it through the ordinary reviewer ladder and record the result as a staffing outcome.

Such a task is claimable by nobody and its assignee counts as holding active work, so left
unrecognised it is never reviewed and its assignee is unavailable to review anything else in the
project, with nothing reporting either fact. This rule is what lets a task recorded that way before
the refusal above existed recover, rather than remaining stuck behind a rule that arrived later.

**Who produced the work SHALL be read from the recorded completion where one names an agent, and from
the task's recorded transitions where it does not.** A completion the operator recorded names no
agent, and a rule keyed only on the completion therefore reports such a task as held by a reviewer —
which is the false statement this requirement exists to prevent, reached one case over. Measured
live: an operator who moved a stuck task to `under_review` by hand, following the only route the
lifecycle offers them, produced exactly that.

**This determination SHALL be drawn from the task's recorded transitions alone, and SHALL NOT
include the agent the task is assigned to or the agents whose runs were bound to it**, and that is
the one place it differs from the determination used to exclude an agent from reviewing. The
question here is whether the assignee is one of the agents that produced the work; an assignee
counted as a producer by definition answers yes for every task that has one, and every review
genuinely in progress would be reported as one nobody is doing. The bound runs answer yes very
nearly as often, since a staffed reviewer's own run is bound to the task it is inspecting. A
reviewer legitimately staffed onto a task is absent from its **transitions**, and that absence is
what carries the distinction — so the wider determination the exclusion uses cannot be reused here,
however tempting one determination for two questions looks.

Where nothing is recorded as completing the task at all **and its assignee is one of the agents its
transitions name**, the ladder SHALL surface it rather than staff it, naming the task. Recovery is
not possible for such a task — no agent can be ruled out as its author — and saying so is what this
requirement asks for in place of reporting a reviewer that is not there. Where instead its assignee
appears on none of its transitions, the task SHALL still be reported as held: an agent may be
dispatched as reviewer by hand for a task no agent is recorded as completing, and that review is
genuinely in progress.

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

#### Scenario: An operator-completed task held by its worker is recognised

- **WHEN** a task the operator moved to `completed` is in `under_review` with an agent recorded on
  its earlier transitions as its assignee
- **THEN** it is not reported as held by a reviewer
- **AND** a reviewer is resolved for it through the ordinary ladder

#### Scenario: A review genuinely in progress is still reported as held

- **WHEN** a task the operator moved to `completed` is in `under_review` and is assigned to a
  reviewer that no transition on that task names
- **THEN** it is reported as held by that reviewer
- **AND** no reviewer is resolved for it

#### Scenario: A task with no recorded completion held by an agent that moved it is surfaced, not restaffed

- **WHEN** a task in `under_review` has no recorded completion at all and its assignee is recorded
  on one of its transitions
- **THEN** it is not reported as held by a reviewer
- **AND** the operator is notified, naming the task

#### Scenario: A review dispatched by hand on a task with no recorded completion is still held

- **WHEN** a task in `under_review` has no recorded completion at all and its assignee is an agent
  that no transition on it names
- **THEN** it is reported as held by that assignee

The route is supported and produces a review that is genuinely in progress: on a task with no
recorded completion, dispatching a review by hand refuses only an agent the record names as the
work's author — the agent recorded as completing it, or the agent recorded as having produced its
evidence — so an agent named by neither may be dispatched, and dispatching staffs the task. Treating
every such task as unstaffable would report a real reviewer's work as nobody's — which is the same
false statement this requirement exists to prevent, made in the opposite direction.
