# spec-document-authority

## ADDED Requirements

### Requirement: A finished change is archived by the operator

Where an approved document's work is done, the Hub SHALL let the operator move it to an `archived`
phase, and SHALL refuse that move from any other actor, enforced in the same function that already
refuses approval to anyone but the operator.

Archiving SHALL change only the document's phase. It SHALL NOT alter the document's requirements,
digests, recorded events, or any task the document previously declared.

The Hub SHALL refuse to archive a document that is not currently `approved`. Archiving SHALL NOT be
reachable from `exploring` or `proposed` — an unfinished document is abandoned or reopened through the
means that already exist for that, not archived.

An `archived` document SHALL have no further phase transition available to it.

#### Scenario: An approved document is archived by the operator

- **WHEN** the operator moves an approved document to `archived`
- **THEN** the document's phase becomes `archived`
- **AND** its requirements, digests, events and declared tasks are unchanged

#### Scenario: An agent cannot archive

- **WHEN** an agent attempts to move a document to `archived`
- **THEN** it is refused, and the refusal says archiving is the operator's

#### Scenario: An unfinished document cannot be archived

- **WHEN** archiving is attempted on a document that is `exploring` or `proposed`
- **THEN** it is refused as an illegal transition

#### Scenario: An archived document is a terminal state

- **WHEN** any phase transition is attempted on an archived document
- **THEN** it is refused

### Requirement: A capability document sits outside the phase machine

Where a document is created with `kind` `capability`, the Hub SHALL place it directly in a `current`
phase rather than `exploring`, and SHALL refuse every phase transition attempted against it, including
one naming `current` itself.

A capability document's content SHALL be written only by the operator. A submission from any other
actor SHALL be refused, regardless of the document's phase, because a capability document is never in
a phase a submission would otherwise be blocked by.

A document's `kind` SHALL be fixed at creation. A subsequent content submission whose `kind` disagrees
with the document's recorded `kind` SHALL be refused, and SHALL NOT change what the document is
classified as. This applies to every document, not only capability documents — the document a
submission targets is not the submission's to reclassify.

#### Scenario: A capability document starts and stays current

- **WHEN** a document is created with `kind` `capability`
- **THEN** its phase is `current`
- **AND** no phase transition, including one naming `current`, succeeds against it

#### Scenario: Only the operator writes a capability document

- **WHEN** an agent submits content against a capability document
- **THEN** it is refused
- **AND** the same submission from the operator succeeds

#### Scenario: A document's kind cannot be changed by a submission

- **WHEN** a submission's `kind` differs from the document's recorded `kind`
- **THEN** it is refused, and the document's recorded `kind` is unchanged

### Requirement: A change's delta is absorbed into the corpus by an authored merge

The Hub SHALL let the operator merge a reviewed, approved or archived change document into one or
more capability documents: writing new content into a named capability document and recording, for
each source change named, who performed the merge and when.

The Hub SHALL refuse a merge whose target is not a capability document. The Hub SHALL refuse a merge
naming a source document that is not `approved` or `archived` — a merge cites finished work, not work
still being decided about.

A merge record SHALL be attributable only to the operator.

Merging SHALL NOT be a precondition for archiving a change document, and archiving SHALL NOT be a
precondition for merging one — the Hub SHALL allow either to happen first, or a change to be archived
having never been merged.

Every merge SHALL be retrievable both by the capability document it changed and by the change document
it came from.

#### Scenario: A merge writes the capability document and records its source

- **WHEN** the operator merges a change document into a capability document
- **THEN** the capability document's content becomes what was submitted
- **AND** a merge record links the two documents, attributed to the operator

#### Scenario: A merge cannot target a non-capability document

- **WHEN** a merge names a target document that is not a capability document
- **THEN** it is refused

#### Scenario: A merge cannot cite unfinished work

- **WHEN** a merge names a source document that is `exploring` or `proposed`
- **THEN** it is refused

#### Scenario: Archiving and merging are independent

- **WHEN** a change document is merged into a capability document before it is archived, or archived
  before it is ever merged
- **THEN** neither act blocks or requires the other

#### Scenario: A merge is found from either side

- **WHEN** a change document has been merged into a capability document
- **THEN** the merge is retrievable by querying either document

## MODIFIED Requirements

### Requirement: A document has a phase and the Hub owns its transitions

A specification document SHALL carry a phase the Hub alone assigns and transitions: `exploring`,
`proposed`, `approved`, `archived`, or `current`. The phase SHALL be read from a database row the Hub
controls, never from content in the file itself, which the operator or an agent can edit.

`current` SHALL be reachable only at document creation, for a document of `kind` `capability`, and
SHALL have no transition into or out of it through the ordinary phase-transition operation. Every other
phase SHALL be reachable only through the transitions this capability declares, and an attempted move
outside them SHALL be refused, naming why.

#### Scenario: An unrecognised phase is refused

- **WHEN** a transition names a phase this capability does not define
- **THEN** it is refused

#### Scenario: An illegal transition is refused

- **WHEN** a transition is attempted between two phases with no direct move between them
- **THEN** it is refused, naming the phases involved

#### Scenario: current has no transition

- **WHEN** any caller attempts to move a document to or from `current` through the transition operation
- **THEN** it is refused

### Requirement: Approval is the operator's decision and no agent can express it

Approving a document, and archiving one, SHALL be decisions only the operator can make. Both SHALL be
enforced at the point the Hub actually changes a document's phase, not only at whichever surface a
caller happens to reach it through — a rule checked in one place only survives until a second caller
of that place is added.

#### Scenario: An agent cannot approve

- **WHEN** an agent attempts to move a document to `approved`
- **THEN** it is refused, and the refusal says approval is the operator's

#### Scenario: An agent cannot archive

- **WHEN** an agent attempts to move a document to `archived`
- **THEN** it is refused, and the refusal says archiving is the operator's

#### Scenario: The refusal holds regardless of caller

- **WHEN** either transition is attempted through any code path that ultimately calls the Hub's phase
  transition operation
- **THEN** the same refusal applies, because the check is made there and not duplicated per caller
