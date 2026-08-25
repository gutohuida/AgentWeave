## ADDED Requirements

### Requirement: A turn that produced nothing and asked nothing is recorded as such

The Hub SHALL record, and surface to the operator, a run that reaches a terminal status having
neither advanced the deliverable it was given nor recorded a question.

The determination SHALL be made from structured state alone: that the run ended, that it wrote no
question, and that the deliverable did not advance. **The agent's prose SHALL NOT be inspected, and
no inference SHALL be drawn from how its final message reads.**

That constraint is the point of this requirement, not an aside. A backstop that guessed whether
trailing prose was a question previously existed and was retired deliberately, on the reasoning that
such a guess is a judgement the product should not make on the operator's behalf. That reasoning
stands. What this requirement adds needs no guess: every fact it uses is already recorded.

The measured cost of having nothing here: an agent read the code, diagnosed the bug correctly and
unprompted, asked four well-judged questions as chat text, and ended its turn. No question row, no
blocking, no parked task — the run was over and the specification was never written. The agent was
not underinstructed; its charter names the asking tool six times, and told plainly on the next turn
it used it immediately and well. The mechanism works; what was missing was anything making it the
path of least resistance at the moment the agent had a question.

#### Scenario: A turn ends without advancing or asking
- **WHEN** a run reaches a terminal status, wrote no question, and its deliverable did not advance
- **THEN** that outcome SHALL be recorded against the run
- **AND** SHALL be visible to the operator

#### Scenario: A turn that asked
- **WHEN** a run recorded a question
- **THEN** no such outcome SHALL be recorded, whether or not the deliverable advanced

#### Scenario: A turn that advanced its deliverable
- **WHEN** a run advanced the deliverable it was given
- **THEN** no such outcome SHALL be recorded

#### Scenario: Prose is never the evidence
- **WHEN** a run's final message reads like a question but no question was recorded and the deliverable advanced
- **THEN** no such outcome SHALL be recorded

#### Scenario: The expectation is stated in advance
- **WHEN** canonical context is assembled for a turn whose deliverable is an unwritten document
- **THEN** the context SHALL state that ending without either submitting it or asking is not a valid outcome
