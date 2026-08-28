## ADDED Requirements

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

#### Scenario: A refused review leaves no checkout behind

- **WHEN** a review is requested and refused for any reason
- **THEN** no checkout has been created for the reviewer or the named task
- **AND** the task's status and holder are as they were before the request

#### Scenario: A request that is never delivered leaves the task untouched

- **WHEN** a review is requested and the turn is never dispatched
- **THEN** the task's status and holder are unchanged
