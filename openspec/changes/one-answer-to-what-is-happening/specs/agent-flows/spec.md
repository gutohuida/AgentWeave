## ADDED Requirements

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
