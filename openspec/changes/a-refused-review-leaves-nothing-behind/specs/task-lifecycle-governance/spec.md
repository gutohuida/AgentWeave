## ADDED Requirements

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
- **AND** the operator then requests a review of the same task naming a different reviewer
- **THEN** that request is not refused on the ground that the task is already under review

#### Scenario: A review that starts is still staffed

- **WHEN** a review is dispatched and nothing refuses it
- **THEN** the task is held by the reviewer and is in review before the turn begins, exactly as
  *"Dispatching a review staffs the task, whichever path dispatched it"* requires
