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

**Where approval of the task is refused for a reason only the operator can remove, a review that gave no verdict SHALL NOT be answered by resolving a second reviewer**, whether the reviewer that failed was declared or selected by availability. The Hub SHALL surface the review instead, as *A review no reviewer can approve is handed to the operator* states. A reason only the operator can remove is one whose remedy is a decision on evidence, where the agent the resolution would select has not been granted that decision, or a requirement that cannot be satisfied as written. A second reviewer meets the identical refusal, so resolving one spends a review turn on a conclusion that has nowhere to go and tells the operator about staffing instead of about the decision waiting for them. Where the agent the resolution selects has been granted the decision on evidence, it can remove the reason itself, and the resolution SHALL proceed as above.

**The Hub SHALL NOT resolve, as a task's reviewer, an agent that could not record a verdict on it.**
An agent is barred from judging work it completed, so naming it would produce a review refused on
arrival; the resolution SHALL exclude it rather than discover the refusal afterwards.

#### Scenario: The author is not offered the work by the second resolution either

- **WHEN** a reviewer staffed for a task the operator moved to `completed` ends its turn without
  recording a verdict, and the Hub resolves a replacement
- **THEN** an agent that any record associates with that task is not selected
- **AND** the agent that gave no verdict is not selected

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

## ADDED Requirements

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

#### Scenario: A later firing names the same reason

- **WHEN** a flow fires while that task is still under review with the silent reviewer named, and approving it is still refused for the same reason
- **THEN** the sentence the flow records names that reason and the decision waiting for the operator
- **AND** it does not offer asking the same reviewer again

#### Scenario: A refusal the author can repair is answered as before

- **WHEN** a review selected on availability ends without a verdict, and approving the task is refused only because the work cannot be merged cleanly
- **THEN** the reviewer is resolved again as *A flow resolves a reviewer by declaration, then by availability* states
