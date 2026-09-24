## MODIFIED Requirements

### Requirement: An agent can read a specification document

The system SHALL provide an agent with a way to read a specification document, and that capability
SHALL be described in the surface the agent is told it has.

Documents are written into the project's own directory, while a working agent's checkout is an
isolated one branched before the document existed. An agent is therefore told which document governs
its work and, without this, has no way to open it — leaving it to implement from another agent's
paraphrase, with no way to detect divergence from what was approved.

The document SHALL be returned as structured content rather than as its rendered form. The rendering
exists for a person; returning it spends an agent's context on markup and leaves it to re-derive
what the structure already states.

Each requirement returned SHALL carry the identifier the system minted for it, so that an agent
quotes the same identifier that tasks, evidence and gates use.

Acceptance criteria SHALL be returned grouped under the requirement they demonstrate, rather than as
a separate list to be joined by the reader. An outline, which an agent asks for in order to see
every requirement cheaply, carries each requirement's identifier, key, modal, statement and state
and no acceptance criteria; that is what makes it an outline, not an omission.

Each read SHALL either return every requirement asked for or name, as remaining, those it did not
return. A read too large for one tool call is bounded (*An agent can read a specification document in
results that fit one tool call*), and a requirement it does not return is named so that the agent
can ask for it; nothing is dropped silently.

A document SHALL be readable by its id as well as by its path, since the id is what tasks carry.

A read that names requirements, which is how the rest of a bounded read is fetched, SHALL return
those requirements without the document's summary, problem, scope or open questions.

Reading SHALL be permitted in every phase. Reading is not authoring, and every gate in this area
governs writing or approving. A capability that is refused depending on state is one an agent
concludes it does not have.

The document's phase SHALL be returned, so that how settled it is can be judged rather than assumed.

Content that cannot be matched to a minted identifier SHALL still be returned, accompanied by a
statement of the problem. A document carrying no structured content SHALL be reported as such rather
than as a document with no requirements.

#### Scenario: An agent reads the document it is implementing

- **WHEN** an agent reads a specification document by path or by id
- **THEN** it receives the requirements with their identifiers, statements and obligations, each
  one either returned or named as remaining
- **AND** each requirement returned carries its own acceptance criteria
- **AND** the document's phase is stated

#### Scenario: An outline carries no acceptance criteria

- **WHEN** an agent asks for a document's outline
- **THEN** every requirement is returned with its identifier, key, modal, statement and state
- **AND** no acceptance criteria are returned

#### Scenario: A continuation carries no preamble

- **WHEN** an agent reads a document naming the requirements a previous read listed as remaining
- **THEN** it receives those requirements
- **AND** the document's summary, problem, scope and open questions are not returned again

#### Scenario: Reading is allowed before approval

- **WHEN** an agent reads a document that has not been approved
- **THEN** the document is returned
- **AND** its phase says it is not approved

#### Scenario: A document with no structured content is reported honestly

- **WHEN** an agent reads a document carrying no structured content
- **THEN** the response states that, rather than reporting an empty set of requirements

#### Scenario: The capability appears in the described surface

- **WHEN** an agent is told what it can do
- **THEN** reading a specification document is among the capabilities described
