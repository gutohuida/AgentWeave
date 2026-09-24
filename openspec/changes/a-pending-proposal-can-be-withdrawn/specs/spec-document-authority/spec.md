## MODIFIED Requirements

### Requirement: A document at contract or gate rigor gates edits behind an operator-accepted proposal

A specification document whose rigor is `contract` or `gate` SHALL NOT apply an agent's submitted edit
directly to the live document. Instead, the Hub SHALL compute the difference between the submitted
content and the document's currently stored content, and SHALL record one pending, individually
addressable proposal per changed unit — each added, modified, or removed requirement, identified by
its key (the document-scoped handle an agent's submission carries; a requirement newly added by a
proposal has no Hub-minted public identifier until the proposal is accepted), plus one proposal
covering the document's non-requirement content (summary, problem, scope, design, tasks, algorithms,
open questions) as a single unit when any of it changes — unless an identical proposal from the same
proposer is already pending against the same document digest, in which case no second proposal is
recorded for that unit and the submission reports the pending one instead. The live document SHALL
remain exactly as it was until an operator accepts a specific proposal. A document at `sketch` rigor is unaffected: an
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

#### Scenario: A repeated unit is reported, not recorded twice

- **WHEN** an agent submits the same edit twice against a `gate`-rigor document whose content did not
  change between the two submissions
- **THEN** the second submission records no proposal for the repeated units
- **AND** it reports the pending proposal that already holds each of them

## ADDED Requirements

### Requirement: A proposal leaves the queue without a judgement when it is repeated, revised or withdrawn

The Hub SHALL NOT record a second pending proposal identical to one already pending from the same proposer against the same document content, SHALL mark a proposer's earlier pending proposal for a unit as superseded when that proposer's newest submission proposes a different edit to that unit or no longer proposes a change to it, and SHALL let the operator withdraw a pending proposal without recording a judgement about its content.

Retries, double submissions and revisions are ordinary, and an agent is told that submitting
repeatedly is expected. Without this the operator's list fills with identical or outdated rows that
nothing distinguishes, and the only way to clear one is to reject it — recording that an edit was
wrong when nobody judged it.

A repeated submission SHALL report which pending proposal already holds each repeated unit.
Proposals from different proposers SHALL NOT supersede each other; they are alternatives, and choosing
between them is the operator's. Withdrawing SHALL be reserved to the operator, like accepting and
rejecting, and a withdrawn or superseded proposal SHALL be marked distinctly from a rejected, stale or
accepted one.

A submission is the proposer's whole document, so it is the proposer's current word on every unit.
A unit it leaves as stored, or no longer mentions, withdraws that proposer's earlier proposal for it.
Otherwise accepting the leftover proposal would apply an edit its own proposer took back.

A proposal SHALL leave `pending` at most once. Of two decisions racing for the same proposal
(accept, reject, withdraw, supersede, or marking it stale), exactly one SHALL take effect. The other
SHALL be refused, or for a supersession skipped, and SHALL NOT overwrite the first.

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

#### Scenario: A unit the proposer takes back is superseded

- **WHEN** a proposer's earlier submission left a pending proposal to remove a requirement
- **AND** the proposer's next submission keeps that requirement exactly as it is stored
- **THEN** the proposal to remove it is marked superseded
- **AND** it is no longer offered for acceptance

#### Scenario: A decided proposal is not decided again

- **WHEN** a proposal is accepted while another request that read it as pending tries to reject,
  withdraw or supersede it
- **THEN** the proposal stays accepted
- **AND** the other request is refused, or makes no change

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
