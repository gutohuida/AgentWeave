## MODIFIED Requirements

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
