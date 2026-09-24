## MODIFIED Requirements

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

Where text the firing did not compose is delivered after the briefing in the same turn, a review
briefing SHALL identify it as the loop's standing message, delivered on every firing and not written
for this turn in particular. It SHALL NOT instruct the agent to disregard that text: a loop's message
may itself be written to address a review, and a briefing that told the agent to ignore it would be
wrong in exactly the cases where its author had thought hardest. The message's words SHALL NOT be
rewritten either, because it is the durable record of what its author said. The one change its
delivery makes is the one `agent-run-sandboxing` requires of every firing's text (*Text the operator
did not write reaches a run without a file mention its harness would expand*): each at-sign in it is
neutralised so that it attaches no file. The stored message keeps the text as its author wrote it.

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

#### Scenario: The loop's standing message is not mistaken for this turn's instruction

- **WHEN** an agent is briefed for a review turn and the loop's own message follows the briefing
- **THEN** the briefing identifies the text following it as the loop's standing message
- **AND** does not instruct the agent to disregard it
- **AND** the loop's message itself is delivered with its words unchanged, its at-signs neutralised as
  every firing's text is

#### Scenario: An implementation firing is unaffected

- **WHEN** a firing is not staffed as a review
- **THEN** the briefing instructs the agent to do the task's work
- **AND** names the transition that finishes it

#### Scenario: A loop's message that mentions a file is delivered without attaching it

- **WHEN** a review firing delivers a loop message that mentions a file in the harness's mention syntax
- **THEN** the message reaches the run with that mention neutralised and no file is attached for it
- **AND** the stored message keeps the mention as its author wrote it
