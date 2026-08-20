## ADDED Requirements

### Requirement: The Hub can write the document index it reads

The Hub SHALL be able to produce `spec/index.json` for the documents a project holds. An index the
Hub writes MUST parse as valid when read back, so that a corpus carries its own home, titles,
hierarchy and ordering when the project directory moves.

Writing the index is the operator's action, not an agent's, because it decides how the corpus is
presented rather than what any document says.

#### Scenario: A written index reads back as valid

- **WHEN** the Hub writes the index for a project holding at least one document
- **THEN** reading that file yields a valid index
- **AND** its state is reported as valid rather than absent, unreadable or invalid

#### Scenario: Documents the Hub rendered become filed rather than unindexed

- **GIVEN** a project whose documents were rendered by the Hub and have no index
- **WHEN** the operator rebuilds the index
- **THEN** every discovered document is reported as filed
- **AND** none is reported as unindexed

#### Scenario: An agent cannot write the index

- **WHEN** an agent attempts to rebuild or write the document index
- **THEN** the attempt is refused
- **AND** the index on disk is unchanged

### Requirement: The index describes documents in the same vocabulary the Hub renders

A document's kind and phase SHALL mean the same thing in the index as in the document the Hub
rendered. Every kind an agent may submit MUST be expressible in the index, and a document's index
status MUST be its lifecycle phase — the value the Hub writes into the rendered document's own
metadata.

This exists because the two vocabularies were introduced at different times and diverged: a
document the Hub itself produced could not be described by an index the Hub itself validated, which
made a correct corpus indistinguishable from a corrupt one.

#### Scenario: A capability document can be indexed

- **WHEN** the index describes a document whose kind is `capability`
- **THEN** the index is valid
- **AND** the document is reported as filed

#### Scenario: A document's index status is its phase

- **GIVEN** a document at a given lifecycle phase
- **WHEN** the Hub writes the index
- **THEN** the entry's status is that phase
- **AND** comparing the entry against the rendered document reports no metadata conflict

#### Scenario: An archived change document can be indexed

- **WHEN** the index describes a change document that has been archived
- **THEN** the index is valid
- **AND** the document is reported as filed

#### Scenario: A phase that is not a phase is refused

- **WHEN** an index entry carries a status that is not a lifecycle phase
- **THEN** the index is reported as invalid
- **AND** the discovered documents are still listed

#### Scenario: A kind and phase that cannot occur together are refused

- **WHEN** an index entry pairs a kind with a phase that kind can never hold
- **THEN** the index is reported as invalid

### Requirement: Rebuilding the index preserves what the operator arranged

Rebuilding the index SHALL carry forward the presentation choices already recorded in a valid index
— which document is home, each document's parent, and its order. The Hub MUST NOT replace a
recorded arrangement with a derived one.

Where no arrangement is recorded, the Hub SHALL derive a stable order and leave parentage unset,
and MUST NOT invent a home it was never given.

#### Scenario: A recorded home survives a rebuild

- **GIVEN** a valid index recording a home document that still exists
- **WHEN** the operator rebuilds the index
- **THEN** the same document is still home

#### Scenario: Recorded parentage and order survive a rebuild

- **GIVEN** a valid index recording a parent and an order for a document
- **WHEN** the operator rebuilds the index
- **THEN** that document's parent and order are unchanged

#### Scenario: An unarranged corpus is ordered stably and left unparented

- **GIVEN** a project with several documents and no recorded arrangement
- **WHEN** the operator rebuilds the index twice with no document changing in between
- **THEN** both rebuilds produce the same order
- **AND** no document is given a parent

#### Scenario: An ambiguous home is still not guessed

- **GIVEN** a project with several documents and no recorded home
- **WHEN** the operator rebuilds the index
- **THEN** no document is recorded as home
- **AND** the operator is asked which is home

#### Scenario: A home naming a document that no longer exists is not silently replaced

- **GIVEN** a valid index whose home names a document that has since been removed
- **WHEN** the operator rebuilds the index
- **THEN** no other document is substituted as home
- **AND** the condition is reported

### Requirement: Both index implementations agree on the vocabulary

The Hub and the CLI validate the index independently and MUST accept exactly the same kinds and
phases. A value one accepts and the other rejects SHALL be treated as a defect in whichever is
behind.

This is asserted rather than documented because the two modules deliberately have no import
relationship, so nothing but a test can hold them together.

#### Scenario: The two implementations accept the same kinds

- **WHEN** the set of kinds each implementation accepts is compared
- **THEN** the two sets are identical

#### Scenario: The two implementations accept the same phases

- **WHEN** the set of phases each implementation accepts is compared
- **THEN** the two sets are identical
