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

#### Scenario: A turn that was given no deliverable
- **WHEN** a run was given no document and no task
- **THEN** no such outcome SHALL be recorded, whatever the run produced
- **AND** an ordinary conversational reply SHALL therefore never be recorded as a non-outcome

#### Scenario: A turn given a task rather than a document
- **WHEN** a run bound to a task ends without moving it
- **THEN** the existing run-divergence behaviour SHALL apply unchanged
- **AND** the two mechanisms SHALL NOT both record the same run

#### Scenario: Prose is never the evidence
- **WHEN** a run's final message reads like a question but no question was recorded and the deliverable advanced
- **THEN** no such outcome SHALL be recorded

#### Scenario: The expectation is stated in advance
- **WHEN** canonical context is assembled for a turn whose deliverable is an unwritten document
- **THEN** the context SHALL state that ending without either submitting it or asking is not a valid outcome

#### Scenario: A document that exists but has never been written into has not advanced
- **WHEN** a run is given a document that the Hub created and scaffolded but into which nothing has since been written
- **THEN** that deliverable SHALL be treated as not advanced
- **AND** the determination SHALL NOT rest on any field the Hub populates at creation time

The last clause is what the first implementation got wrong, and it is stated as a requirement
because the mistake is not visible from the rest of this document. That implementation asked
whether the document had a recorded content digest, on the reasoning that its absence means
"nothing has ever been written here". No creation path leaves it absent: both the operator route
and the agent's own document-creation tool write a scaffold payload the instant the row exists, so
the digest is populated from the document's first microsecond. Measured on the live database, 50
documents, 0 without one — so the check never fired, while six tests passed against a fixture that
built a document in a state the product does not produce.

The document this requirement was written for proves it. The one the author was given and never
wrote records its creation and its scaffold write at the same microsecond. The check written to
catch that turn would have returned "advanced" on that turn.
