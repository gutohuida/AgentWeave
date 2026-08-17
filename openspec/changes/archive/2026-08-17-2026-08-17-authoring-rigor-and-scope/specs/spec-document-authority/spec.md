# spec-document-authority

## ADDED Requirements

### Requirement: A document at contract or gate rigor gates edits behind an operator-accepted proposal

A specification document whose rigor is `contract` or `gate` SHALL NOT apply an agent's submitted edit
directly to the live document. Instead, the Hub SHALL compute the difference between the submitted
content and the document's currently stored content, and SHALL record one pending, individually
addressable proposal per changed unit — each added, modified, or removed requirement, identified by
its key (the document-scoped handle an agent's submission carries; a requirement newly added by a
proposal has no Hub-minted public identifier until the proposal is accepted), plus one proposal
covering the document's non-requirement content (summary, problem, scope, design, tasks, algorithms,
open questions) as a single unit when any of it changes. The live document SHALL remain exactly as it
was until an operator accepts a specific proposal. A document at `sketch` rigor is unaffected: an
agent's submission continues to apply immediately.

#### Scenario: A submission against a gate-rigor document creates proposals instead of applying

- **WHEN** an agent submits an edit against a document whose rigor is `gate`, changing two
  requirements and leaving the rest unchanged
- **THEN** neither requirement's live content changes
- **AND** exactly two pending proposals are recorded, each naming the requirement it targets

#### Scenario: The same submission against a sketch-rigor document applies immediately

- **WHEN** an agent submits the same shape of edit against a document whose rigor is `sketch`
- **THEN** the live document is updated immediately, with no proposal recorded, unchanged from a
  document with no rigor gating at all

#### Scenario: A no-op submission creates no proposal and is not an error

- **WHEN** an agent submits a `contract`- or `gate`-rigor document's content unchanged from what is
  currently stored
- **THEN** no proposal is created
- **AND** the submission is not reported as a failure

### Requirement: A pending proposal is discoverable in position and is individually acceptable

A pending proposal targeting a requirement SHALL be discoverable at that requirement when the document
is read, not only in a separate list. A pending proposal targeting the document's non-requirement
content SHALL be discoverable at the document's summary. Accepting or rejecting one proposal SHALL NOT
alter the status of any other pending proposal on the same document.

#### Scenario: Two proposals on the same document are independent

- **WHEN** a document has one pending proposal against requirement FR-3 and another against its
  metadata
- **THEN** an operator can accept the FR-3 proposal without the metadata proposal changing state
- **AND** the metadata proposal remains pending and unapplied

#### Scenario: A rejected proposal leaves the document exactly as it was

- **WHEN** an operator rejects a pending proposal
- **THEN** the live document's content is unchanged
- **AND** reading the requirement or metadata section the proposal targeted shows no trace of the
  rejected content

### Requirement: An accepted proposal is attributed to both its proposer and its accepter

The record of an accepted proposal SHALL name both the actor whose submission created the proposal and
the operator who accepted it, as distinct fields, in a shape that does not let one overwrite the
other.

#### Scenario: Both identities survive being read back later

- **WHEN** a proposal created by agent run `run-123` is accepted by operator `alex`
- **THEN** a later read of that document's history reports `run-123` as the proposer and `alex` as the
  accepter of that specific content change
- **AND** neither identity is lost or merged into a single field

### Requirement: Accepting or rejecting a proposal is reserved to the operator

An agent-authenticated actor SHALL NOT accept or reject a proposal, mirroring the existing rule that
approving or archiving a specification document is reserved to the operator. This SHALL be enforced in
the functions that perform acceptance and rejection, not only at the API boundary.

#### Scenario: An agent's attempt to accept its own proposal is refused

- **WHEN** an actor of kind `agent` attempts to accept a pending proposal, including one it created
  itself
- **THEN** the attempt is refused
- **AND** the proposal's status is unchanged

### Requirement: A proposal that no longer matches the document's current content is not silently applied

Accepting a proposal SHALL be refused, rather than applied against content it was never compared
against, if the document's stored content has changed since the proposal was created — through
another accepted proposal, a direct edit while still at `sketch` rigor before promotion, or a rigor
change. A refused-as-stale proposal SHALL be marked distinctly from a pending or accepted one so it is
not mistaken for either.

#### Scenario: Accepting a proposal whose document has moved underneath it is refused

- **WHEN** an operator attempts to accept a proposal whose captured digest no longer matches the
  document's current content digest
- **THEN** the attempt is refused with a stated reason
- **AND** the proposal is reported as stale, not accepted

### Requirement: Authoring assistance is scoped away from performing discovered implementation work

WHEN an agent's turn is triggered with a specification document open, THEN the spawned run SHALL NOT
be granted the ability to write or edit files in the project workspace for that turn, regardless of
the document's phase or rigor, and regardless of the run's configured permission posture (including a
posture that would otherwise skip permission prompts entirely). The turn's context SHALL state that
discovered implementation work is to be proposed — for example, by creating a task — rather than
performed directly. A turn triggered with no specification document open is unaffected.

#### Scenario: A file-editing attempt during a spec-authoring turn is unavailable, not merely discouraged

- **WHEN** an agent is triggered with a specification document open and, in the course of the turn,
  identifies a code change needed to fix a discovered problem
- **THEN** the run has no file-write tool available to make that change directly
- **AND** the turn's context states that the discovery should be recorded as a proposed task instead

#### Scenario: The restriction holds even under a permission posture that skips prompts

- **WHEN** an agent is triggered with a specification document open and a permission posture that
  would otherwise let every tool call proceed without a prompt
- **THEN** the run still has no file-write tool available for that turn

#### Scenario: A turn with no document open is unrestricted

- **WHEN** an agent is triggered with no specification document open
- **THEN** its tool surface is exactly what it would be without this requirement in effect
