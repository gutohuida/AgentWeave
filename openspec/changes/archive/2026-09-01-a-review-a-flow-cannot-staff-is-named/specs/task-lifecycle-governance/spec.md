## MODIFIED Requirements

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

The route is supported and produces a review that is genuinely in progress: dispatching a review by
hand refuses only an agent *recorded* as completing the task, so on a task with no recorded
completion any agent may be dispatched, and dispatching staffs the task. Treating every such task as
unstaffable would report a real reviewer's work as nobody's — which is the same false statement this
requirement exists to prevent, made in the opposite direction.
