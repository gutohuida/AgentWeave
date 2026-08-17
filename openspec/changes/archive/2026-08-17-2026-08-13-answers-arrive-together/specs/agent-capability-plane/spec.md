# agent-capability-plane

## MODIFIED Requirements

### Requirement: An agent can ask several questions in one turn

The question tool SHALL accept a list of questions and hold the turn until every one has been
answered or the wait expires.

An agent needing several decisions before it can start would otherwise block its turn once per
question and interrupt the operator once per question, or decide some of them itself. Asking together
is one interruption and one wait.

Where the asking run is no longer waiting — it expired, ended, or the question was not blocking —
the answers SHALL reach the agent as **one** delivery for the batch rather than one per answer, and
that delivery SHALL happen only once every question in the batch has been answered or declined. An
answer delivered on its own has the agent act on part of a decision while the operator is still
making the rest, which is the interruption asking together exists to prevent.

The delivery SHALL carry every question in the batch, in the order they were asked, each with its
answer or with the fact that the operator declined it. It SHALL include an answer that was recorded
while the asking run was still waiting but which that run never received. Where the batch produced no
answers at all, nothing SHALL be delivered.

Recording an answer SHALL NOT wait for the batch. Each answer SHALL be persisted, reported, and
SHALL release any task it had parked when the operator gives it.

#### Scenario: A batch is asked and answered

- **WHEN** an agent asks several questions in one call
- **AND** the operator answers all of them
- **THEN** the tool returns every answer, each identified with the question it answers

#### Scenario: The wait expires with a batch partly answered

- **WHEN** the wait expires before every question in a batch is answered
- **THEN** the tool returns without an answer for the unanswered ones and states plainly that they
  went unanswered

#### Scenario: A single question is still a single question

- **WHEN** an agent asks one question
- **THEN** it behaves exactly as an unbatched question does, with no extra step for the operator

#### Scenario: Each question keeps its required structure

- **WHEN** any question in a batch is submitted without its header, its options, or its
  multi-select flag
- **THEN** the call is rejected rather than partially accepted

#### Scenario: Answers to a batch whose asker has gone arrive together

- **WHEN** the asking run is no longer waiting and the operator answers the first question of a
  batch
- **THEN** nothing is delivered to the agent
- **WHEN** the operator resolves the remaining questions
- **THEN** exactly one delivery reaches the agent, carrying every question and its answer in the
  order asked

#### Scenario: A decline completes a batch and is delivered as a decline

- **WHEN** the operator answers some questions of a batch and declines the rest
- **THEN** the batch is delivered
- **AND** the declined questions are named as declined rather than omitted

#### Scenario: An answer the asking run never received is still delivered

- **WHEN** the operator answers a question while its asking run is waiting
- **AND** that run ends before the batch completes
- **AND** the operator then resolves the remaining questions
- **THEN** the delivery carries the earlier answer as well as the later ones

#### Scenario: A batch resolved entirely by declines delivers nothing

- **WHEN** every question in a batch is declined and none is answered
- **THEN** no delivery is made to the agent

#### Scenario: An answer is recorded before its batch completes

- **WHEN** the operator answers one question of a batch and the batch is not yet complete
- **THEN** that answer is recorded and any task it had parked is released
- **AND** it survives a reload of the operator's view

#### Scenario: A waiting asker is not sent the batch twice

- **WHEN** the asking run is still waiting and the operator answers every question in the batch
- **THEN** the tool call returns the answers
- **AND** no delivery is queued to the agent

### Requirement: The operator answers a batch one question at a time

The operator SHALL be shown one question of a batch at a time, told which step they are on and how
many there are, and advanced to the next once the current one is answered.

Showing a batch at once turns a conversation into a form, and a count of outstanding questions
displayed where a step count belongs misrepresents how much is left.

Where a batch's answers are held until it completes, the operator SHALL be told that the answers go
to the agent together. Without it, a part-answered batch is indistinguishable from answers that were
discarded: the operator answers, sees nothing happen, and has no way to tell that the agent is
waiting on the rest. This statement is about what has been sent and is distinct from the step
counter, which is about position.

#### Scenario: The step counter reflects position within the batch

- **WHEN** the operator is answering a batch
- **THEN** the displayed count is their position within that batch and its total, not the number of
  questions outstanding across the project

#### Scenario: Answering advances to the next question

- **WHEN** the operator answers the question on screen and others in its batch remain
- **THEN** the next unanswered question in that batch is shown

#### Scenario: The answer is recorded against the question that was displayed

- **WHEN** the operator answers
- **THEN** the answer is recorded against the question they were shown

#### Scenario: An answer survives an interruption

- **WHEN** the operator answers part of a batch and their view is reloaded
- **THEN** the answers already given are still recorded, and the batch resumes at the first
  unanswered question

#### Scenario: A held batch says that its answers travel together

- **WHEN** the operator has answered part of a batch whose asker is no longer waiting
- **THEN** the panel states that the answers reach the agent together once the batch is finished
