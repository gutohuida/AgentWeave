## ADDED Requirements

### Requirement: A proposal leaves the queue without a judgement when it is repeated, revised or withdrawn

The Hub SHALL NOT record a second pending proposal identical to one already pending from the same proposer against the same document content, SHALL mark a proposer's earlier pending proposal for a unit as superseded when that proposer proposes a different edit to the same unit, and SHALL let the operator withdraw a pending proposal without recording a judgement about its content.

Retries, double submissions and revisions are ordinary, and an agent is told that submitting
repeatedly is expected. Without this the operator's list fills with identical or outdated rows that
nothing distinguishes, and the only way to clear one is to reject it — recording that an edit was
wrong when nobody judged it.

A repeated submission SHALL report which pending proposal already holds each repeated unit.
Proposals from different proposers SHALL NOT supersede each other; they are alternatives, and choosing
between them is the operator's. Withdrawing SHALL be reserved to the operator, like accepting and
rejecting, and a withdrawn or superseded proposal SHALL be marked distinctly from a rejected, stale or
accepted one.

Deciding a proposal — accepting, rejecting or withdrawing it — SHALL be announced to every open view
of the project, so a decided proposal does not stay offered for a decision.

#### Scenario: A repeated submission proposes nothing new

- **WHEN** a proposer submits the same edit twice against a `gate`-rigor document whose content has
  not changed between the two
- **THEN** the second submission records no new proposal
- **AND** its response names the pending proposal that already holds each unit

#### Scenario: A revision supersedes the proposer's earlier proposal

- **WHEN** a proposer submits a different edit to a requirement it already has a pending proposal for
- **THEN** the new proposal is pending
- **AND** the earlier one is marked superseded, naming the new one

#### Scenario: Another proposer's proposal is not superseded

- **WHEN** a second proposer submits an edit to a requirement the first proposer has a pending
  proposal for
- **THEN** both proposals are pending

#### Scenario: The operator withdraws a proposal

- **WHEN** the operator withdraws a pending proposal
- **THEN** it is marked withdrawn and no longer listed as pending
- **AND** no rejection is recorded for it
- **AND** the live document is unchanged

#### Scenario: An agent cannot withdraw a proposal

- **WHEN** an agent-authenticated actor attempts to withdraw a pending proposal
- **THEN** the attempt is refused
- **AND** the proposal's status is unchanged

#### Scenario: A decided proposal leaves every open view

- **WHEN** the operator rejects a pending proposal in one view
- **THEN** the proposal is no longer offered for a decision in any open view of that document
