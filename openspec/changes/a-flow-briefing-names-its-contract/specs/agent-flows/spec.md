## ADDED Requirements

### Requirement: A firing's briefing names how its claimed task is finished

A firing's briefing SHALL name the call that moves the claimed task to the status that means the work is finished, SHALL name that status, and SHALL state what a turn that ends without it costs.

The briefing SHALL state the status the task is in at the moment the agent receives it, so that a
transition needing more than one step is visible as more than one step rather than implied as one.

This SHALL be stated for every firing that claims a task, whether or not the loop declares a
specification document. A task's lifecycle is the same in both, and a queue drains on the same band
in both; a document-less loop whose task never leaves an active status re-claims that task on every
subsequent firing for exactly the reason a flow's does.

What completing **causes** SHALL be stated only where it is true of that firing. A flow SHALL state
that finished work is offered for review by another agent; a loop that declares no document SHALL
NOT state that anything routes its work onward.

Where the claimed task serves requirements of record, the briefing SHALL name those requirements by
their identifiers and SHALL name how evidence is recorded against them. Where the task serves none,
the briefing SHALL say nothing about evidence — an instruction to record evidence against a
requirement that does not exist is refused when followed, which is worse than silence.

The turn context's inventory of callable tools SHALL NOT be read as satisfying this. An inventory
states that a capability exists; this states that using it is how the firing's work is concluded.
Measured on 2026-08-30, two agents in a flow each called the tool the briefing named and neither
called the tool named only in the inventory, and the flow re-briefed both for finished work on every
subsequent firing.

#### Scenario: The briefing names the transition that finishes the work

- **WHEN** a firing claims a task and briefs an agent for it
- **THEN** the briefing names the call that moves that task
- **AND** names the status that means the work is finished
- **AND** names the status the task is in now

#### Scenario: A flow says what completing causes and a loop does not

- **WHEN** a flow fires an agent for a task
- **THEN** the briefing states that finished work is offered for review by another agent
- **WHEN** a loop that declares no document fires an agent for a task
- **THEN** the briefing still names how the task is finished
- **AND** does not state that anything routes its work onward

#### Scenario: A turn that ends without moving the task is named as a cost

- **WHEN** a firing claims a task and briefs an agent for it
- **THEN** the briefing states what happens if the turn ends with the task unmoved

#### Scenario: Evidence is named only where there is a requirement to name

- **WHEN** a firing claims a task that serves requirements of record
- **THEN** the briefing names those requirements by identifier
- **AND** names how evidence is recorded against them
- **WHEN** a firing claims a task that serves no requirement of record
- **THEN** the briefing says nothing about recording evidence

#### Scenario: A firing that claims no task states no completion contract

- **WHEN** a firing proceeds with no task claimed
- **THEN** the briefing names no task, no transition and no requirement


### Requirement: A review firing's briefing is a review briefing

Where a firing is staffed as a review, its briefing SHALL state that the turn is a review, SHALL NOT instruct the agent to carry out the task's work, and SHALL name both verdicts available to the reviewer.

The task's own description and acceptance criteria SHALL be presented as the standard the finished
work is checked against, under a heading that says so. They SHALL NOT be presented under an
instruction to complete them.

The verdicts named SHALL be legal from the status the task is in when the reviewer receives it, and
SHALL agree with what the turn context states. Naming them on both channels is required rather than
merely permitted: a reviewer that is told how to end only on the channel the briefing contradicts is
the condition under which no flow-dispatched review had ever recorded a verdict.

A review briefing SHALL still state the tier the agent is working inside, and SHALL still state that
the turn ends rather than continuing into other work.

#### Scenario: A reviewer is not told to build what it is reviewing

- **WHEN** a flow staffs an agent to review a completed task
- **THEN** the briefing states that the turn is a review
- **AND** does not instruct the agent to finish or complete the task
- **AND** presents the task's description as what the work is checked against

#### Scenario: Both verdicts are named in the briefing

- **WHEN** an agent is briefed for a review turn
- **THEN** the briefing names how to record that the work is correct
- **AND** names how to record that it needs revision
- **AND** both are transitions the task can make from the status it is in

#### Scenario: The two channels agree

- **WHEN** an agent is briefed for a review turn
- **THEN** the briefing and the turn context do not give contradictory instructions about whether
  the agent is doing the work or checking it

#### Scenario: An implementation firing is unaffected

- **WHEN** a firing is not staffed as a review
- **THEN** the briefing instructs the agent to do the task's work
- **AND** names the transition that finishes it
