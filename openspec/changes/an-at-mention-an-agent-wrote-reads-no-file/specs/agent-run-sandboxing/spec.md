## ADDED Requirements

### Requirement: Text the operator did not write reaches a run without a file mention its harness would expand

The system SHALL deliver text that the operator did not write to an agent's run in a form in which the run's harness attaches no file for it.

Some harnesses read a file named by a mention token in a turn's input, such as `@path`, before the
model runs and without a tool call. A read made that way is never put to any permission posture.
Text written by another agent, a scheduled job, a checkpoint or any other source that is not the
operator therefore reaches a run with every such mention neutralised. The text also carries a
statement, in words and with no mention of its own, of how it was changed.

Only the text handed to the runner SHALL be changed. What the system stores and shows the operator
keeps the text as it was written.

Text the operator wrote SHALL reach the run unchanged. The operator's own mentions are how they
attach workspace files to a turn.

A source added later SHALL be treated as not written by the operator until it is decided otherwise.

#### Scenario: A peer's mention of a file outside the workspace attaches nothing

- **WHEN** an agent sends another agent a message that mentions a file outside the recipient's workspace in the harness's mention syntax
- **THEN** the recipient's harness attaches no file for that mention
- **AND** the recipient's turn states that text not written by the operator was changed so it cannot attach files

#### Scenario: The operator's own mention still attaches

- **WHEN** the operator sends an agent a message that mentions a workspace file in the harness's mention syntax
- **THEN** the message reaches the run unchanged and the harness attaches the file

#### Scenario: One turn mixes the operator's text and a peer's

- **WHEN** a single turn delivers an operator message and a peer message, each containing a mention
- **THEN** only the peer message's mention is neutralised

#### Scenario: An agent's own question does not come back as a file read

- **WHEN** the operator answers a question whose text contains a mention
- **THEN** the question's text is neutralised in the delivered answer and the operator's answer is not

#### Scenario: The stored message keeps its original text

- **WHEN** a peer message containing a mention is neutralised for delivery
- **THEN** the stored message and the operator's view of it show the text as the peer wrote it
