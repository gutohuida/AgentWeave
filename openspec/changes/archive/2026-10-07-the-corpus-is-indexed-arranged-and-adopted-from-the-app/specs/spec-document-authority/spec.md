## MODIFIED Requirements

### Requirement: A failure to write the index does not abandon the requirement index

When the document index cannot be written, the requirement index SHALL still be rebuilt, and the
reason the file was not written SHALL be reported.

Rebuilding covers two indexes — the requirement index held as records, and the document index held
as a file — and only the file can be blocked on a decision that is the operator's to make.

The same SHALL hold when the file cannot be written for a reason outside the Hub (a full disk, a
permission, a locked file). Such a failure SHALL be reported in the rebuild's own response as a
sentence naming the reason, not as a bare server error that discards the requirement index with it.
A failed index write SHALL leave the previous index file as it was. A document that cannot be
re-rendered for the same kind of reason SHALL be reported as skipped with that reason, and the
rebuild SHALL continue with the other documents.

A placement whose index cannot be written SHALL be refused with the reason. Nothing is placed, and
the previous index stays in place.

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

#### Scenario: An index file that cannot be written still rebuilds the requirements

- **GIVEN** a project whose index file cannot be written
- **WHEN** the operator rebuilds
- **THEN** the requirement index is rebuilt and kept
- **AND** the response reports that no document index was written, naming the reason
- **AND** the previous index file is unchanged

#### Scenario: A document that cannot be re-rendered is skipped, not fatal

- **WHEN** one document's file cannot be written while the corpus is re-rendered
- **THEN** that document is reported as skipped, with the reason
- **AND** the other documents are still re-rendered and recorded

#### Scenario: A placement whose index cannot be written is refused with the reason

- **WHEN** the operator places a document and the index file cannot be written
- **THEN** the placement is refused with a message naming the reason
- **AND** the previous index file is unchanged
