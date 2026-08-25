## ADDED Requirements

### Requirement: Divergence is reported when a document is read, not only when it is written

Serving the content of a document whose approved digest no longer matches what is on disk SHALL mark
that divergence to every reader — the operator in the interface, and any agent reading it through
the tool surface.

The Hub already holds both halves: the digest of what was approved, and a comparison function. That
function has exactly one caller and it is on the **save** path, so divergence is noticed only when
somebody tries to write and never when somebody reads. An approved document edited directly on disk
is therefore served to everyone with nothing marking it.

This inverts the guarantee the phase machine exists to provide. The phase is authoritative because
it is read from a row rather than from a file an agent can write — but the **content** is still
served from that file, unchecked, so approval attaches to a path rather than to the bytes anyone
subsequently reads.

Divergence SHALL be marked, not refused. Editing an approved document on the way to a new revision
is legitimate, and refusing the read would break it.

#### Scenario: An approved document is edited on disk
- **WHEN** an approved document's file no longer matches its approved digest and any reader requests it
- **THEN** the response SHALL carry the content and SHALL mark it as diverged from what was approved

#### Scenario: An agent reads a tampered document
- **WHEN** an agent reads such a document through the tool surface
- **THEN** the divergence SHALL be stated to the agent

#### Scenario: An unmodified approved document
- **WHEN** an approved document matches its digest
- **THEN** no divergence SHALL be reported

#### Scenario: The document listing
- **WHEN** documents are listed
- **THEN** a diverged document SHALL be identifiable from the listing

### Requirement: A document that produced nothing can be archived

A document that has never been approved and from which nothing has been materialised SHALL be
archivable, so that one created by mistake can be retired.

Today such a document is permanent in every direction: archiving requires approval, approval
requires proposal, proposal requires requirements the orphan does not have, and there is no
deletion. It is not inert — it leaves a standing drift warning that nobody can clear.

Retirement SHALL go through the phase machine rather than a separate deletion path, so that phase
remains the single mechanism and the archived phase's existing effects apply unchanged.

#### Scenario: An orphan document is archived
- **WHEN** a document in an early phase with no requirements and no materialised tasks is archived
- **THEN** the transition SHALL be permitted
- **AND** the drift warning it caused SHALL clear

#### Scenario: A document with materialised work
- **WHEN** archiving is attempted on a document from which tasks have been materialised
- **THEN** it SHALL be refused, naming what depends on it

#### Scenario: The approved path is unchanged
- **WHEN** an approved document is archived
- **THEN** the existing behaviour SHALL apply unchanged
