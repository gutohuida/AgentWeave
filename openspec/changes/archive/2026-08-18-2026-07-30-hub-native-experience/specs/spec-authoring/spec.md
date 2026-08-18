## ADDED Requirements

### Requirement: A specification declares how binding it is

Each specification SHALL declare a rigor level, and SHALL default to the least binding level when
created. At minimum three levels SHALL exist:

- a **sketch**, which records boundaries and constraints, gates nothing, and may be changed freely;
- a **contract**, whose requirements are individually addressable, whose divergence from
  implementation is a defect, and whose changes are proposed for acceptance rather than applied;
- a **gate**, which additionally prevents work from being reported complete while any of its
  requirements lacks accepted evidence.

Raising a document's rigor SHALL be a deliberate act, recorded with who raised it and when. Lowering
it SHALL be equally deliberate and SHALL NOT discard existing evidence.

#### Scenario: New specifications start least binding

- **WHEN** a specification is created
- **THEN** it is a sketch
- **AND** it gates nothing

#### Scenario: Rigor determines who may change the document

- **WHEN** an agent proposes a change to a sketch
- **THEN** the change is applied
- **WHEN** an agent proposes a change to a contract or a gate
- **THEN** the change awaits operator acceptance

#### Scenario: Promotion is deliberate and recorded

- **WHEN** a specification's rigor is raised
- **THEN** the change is recorded with its author and time

#### Scenario: Demotion preserves evidence

- **WHEN** a specification's rigor is lowered
- **THEN** existing evidence and links are retained

#### Scenario: Only a gate blocks completion

- **WHEN** work is reported complete against a gate whose requirements lack accepted evidence
- **THEN** completion is refused and the unsatisfied requirements are identified
- **WHEN** the same work is reported against a sketch or a contract
- **THEN** completion is not blocked, though unserved requirements are still reported

### Requirement: Authoring is a conversation against a visible document

While authoring, an operator SHALL see the document and converse about it in the same place, and
proposed changes SHALL appear in the document itself rather than being described.

Each proposed change SHALL be individually acceptable or rejectable. Rejecting a change SHALL leave
the document exactly as it was.

#### Scenario: Proposals appear in the document

- **WHEN** an assisting agent proposes a change during authoring
- **THEN** the change is shown in position within the document
- **AND** what it replaces remains legible

#### Scenario: Changes are accepted or rejected individually

- **WHEN** several changes are proposed at once
- **THEN** the operator may accept some and reject others

#### Scenario: Rejection leaves no residue

- **WHEN** a proposed change is rejected
- **THEN** the document is exactly as it was before the proposal

#### Scenario: Accepted changes to a contract are attributed

- **WHEN** a proposed change to a contract or gate is accepted
- **THEN** the record names both the proposing agent and the accepting operator

### Requirement: A specification can always be started from existing material

Creating a specification SHALL offer at least: deriving one from existing implementation, growing
one from a conversation, and starting from a template. An empty document MUST NOT be the only
available starting point.

A derived specification SHALL be marked as derived and SHALL start as a sketch, because material
inferred from implementation has not been confirmed as intent.

#### Scenario: Several on-ramps are offered

- **WHEN** an operator creates a specification
- **THEN** deriving from existing implementation, growing from a conversation, and starting from a
  template are all available

#### Scenario: Derived specifications are marked and unbinding

- **WHEN** a specification is derived from existing implementation
- **THEN** it is marked as derived
- **AND** it is a sketch until an operator raises it

### Requirement: Assistance during authoring is scoped to specification

An agent assisting with authoring SHALL act within the project's specifications and SHALL NOT modify
implementation as part of authoring.

Where authoring reveals work to be done, the agent SHALL propose that work rather than perform it.

#### Scenario: Authoring does not change implementation

- **WHEN** an agent assists with authoring
- **THEN** it does not modify implementation

#### Scenario: Discovered work is proposed, not performed

- **WHEN** authoring reveals implementation work
- **THEN** the agent proposes that work for the operator to accept

### Requirement: Specification assistance is available wherever specifications are

The capabilities used to explore, draft, revise, and reindex specifications SHALL be available to an
agent assisting an operator in the specification workspace, not only to an operator invoking them
from a command line.

#### Scenario: Authoring capabilities are reachable from the workspace

- **WHEN** an operator authors a specification in the workspace
- **THEN** exploration, drafting, revision, and reindexing are available there
- **AND** no command line is required

### Requirement: The specification workspace meets the interface standard of the rest of the Hub

The specification workspace SHALL use the same visual language, control behaviour, motion, and
typography as every other part of the Hub, and SHALL derive its live state from the same event
stream.

It MUST NOT be a lesser-finished surface than the agent conversation.

#### Scenario: The workspace is not a lesser surface

- **WHEN** the specification workspace is compared with the agent conversation
- **THEN** it uses the same controls, motion, typography, and separation treatment

#### Scenario: The workspace is live

- **WHEN** a requirement's verification state changes while an operator is reading it
- **THEN** the workspace reflects the change without an operator action

#### Scenario: Agent identity is consistent here too

- **WHEN** an agent is represented in the specification workspace
- **THEN** it carries the same identity colour and name it carries elsewhere

### Requirement: Specifications remain plain, portable documents

A specification SHALL remain readable and editable outside the Hub, and its identifiers, structure,
and rigor declaration SHALL be legible in the document itself rather than held only in the Hub.

Work performed outside the Hub SHALL be reconcilable rather than lost.

#### Scenario: A specification is legible outside the tool

- **WHEN** a specification is read outside the Hub
- **THEN** its requirements, their identifiers, and its rigor level are all legible in the document

#### Scenario: External edits reconcile

- **WHEN** a specification is edited outside the Hub
- **THEN** the change is reconciled and reported
- **AND** existing links and evidence are preserved where their requirements still exist
