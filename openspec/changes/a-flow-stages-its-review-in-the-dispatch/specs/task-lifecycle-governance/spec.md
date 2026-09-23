## MODIFIED Requirements

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

Two holders are not a different reviewer in that sense, and a dispatch SHALL replace them. One is an
agent recorded as having produced the work, by the record that would refuse its verdict: it cannot
be reviewing the task, and a task entering review may not name it as holder in the first place. The
other is a reviewer whose review ended without a verdict and whom the resolution of that failed review
replaced by the reviewer being dispatched: the record of that failed review names the previous holder
and the replacement, so the task's history explains the handover. In both cases no path records the
new holder before the dispatch, so a refused dispatch leaves the previous holder in place.

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

#### Scenario: A failed review's replacement is staffed at its dispatch

- **WHEN** a review ends without a verdict, the resolution replaces its reviewer, and the replacement's review turn is dispatched
- **THEN** the replacement becomes the task's holder when the turn is dispatched, not before
- **AND** no transition is recorded for the task by the dispatch
- **AND** if that dispatch is refused, the reviewer that gave no verdict is still the holder

#### Scenario: An author left as holder is replaced by the dispatched reviewer

- **WHEN** a task is under review and its holder is the agent recorded as having produced the work
- **AND** a review naming a different agent is dispatched
- **THEN** the dispatched reviewer becomes the holder
- **AND** the request is not refused on the ground that the task is already under review

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

### Requirement: A refused review dispatch leaves the task as it was before the dispatch

A review dispatch that is refused SHALL leave the task's status and holder exactly as they were before the dispatch and SHALL leave no transition recorded for it, whichever refusal it was, whether the refusal was raised while the staffing was being judged or after it, and whether it was raised when a request was answered or when queued input was delivered.

Staffing a review records the reviewer as the task's holder before the move into review is judged,
because the rule that a task entering review may not name its author has to judge the reviewer
being entered. That record exists only so that the move can be judged. Where the dispatch is then
refused, the record describes a review that never started. Kept, it tells the operator that a review
is in progress on a board that shows nothing wrong, and it refuses every other reviewer the operator
sends, because the task already names one.

This SHALL hold for a refusal that becomes knowable only when queued input is delivered. That
includes a condition that arose after the request was accepted, such as the named reviewer
recording evidence for the task while the request waited behind that reviewer's own running turn.
It includes a condition that the repository holds rather than the system's records: the commit
under review no longer present, the project not a repository, and the reviewer's checkout location
obstructed. It also includes a deferral that is expected to clear on its own. A deferred dispatch
has not started a review either.

The refusal's own sentence SHALL still be recorded where the operator reads why queued input is
waiting, and SHALL still count toward giving up on that input where the refusal is one that counts.
Discarding the staffing SHALL NOT discard the explanation of why it was discarded.

Each further attempt to deliver the same refused request SHALL leave the task as it was. A refusal
repeated on every attempt SHALL NOT accumulate a record of the task entering review.

No path records the reviewer before the dispatch. A flow's firing and a failed review's
restaffing queue the review turn and leave the task's status and holder to its dispatch, so a
refused dispatch leaves the task exactly as it was before the path that queued it, as well as before
the dispatch.

#### Scenario: A review whose commit is gone from the repository is refused and changes nothing

- **WHEN** the operator dispatches a review of a completed task whose evidence names a commit the
  repository no longer contains
- **THEN** the request is refused, naming the commit
- **AND** the task's status and holder are what they were before the request
- **AND** no transition is recorded for the task
- **AND** no reviewing turn has been started

#### Scenario: A review whose checkout cannot be prepared is refused and changes nothing

- **WHEN** the operator dispatches a review, and the location of the reviewer's review checkout is
  occupied by something that is not that checkout
- **THEN** the request is refused, naming the location
- **AND** the task's status and holder are what they were before the request
- **AND** no transition is recorded for the task

#### Scenario: A review of a project that is not a repository is refused and changes nothing

- **WHEN** a review is dispatched for a task whose project is not a git repository
- **THEN** the dispatch is refused
- **AND** the task's status and holder are what they were before the dispatch
- **AND** no transition is recorded for the task

#### Scenario: A review accepted while its reviewer was busy, and refused on delivery, changes nothing

- **WHEN** the operator requests a review naming an agent whose own turn is running, and the
  request is accepted as waiting
- **AND** during that turn the agent records evidence for the task, and no agent is recorded as
  completing it
- **THEN** when the waiting request is delivered, the dispatch is refused
- **AND** the task's status and holder are what they were before the dispatch
- **AND** the refusal's own sentence is recorded as what the waiting input is waiting for
- **AND** a delivery attempt is counted against that input

#### Scenario: Every attempt to deliver a refused review leaves the task as it was

- **WHEN** a review dispatch is refused on delivery and is attempted again until the system gives
  up on it
- **THEN** after every attempt the task's status and holder are what they were before the first
- **AND** no transition is recorded for the task by any of the attempts
- **AND** when the system gives up, the operator is told, with the refusal as the reason

#### Scenario: A deferred review dispatch leaves the task as it was

- **WHEN** a review dispatch is deferred for a reason that is expected to clear on its own
- **THEN** the task's status and holder are what they were before the dispatch
- **AND** the input remains queued, with no delivery attempt counted against it

#### Scenario: A refused review does not stop another reviewer being sent

- **WHEN** a review dispatch naming one reviewer has been refused
- **AND** that dispatch found the task awaiting review, held by no reviewer
- **AND** the operator then requests a review of the same task naming a different reviewer
- **THEN** that request is not refused on the ground that the task is already under review

#### Scenario: A review a flow staffed and whose dispatch is refused changes nothing

- **WHEN** a flow's firing staffs a review of a completed task, and the dispatch of that review turn is refused because the commit under review is not in the repository
- **THEN** the task is completed, with the holder it had before the firing
- **AND** no transition is recorded for the task by the firing or by the dispatch

#### Scenario: A review that starts is still staffed

- **WHEN** a review is dispatched and nothing refuses it
- **THEN** the task is held by the reviewer and is in review before the turn begins, exactly as
  *"Dispatching a review staffs the task, whichever path dispatched it"* requires
