## ADDED Requirements

### Requirement: An agent can read a specification document in results that fit one tool call
The Hub SHALL bound every result of an agent's read of a specification document to a fixed size, and SHALL tell the agent exactly what was left out and how to read it.

The read is the one route the product names for learning what was approved. A result larger than
the agent's harness accepts is spilled to a file outside the workspace, which the workspace guard
then refuses. So an unbounded result is not a larger answer. It is no answer at all, and the agent
falls back to a paraphrase, which is the failure the read exists to prevent.

The bound SHALL be enforced by the Hub, not chosen by the agent. Where the requested content does not
fit, the Hub SHALL return the requirements in identifier order up to the bound and SHALL list the
identifiers of those it did not return, naming a requirement the index has not given an identifier
by its key, so that every requirement can be asked for again. It SHALL name the sections it did not return, and say in the
result how to read the rest. Every section it names as not returned SHALL be readable on its own,
including the summary, problem, scope and open questions. The first requirement or requested
section SHALL always be returned, cut if it alone exceeds the bound, so that every read makes
progress.

An agent SHALL be able to read only named requirements, and SHALL be able to read an outline of
every requirement without its rationale or acceptance criteria. An identifier it names that the
document does not declare SHALL be reported as unknown, and SHALL NOT fail the read.

A read that names requirements SHALL return those requirements and the document's identifying
fields only, without the summary, problem, scope or open questions. It continues a read that
already offered them, and re-sending them on every continuation would spend the bound on what the
agent already has, so that a document with a long preamble could take many more reads than its
size requires.

#### Scenario: A document larger than the bound
- **WHEN** an agent reads a document whose requirements and criteria serialise to more than the bound
- **THEN** the result SHALL be within the bound
- **AND** it SHALL carry the leading requirements in identifier order, mark itself truncated, and list the identifiers it did not return

#### Scenario: Reading the rest
- **WHEN** an agent reads the same document again naming the identifiers the first result listed as remaining
- **THEN** the result SHALL carry those requirements, within the bound
- **AND** it SHALL NOT carry the document's summary, problem, scope or open questions

#### Scenario: An omitted preamble field is read on its own
- **WHEN** a read names the document's problem statement as not returned because it did not fit
- **AND** the agent asks for that field alone
- **THEN** the result SHALL carry it, cut to the bound and marked as cut if it alone exceeds it

#### Scenario: A document that fits
- **WHEN** an agent reads a document whose requested content is within the bound
- **THEN** the result SHALL carry all of it and SHALL NOT be marked truncated

#### Scenario: An outline
- **WHEN** an agent asks for the outline of a document
- **THEN** each requirement SHALL be returned with its identifier, key, modal, statement and state, and without its rationale or acceptance criteria
- **AND** a requirement the index has not given an identifier SHALL still carry its key

#### Scenario: An identifier the document does not declare
- **WHEN** an agent names `FR-99` among the identifiers to read and the document has no `FR-99`
- **THEN** the other named requirements SHALL be returned
- **AND** `FR-99` SHALL be reported as unknown

#### Scenario: A full read whose sections do not fit
- **WHEN** an agent asks for the full document and its design section does not fit within the bound
- **THEN** the design section SHALL be named as omitted
- **AND** reading that section alone SHALL return it

### Requirement: A specification document is readable by the id tasks carry
The Hub SHALL accept a specification document's id wherever an agent's read of a document accepts its path, resolving it only within the agent's own project.

Tasks carry the id of the document they implement, so an agent holding a task reaches for the id.
Refusing it with a message about path syntax tells the agent the document cannot be read, when the
Hub knows exactly which document was meant.

#### Scenario: Reading by id
- **WHEN** an agent reads a document by the `spdoc-` id its task carries
- **THEN** the result SHALL be the same as reading it by its path
- **AND** SHALL carry both the id and the path

#### Scenario: An id from another project
- **WHEN** an agent reads by an id that belongs to a document in a different project
- **THEN** the read SHALL be refused as no such document, with the same answer as an id that does not exist
