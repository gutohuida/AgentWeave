## ADDED Requirements

### Requirement: A document's path is fixed once it has ever been approved

The Hub SHALL refuse to rename a document that has been approved at any point, not only one that is
approved at the moment of the request.

The rule that a document's path is part of what was approved is already stated, and it is already
enforced — but only while the document sits in the approved phase. Approved has two exits: a document
may be archived, and it may be reopened for revision. Both leave the phase, and both therefore
release a path the approval was supposed to have fixed. An approved document's path can consequently
be changed today by archiving it first, which the rule plainly does not intend.

Once other work refers to a document by path, that path is a promise rather than a convenience: a
reference recorded in another document travels with the repository and cannot be repaired by a
database that stayed behind.

Having been approved SHALL be recorded durably and SHALL NOT be cleared when the document leaves the
approved phase. This distinguishes it from the record of exploration having been closed, which is
deliberately cleared on reopening because reopening genuinely reopens the exploration — whereas
reopening does not un-approve history.

#### Scenario: An archived document keeps its path

- **WHEN** a rename is attempted on a document that was approved and has since been archived
- **THEN** the rename is refused

#### Scenario: A reopened document keeps its path

- **WHEN** a rename is attempted on a document that was approved and has since been reopened for
  revision
- **THEN** the rename is refused

#### Scenario: A document that has never been approved may still be renamed

- **WHEN** a rename is attempted on a document that has never been approved
- **THEN** the rename succeeds

#### Scenario: Approval is recorded durably

- **WHEN** a document is approved and subsequently leaves the approved phase
- **THEN** the record that it was approved remains

### Requirement: A document may declare a dependency on another document's work

A specification document SHALL be able to reference a task belonging to another document, so that the
order of work spanning documents is recorded in the specifications rather than only in the heads of
the people coordinating it.

Such a reference SHALL name a document that has been approved. The restriction is what makes the
reference sound: an approved document's path is fixed, so the reference cannot be broken by a rename,
and an approved document has already produced its tasks, so the referenced work exists.

#### Scenario: A cross-document reference is recorded in the document

- **WHEN** a document declares a dependency on an approved document's task
- **THEN** the reference is part of the document's own content

#### Scenario: A reference to an unapproved document blocks a proposal

- **WHEN** a document references a task in a document that has not been approved
- **THEN** the document cannot be proposed until it has been
