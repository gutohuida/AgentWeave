# Agent document creation

What an agent may begin, where it lands, what it may not begin, and how the act is attributed.

## ADDED Requirements

### Requirement: An agent may begin a specification document

The capability plane SHALL offer an operation by which an agent creates a specification document,
and the created document SHALL be immediately writable by that agent through the existing submission
operation.

An agent that reaches the point where a finding deserves a document should record it and keep
working. Requiring the operator to create the document first turns every such moment into a stop,
and the operator asked for that stop to be removed.

The created document SHALL enter the same phase and carry the same lifecycle as one the operator
created. Nothing about its origin makes it a lesser document.

#### Scenario: An agent creates a document and fills it in

- **WHEN** an agent creates a specification document and then submits a payload against the returned
  path
- **THEN** the creation succeeds and the submission is accepted

#### Scenario: The created document is in the exploring phase

- **WHEN** an agent creates a specification document
- **THEN** the document's phase is `exploring`

#### Scenario: Creation is attributed to the run

- **WHEN** an agent creates a specification document
- **THEN** the creation event names the agent and its run

#### Scenario: Identity is not taken from the request

- **WHEN** a creation request carries an actor, agent name or run identifier in its body
- **THEN** that value is ignored and identity is taken from the run credential

### Requirement: The Hub chooses where an agent's document lands

The creation operation SHALL NOT accept a document path, a filename, a slug, or any value from which
one is derived. The Hub SHALL mint a placeholder path that is free against both the project's records
and the contents of the specification directory.

Path validation is the single control keeping a document from being written to an arbitrary location
beneath the specification directory. An operation that accepted a destination would make that control
the only guard standing between the least trusted caller in the system and every document in the
corpus — including the capability documents that a separate rule forbids agents from writing. A
minted path makes the wrong destination unexpressible rather than merely refused.

A minted path being free against the filesystem as well as the records is what guarantees that
creation cannot overwrite an existing document.

#### Scenario: No path can be supplied

- **WHEN** an agent attempts to create a document at a chosen path
- **THEN** the path is not honoured and the Hub mints one

#### Scenario: The minted path is unoccupied

- **WHEN** the Hub mints a path for a new document
- **THEN** no record and no file occupies that path

#### Scenario: An existing document is never overwritten

- **WHEN** an agent creates documents repeatedly in a project whose specification directory already
  holds documents
- **THEN** no existing document's file is modified

#### Scenario: The document is named once its subject is known

- **WHEN** an agent renames a document it created, supplying the subject
- **THEN** the document moves to a path derived from that subject

### Requirement: An agent may begin only a change specification

The creation operation SHALL produce a document of the change-specification kind and SHALL NOT offer
any other.

Two reasons, and the first is a trap rather than a preference. A capability document is created
directly in the current phase, and a separate standing rule refuses every capability submission from
an agent — so an agent permitted to choose that kind would create a document that succeeds and can
then never be filled in. Creation that looks like success and produces an unusable artefact is worse
than a refusal.

The second reason is that the remaining kinds describe what a project *is* and how its corpus is
arranged, rather than contributing to it. A change specification is the one kind whose whole
lifecycle is designed to be authored by an agent and gated by the operator at each transition.

A refusal SHALL name what may be created, not only what may not.

#### Scenario: A capability document cannot be created by an agent

- **WHEN** an agent attempts to create a capability document
- **THEN** it is refused
- **AND** the refusal names the kind an agent may create

#### Scenario: The corpus is unreachable through creation

- **WHEN** an agent creates a document and submits a capability payload against it
- **THEN** the submission is refused because the document's kind is fixed at creation

### Requirement: Creating a document confers no authority over it

An agent that created a document SHALL have no capability over that document beyond what any agent
has over any document. In particular it SHALL NOT be able to propose it, approve it, transition its
phase, or archive it.

Authorship is not authority. An agent that could approve what it wrote would be the sole party in
its own gate, which is the arrangement every other rule in the specification lifecycle exists to
prevent.

#### Scenario: The creating agent cannot approve its document

- **WHEN** the agent that created a document attempts to approve it
- **THEN** it is refused

#### Scenario: The creating agent cannot transition its document

- **WHEN** the agent that created a document attempts to move it to another phase
- **THEN** it is refused

### Requirement: Submission against a missing document names the remedy an agent has

Where a submission names a path with no document, the refusal SHALL state that the document can be
created, and SHALL NOT state that only the operator may create it.

This rule previously read that the operator starts an exploration and the agent fills it in. It was
stated in two places — the tool description a model reads before acting, and the error a model reads
after failing. Both are retired by this change, and they are retired together: leaving either would
have the product contradict itself in exactly the place a confused agent looks.

#### Scenario: A missing document is still an error

- **WHEN** an agent submits a payload for a path with no document
- **THEN** the submission is refused

#### Scenario: The refusal names creation as the remedy

- **WHEN** an agent submits a payload for a path with no document
- **THEN** the refusal states that the agent may create the document
