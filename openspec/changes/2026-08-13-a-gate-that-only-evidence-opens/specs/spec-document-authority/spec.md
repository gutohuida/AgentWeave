# spec-document-authority

## ADDED Requirements

### Requirement: A document declares how strictly it is enforced

A specification document SHALL carry a rigor level of `sketch`, `contract` or `gate`, stated in the
document itself, defaulting to `sketch`.

Rigor says what happens to work that ignores the document. `sketch` reports its state and blocks
nothing. `contract` reports its state, including drift, and blocks nothing. `gate` refuses the
approval of work serving its requirements while any of them is unverified.

**Rigor is not phase.** Phase asks whether the operator has agreed to the document; rigor asks what
follows for work that does not satisfy it. A document may be approved and remain a sketch, or be a
gate while still exploring. Making approval imply enforcement would turn every agreed document into
a barrier.

The Hub SHALL own rigor transitions. A change SHALL be written against the document's current
content digest, so a rigor change cannot land on a document that was edited underneath it, and each
change SHALL be recorded append-only with the actor, the reason, and the digest current at that
moment.

#### Scenario: A document with no stated rigor is a sketch

- **WHEN** a document is created
- **THEN** its rigor is `sketch`
- **AND** it blocks no work

#### Scenario: Rigor is visible in the document

- **WHEN** a document's rigor is set
- **THEN** the rendered document states it

#### Scenario: A rigor change is recorded

- **WHEN** rigor moves from one level to another
- **THEN** the previous level, the new level, the actor and the reason are recorded and never
  overwritten

#### Scenario: A rigor change cannot land on a document that moved

- **WHEN** a rigor change is submitted against a digest that is no longer current
- **THEN** it is refused rather than applied

### Requirement: Only the operator changes rigor

An agent SHALL NOT promote or demote a document's rigor. There SHALL be no argument, tool or route
by which it can express either.

A gate an agent can lower is not a gate. The blocked party would remove the obstacle, and the
enforcement would exist only for agents that did not think to try. Promotion is refused for a
related reason: raising rigor blocks other work, which is a decision about how the project is run.

This is the same construction as approval, and for the same reason: enforced by the absence of a
route rather than by instructing agents not to attempt it. The mechanism it replaces was a charter
instructing an agent to enforce a gate on itself, which is honour-system by construction.

The operator MAY lower rigor, and doing so SHALL be recorded and attributed. An operator who needs
to get past a gate has an explicit, visible way through; what there SHALL NOT be is an unrecorded
override, which is the same act without the evidence that it happened.

#### Scenario: An agent cannot raise rigor

- **WHEN** an agent attempts to promote a document's rigor
- **THEN** it is refused

#### Scenario: An agent cannot lower rigor

- **WHEN** an agent blocked by a gate attempts to demote the document
- **THEN** it is refused
- **AND** the document's rigor is unchanged

#### Scenario: The operator can lower rigor, and it shows

- **WHEN** the operator demotes a document
- **THEN** the demotion is applied and recorded with their attribution

### Requirement: Rigor is only raised on a document that can be enforced

Promotion to `contract` or `gate` SHALL be refused while the document has unresolved requirement
identifiers, duplicate references, or content that does not parse.

Rigor is a claim about enforceability. A document that cannot be read cannot be enforced, and
promoting one would produce a gate whose refusals are parse diagnostics rather than judgements about
the work.

Demotion SHALL NOT be subject to that condition, and SHALL change enforcement only: links,
revisions, evidence and reviews all survive it. A demotion that destroyed the record would be a way
to launder unverified work rather than a way to unblock it.

#### Scenario: A broken document cannot become a gate

- **WHEN** promotion is attempted on a document with an unresolved identifier
- **THEN** it is refused, naming what is unresolved

#### Scenario: Demotion keeps what was established

- **WHEN** a `gate` document is demoted to `sketch`
- **THEN** its requirement links, evidence and reviews are unchanged

#### Scenario: Demotion is always available to the operator

- **WHEN** the operator demotes a document that does not currently parse
- **THEN** the demotion succeeds
