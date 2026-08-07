## ADDED Requirements

### Requirement: An agent can ask several questions in one turn

The question tool SHALL accept a list of questions and hold the turn until every one has been
answered or the wait expires.

An agent needing several decisions before it can start would otherwise block its turn once per
question and interrupt the operator once per question, or decide some of them itself. Asking together
is one interruption and one wait.

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

### Requirement: The operator answers a batch one question at a time

The operator SHALL be shown one question of a batch at a time, told which step they are on and how
many there are, and advanced to the next once the current one is answered.

Showing a batch at once turns a conversation into a form, and a count of outstanding questions
displayed where a step count belongs misrepresents how much is left.

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
