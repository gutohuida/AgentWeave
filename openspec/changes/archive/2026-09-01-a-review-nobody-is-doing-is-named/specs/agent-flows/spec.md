## ADDED Requirements

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
