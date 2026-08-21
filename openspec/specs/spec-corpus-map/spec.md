# spec-corpus-map Specification

## Purpose
TBD - created by archiving change corpus-aware-documents. Update Purpose after archive.
## Requirements
### Requirement: A rendered document carries navigation to its home and its parent

Every rendered specification document SHALL include a navigation region naming the corpus home and,
where one is recorded, the document directly above it. Each SHALL be a relative link resolvable
without a running Hub.

A specification corpus is read as often outside the product as inside it — in a diff, on a code
host, in a browser on a machine with no Hub. A document that cannot be navigated away from is an
island, and thirty-five islands are not a corpus.

The navigation region SHALL depend only on the document's own placement, and SHALL NOT enumerate its
siblings. Sibling navigation is reached through the parent. This bound is deliberate: a strip that
listed siblings would change for every document in a group whenever any one of them was added,
turning a one-document edit into a corpus-wide rewrite.

#### Scenario: A leaf document links home and up

- **WHEN** a document with a recorded parent is rendered
- **THEN** the rendered file contains a link to the corpus home and a link to the parent document

#### Scenario: The home document does not link to itself

- **WHEN** the corpus home document is rendered
- **THEN** the rendered file contains no navigation link to itself

#### Scenario: An unparented document still reaches home

- **WHEN** a document with no recorded parent is rendered
- **THEN** the rendered file contains a link to the corpus home
- **AND** no parent link is shown

#### Scenario: Navigation works without the Hub

- **WHEN** a rendered document is opened directly from disk with no Hub process running
- **THEN** its navigation links resolve to the other documents' files

### Requirement: A document with children renders a generated map of them

A document that other documents name as their parent SHALL render a map section listing each child
with its title, kind, phase and one-line summary, each linked by relative path.

The map SHALL be generated from the document index on every render and SHALL NOT be assembled from
content any author supplied. A map maintained by hand drifts from the corpus the moment a document
is added, and the cost of that drift is paid by the reader who trusts it.

The map region SHALL be visibly identified as generated, so that an operator editing the file does
not lose work to the next regeneration.

A document with no children SHALL render no map section.

#### Scenario: An area document lists its capabilities

- **WHEN** a document named as parent by several others is rendered
- **THEN** its map section lists each of those documents with title, kind, phase and summary

#### Scenario: A leaf renders no map

- **WHEN** a document that no other document names as parent is rendered
- **THEN** the rendered file contains no map section

#### Scenario: The map reflects the index, not the author

- **WHEN** a document's payload contains prose resembling a list of children
- **THEN** the generated map is still built from the document index
- **AND** the authored prose is rendered as authored content, unchanged

#### Scenario: Children are ordered by the arrangement

- **WHEN** a map is generated for children whose recorded order differs from their alphabetical order
- **THEN** the map lists them in recorded order

### Requirement: A child with no usable summary is reported as such

Where a child document's payload carries no summary, or carries only placeholder text, the map SHALL
say that no summary exists rather than rendering an empty cell.

An empty cell reads as a rendering fault and hides a content gap. Saying so turns an invisible
omission into a visible one — the same reason an empty open-questions list states that none are
outstanding instead of omitting the section.

#### Scenario: An empty summary is stated

- **WHEN** a map is generated for a child whose payload summary is empty
- **THEN** the map states that the child has no summary yet

#### Scenario: A summarised child shows its summary

- **WHEN** a map is generated for a child whose payload carries a summary
- **THEN** the map shows that summary

### Requirement: A document's place in the corpus is operator-set and held in the index

A document's parent SHALL be recorded in the project's document index, SHALL name another document
in the same index, and SHALL be settable only by the operator.

Placement is an editorial judgement about what the project is. It is recorded in the index rather
than in a database column because the arrangement must survive the project being copied to another
machine, and it is not derived from directory nesting because a directory layout is not a statement
about meaning.

The Hub SHALL refuse a placement that names an unknown document, that names the document itself, or
that would create a cycle.

#### Scenario: The operator places a document under another

- **WHEN** the operator sets a document's parent to another document in the index
- **THEN** the index records the parent
- **AND** the placement survives a subsequent index rebuild

#### Scenario: An unknown parent is refused

- **WHEN** a placement names a path that is not in the index
- **THEN** it is refused and the index is unchanged

#### Scenario: A cycle is refused

- **WHEN** a placement would make a document its own ancestor
- **THEN** it is refused and the index is unchanged

#### Scenario: A document can be unparented

- **WHEN** the operator clears a document's parent
- **THEN** the index records no parent for it
- **AND** the document renders with a home link and no parent link

#### Scenario: An agent cannot place a document

- **WHEN** placement is attempted by an agent
- **THEN** it is refused

### Requirement: Regeneration is bounded to the documents the arrangement changed

When the document index is rebuilt, the Hub SHALL re-render exactly those documents whose navigation
region or generated map the rebuild changed, and no others.

Rendering the corpus into files buys portability at the cost of writes. The bound is what keeps that
cost proportionate: adding one document must not rewrite every document.

#### Scenario: Adding a document re-renders only its parent

- **WHEN** a new document is added under an existing parent and the index is rebuilt
- **THEN** the parent document is re-rendered
- **AND** no sibling document is re-rendered

#### Scenario: Re-parenting re-renders the document and both parents

- **WHEN** a document's parent changes from one document to another and the index is rebuilt
- **THEN** the moved document, its former parent and its new parent are re-rendered
- **AND** no other document is re-rendered

#### Scenario: A rebuild that changes nothing writes nothing

- **WHEN** the index is rebuilt with no change to any document's title, placement or order
- **THEN** no document file is written

### Requirement: A re-render is driven from the file and is not an authored change

Re-rendering SHALL take the document's structure from the payload embedded in its own file, and
SHALL be recorded as a regeneration distinct from an authored write.

Reading the file rather than the database means a document that arrived by clone regenerates
identically to one the Hub created, and means regeneration does not pass through the write path that
refuses approved documents or attributes editorial change to whoever triggered a rebuild.

A document whose file carries no readable payload SHALL be skipped and reported, never rendered from
guessed structure.

#### Scenario: An approved document still regenerates

- **WHEN** an approved document's generated map changes and the index is rebuilt
- **THEN** the document is re-rendered
- **AND** the regeneration is not refused as a write to an approved document

#### Scenario: A regeneration is distinguishable in the document's history

- **WHEN** a document is re-rendered by a rebuild
- **THEN** the recorded event identifies it as a regeneration rather than an authored change

#### Scenario: A document with no payload is skipped

- **WHEN** a document whose file carries no readable payload block would be re-rendered
- **THEN** it is not written
- **AND** it is reported as skipped, naming the reason

### Requirement: Regeneration records the digest it produced

Where a re-rendered document has a stored content digest, the Hub SHALL update that digest to the
content it just wrote.

Drift detection compares stored content against the file. A regeneration the Hub performed itself
would otherwise be reported as drift, and a drift signal that fires on every rebuild stops being
read.

#### Scenario: A regenerated document is not reported as drifted

- **WHEN** a tracked document is re-rendered by a rebuild and drift is then assessed
- **THEN** the document is not reported as drifted

#### Scenario: A genuine outside edit is still reported

- **WHEN** a regenerated document's file is then edited outside the Hub
- **THEN** drift is reported for it

