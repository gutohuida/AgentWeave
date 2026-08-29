# hub-api-request-contract — delta

## ADDED Requirements

### Requirement: A request body field the system cannot honour is refused by name

A write request carrying a field the receiving contract does not declare SHALL be refused, and the refusal SHALL name the field.

Silently discarding an undeclared field tells the caller their request was understood when part of
it was not. Where the discarded field selects a safety posture, the caller is told a run began under
supervision they asked for and did not receive — and the run is already executing by the time the
response is read. There is no response the caller can inspect to learn that the field was dropped,
so the tolerance cannot be detected, only suffered.

The refusal SHALL be uniform across the write surface. A caller cannot be expected to know which
routes read their whole request and which read part of it; two policies in one interface make the
strict routes look arbitrary and the lax ones look safe. The rule holds for a field that is merely a
typo as much as for one that changes behaviour, because the system cannot tell those apart — only
the caller can, and only if told.

A contract MAY decline this rule where the system's answer to an undeclared field is to **honour the
request in a way the field could not have expressed**, rather than to ignore the field. Where a
destination is minted rather than accepted, sending a destination is not a misunderstanding to
refuse; it is a request the system answers completely, on its own terms. Such a contract SHALL state
in its own text why it declines, so that a declining contract is distinguishable from one where the
rule was never applied.

Where a contract accepts a superseded vocabulary by translating it into its declared fields before
validating them, the translation SHALL consume only the names it recognises and SHALL carry every
other field forward to be refused. A translation that rebuilds the request from the names it knows
discards the rest silently, which is this rule's own failure reintroduced inside the mechanism meant
to satisfy it — and hidden better, because the contract's declaration says it refuses unknown
fields while one of its vocabularies does not.

The system SHALL detect a write contract that neither refuses undeclared fields nor states why it
does not. The rule's failure mode is omission: it is enforced by writing nothing, so its absence is
invisible on inspection and its cost surfaces only when a caller sends the field. Any check
performed once decays at the next route added.

#### Scenario: An undeclared field is refused

- **WHEN** a caller submits a write request carrying a field the contract does not declare
- **THEN** the request is refused
- **AND** the refusal names the undeclared field

#### Scenario: A safety-relevant field is not silently discarded

- **WHEN** a caller submits a request to start agent work, naming a supervision posture in a field the contract does not declare
- **THEN** no work is started
- **AND** the caller is told which field was not understood

#### Scenario: A contract that mints rather than accepts may decline the rule

- **WHEN** a write contract answers an undeclared field by producing a value the caller could not have supplied
- **THEN** that contract may accept the request without refusing the field
- **AND** its own text states why it declines the rule

#### Scenario: A translated legacy vocabulary refuses what it does not recognise

- **WHEN** a caller submits a request in a superseded vocabulary the contract translates, carrying a field that vocabulary does not define
- **THEN** the request is refused
- **AND** the refusal names that field
- **AND** a request in that vocabulary carrying only names it defines is accepted

#### Scenario: A write contract that is silently lax is detected

- **WHEN** a write contract neither refuses undeclared fields nor states why it declines the rule
- **THEN** the system reports it as a defect
