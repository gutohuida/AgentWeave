## ADDED Requirements

### Requirement: A rendered document states where it sits, not only what it says

The rendered form of a specification document SHALL carry, in addition to its own content, the
document's relationship to the rest of the corpus: a link to the corpus home and, where recorded, to
the document above it.

This extends the existing guarantee that a rendered document is *self-contained* — inline style
only, no external resource — from "opens correctly alone" to "can be navigated from alone". Both
properties exist for the same reason: the corpus is committed to the project and is read outside the
product at least as often as inside it.

Corpus context SHALL be supplied to rendering rather than stored in the payload. A document's
placement is arrangement, and arrangement belongs to the index, which travels with the project and
is preserved across rebuilds. A payload copy would be a second source of the same truth with no rule
for which wins.

#### Scenario: A document rendered with corpus context carries navigation

- **WHEN** a document is rendered and corpus context is supplied
- **THEN** the rendered file carries navigation built from that context

#### Scenario: A document rendered without corpus context is unchanged

- **WHEN** a document is rendered with no corpus context supplied
- **THEN** the rendered file is byte-identical to what the same payload produced before corpus
  context existed

#### Scenario: Placement is absent from the payload

- **WHEN** a document's payload is read back from its rendered file
- **THEN** it carries no parent or placement field

### Requirement: A Hub-initiated regeneration is not an authored change

Where the Hub re-renders a document to refresh a generated region, that write SHALL be recorded as a
regeneration, SHALL update the document's stored content digest, and SHALL NOT be attributed as an
authored edit to the party who triggered it.

A rebuild is not an act of authorship. Recording it as one would attribute the operator's editorial
voice to a maintenance operation, would refuse on approved documents which have every right to be
regenerated, and would leave the corpus reporting itself as drifted after every rebuild.

#### Scenario: A regeneration is attributed as such

- **WHEN** the Hub re-renders a document during an index rebuild
- **THEN** the recorded event is a regeneration
- **AND** it is not recorded as a content submission by the triggering party

#### Scenario: A regeneration updates the stored digest

- **WHEN** the Hub re-renders a tracked document
- **THEN** the document's stored content digest matches the content just written

#### Scenario: An approved document may be regenerated

- **WHEN** an approved document's generated region changes
- **THEN** the regeneration proceeds
- **AND** the document's phase is unchanged
