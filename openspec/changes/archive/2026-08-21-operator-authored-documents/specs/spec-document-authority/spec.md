## ADDED Requirements

### Requirement: The operator can write a document's content

The Hub SHALL offer the operator a way to write a document's content directly, without an agent and
without a merge. The payload contract MUST be the same one an agent submits, and the same
validation MUST apply.

This closes a gap rather than granting a new power: "A capability document's content SHALL be
written only by the operator" is already required, and its scenario already states that a
submission from the operator succeeds. The service enforces exactly that. What has never existed is
a route, so the only way to exercise the operator's own authority has been to call the service
in-process.

#### Scenario: The operator writes a capability document

- **GIVEN** a capability document with no content
- **WHEN** the operator submits a valid payload for it
- **THEN** the content is written
- **AND** the document remains in the `current` phase

#### Scenario: The operator writes a document an agent could also have written

- **GIVEN** a change document being explored
- **WHEN** the operator submits a valid payload for it
- **THEN** the content is written

#### Scenario: An agent still cannot write a capability document

- **WHEN** an agent submits content against a capability document
- **THEN** it is refused
- **AND** the document's content is unchanged

#### Scenario: The same validation applies to the operator

- **WHEN** the operator submits a payload that omits a required field or violates a constraint
- **THEN** it is refused with an error identifying the field
- **AND** the document on disk is unchanged

#### Scenario: The operator cannot reclassify a document

- **WHEN** the operator submits a payload whose kind differs from the document's recorded kind
- **THEN** it is refused
- **AND** the document's recorded kind is unchanged

#### Scenario: The operator does not bypass their own approval

- **GIVEN** an approved document
- **WHEN** the operator submits content for it without reopening it
- **THEN** it is refused
- **AND** the approved content is unchanged

#### Scenario: Rigor applies to the operator's writes

- **GIVEN** a document at a rigor that gates edits behind an accepted proposal
- **WHEN** the operator submits content for it
- **THEN** a pending proposal is recorded rather than the document being written

### Requirement: Authorship is attributed to whoever performed it

Every content write SHALL record who performed it and in what capacity, and the Hub MUST establish
that from the caller's credential rather than from anything the caller states about itself.

An operator's write MUST be distinguishable from an agent's in the document's recorded history, so
that a corpus imported by hand is never mistaken for one an agent authored.

#### Scenario: An operator's write is recorded as the operator's

- **WHEN** the operator writes a document's content
- **THEN** the recorded event names the operator as the actor
- **AND** it is not attributed to any agent or run

#### Scenario: An agent's write is recorded as that run's

- **WHEN** an agent writes a document's content
- **THEN** the recorded event names the agent and the run it acted under

#### Scenario: A caller cannot assert an identity it does not hold

- **WHEN** a request carries an actor or run named in its body
- **THEN** the recorded actor is the one established from the credential
- **AND** the body's claim is disregarded
