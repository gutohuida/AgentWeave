## ADDED Requirements

### Requirement: A flow treats an agent whose queue is held as unable to take a turn

A flow SHALL treat an agent whose queue is held by a refusal of the provider's usage allowance as unable to take a turn, wherever a firing asks whether an agent can take one.

The hold is the one `agent-conversation-workspace` defines. The scheduler starts no turn for a held
agent's autonomous input, so a briefing queued for it is as stale by the time it is read as one
queued during a running turn. A flow that asked the question about running agents alone would
re-brief a held agent's assigned task on every firing, and the agent would find a stack of
identical briefings when its hold ended.

A task assigned to a held agent SHALL be reported as in flight while input naming that task is
queued for that agent, and SHALL NOT be briefed again. Input naming the task that is queued for a
different agent does not count. Where no input naming it is queued for the held agent, the firing
SHALL brief it once, as it resumes any assigned task, and the task is in flight from then on. A held agent is
working nothing, so its assignment alone is not the in-flight condition: that condition is the one
`agent-loops` *A task reported as in flight is one an agent is actually working* already states.

A held agent SHALL NOT be chosen as a firing's default agent, and SHALL NOT be recruited for new
work. A reviewer the task declares is unaffected: the declaration names who reviews, and the review
waits for the hold. A reviewer chosen by availability follows *A flow resolves a reviewer by
declaration, then by availability*.

Where a review cannot be staffed and an agent was passed over because its queue is held, the reason
surfaced SHALL name the hold among the grounds, and SHALL NOT state that every agent is running a
turn, holding work or excluded.

This concerns only whether an agent can take a turn now. Which tasks an agent holds, and which of
them make it unavailable, is unchanged.

#### Scenario: A held assignee whose briefing is queued is not re-briefed

- **WHEN** an agent's queue is held, it is assigned a task, input naming that task is queued for it, and another agent in the project is free
- **AND** the flow fires three times
- **THEN** no further input is queued for the held agent
- **AND** its task is reported in flight

#### Scenario: A held assignee with nothing queued is briefed once

- **WHEN** an agent's queue is held, it is assigned a task, and no input naming that task is queued
- **AND** the flow fires three times
- **THEN** exactly one input naming that task is queued for the agent

#### Scenario: A held job agent is passed over

- **WHEN** a flow's job agent is held and another agent is free
- **AND** an unassigned task is startable
- **THEN** the firing staffs the free agent, not the held one

#### Scenario: A held agent is not free

- **WHEN** an agent is held, running no turn and holding no task
- **THEN** it is not counted among the agents free for new work or for review

#### Scenario: An unstaffed review names the hold

- **WHEN** no reviewer is declared, and the only agent that could review a task is held, running no turn and holding no task
- **THEN** the flow surfaces that it could not staff the review
- **AND** the surfaced reason names the provider's usage limit among the grounds

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
and that holds no task in an active status.

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
- **THEN** an agent that is not running, is not held, and holds no active task is fired for the
  review

#### Scenario: A busy agent is not selected

- **WHEN** an otherwise eligible agent is running a turn, is held by a refusal of the provider's
  usage allowance, or holds a task in an active status
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
