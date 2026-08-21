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

#### Scenario: Two documents cannot claim the same position

- **WHEN** two entries in the index record the same order
- **THEN** the index is reported as invalid
- **AND** the diagnostic names both documents

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
- **AND** no index is written

### Requirement: The operator can name the home the Hub refuses to guess

Rebuilding SHALL accept a home named by the operator, and that answer MUST take precedence over any
home already recorded. A named home that does not identify a document in the corpus SHALL be
refused rather than substituted.

This exists because the Hub's refusal to guess, on its own, leaves a corpus of more than one
document permanently unindexable: a home is required, nothing may invent one, and so nothing could
ever be written. The refusal is right; what was missing was a way to answer.

#### Scenario: A named home is recorded and the index is written

- **GIVEN** a project with several documents and no recorded home
- **WHEN** the operator rebuilds the index naming one of them as home
- **THEN** that document is recorded as home
- **AND** every discovered document is reported as filed

#### Scenario: A named home overrides a recorded one

- **GIVEN** a valid index already recording a home
- **WHEN** the operator rebuilds the index naming a different document as home
- **THEN** the newly named document is home

#### Scenario: A named home that identifies no document is refused

- **WHEN** the operator rebuilds the index naming a home that is not in the corpus
- **THEN** no index is written
- **AND** no other document is substituted as home

### Requirement: A failure to write the index does not abandon the requirement index

When the document index cannot be written, the requirement index SHALL still be rebuilt, and the
reason the file was not written SHALL be reported.

Rebuilding covers two indexes — the requirement index held as records, and the document index held
as a file — and only the file can be blocked on a decision that is the operator's to make.

#### Scenario: A corpus with no home still rebuilds its requirements

- **GIVEN** a project with several documents and no home
- **WHEN** the operator rebuilds
- **THEN** the requirement index is rebuilt
- **AND** the response reports that no document index was written
- **AND** the response states why

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
