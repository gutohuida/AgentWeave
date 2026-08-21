## ADDED Requirements

### Requirement: Who may start a document is determined by its kind, not by the caller being the operator

The Hub SHALL determine who may create a specification document from the kind of document being
created. The operator MAY create a document of any kind. An agent MAY create a change specification
and no other kind.

The previous rule — that a document is started by the operator and filled in by an agent — was
broader than the thing it protected. What has value in a specification corpus, and what agents must
not write, is the record of current shipped behaviour: capability documents, already refused to
agents at the point of writing whatever route is used. Guarding creation as well made the write-time
refusal redundant for capability documents and made change specifications, which agents are expected
to author, unreachable for no stated reason.

Constraining kind **at creation** rather than only at write is load-bearing rather than tidy. A
capability document is created directly in the current phase, so a kind checked only at write would
allow an agent to create one it could then never fill in.

#### Scenario: An agent creates a change specification

- **WHEN** an agent creates a specification document
- **THEN** a change specification is created

#### Scenario: The operator's creation is unchanged

- **WHEN** the operator creates a document of any kind
- **THEN** it is created as before, with the kind the operator supplied

#### Scenario: Capability documents remain the operator's to start and to write

- **WHEN** an agent attempts to create or to write a capability document
- **THEN** it is refused in both cases

### Requirement: Approval remains the operator's regardless of who authored the document

A document created by an agent SHALL be subject to exactly the same phase machinery as a document
created by the operator, and its author SHALL gain no standing in it.

Relaxing who may *start* a document says nothing about who may agree to one. These are different
questions and the first must not be read as answering the second.

#### Scenario: An agent-created document still needs operator approval

- **WHEN** an agent-created document is proposed
- **THEN** approval is the operator's decision, as for any document

#### Scenario: Origin is not visible to the phase machine

- **WHEN** a document's phase is transitioned
- **THEN** the transition rules are the same whether the document was created by an agent or by the
  operator
