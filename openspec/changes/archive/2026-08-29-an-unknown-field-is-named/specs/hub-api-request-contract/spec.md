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
validating them, the translation SHALL remove every name that vocabulary defines and SHALL carry
every other field forward to be refused. A translation that rebuilds the request from the names it
knows discards the rest silently, which is this rule's own failure reintroduced inside the mechanism
meant to satisfy it — and hidden better, because the contract's declaration says it refuses
unknown fields while one of its vocabularies does not.

What the translation removes SHALL be the vocabulary it defines, not the names it happened to read.
A superseded vocabulary commonly offers several names for one value, and a request carrying two of
them is what a rolling upgrade emits rather than a mistake: the translation reads one, and refusing
the other would refuse a name the contract itself declares it accepts. A field the vocabulary does
not define SHALL still be refused, and both vocabularies SHALL be refused on the same terms.

The vocabulary SHALL include the names the superseded writer emitted that the translation reads
nowhere at all. A retired writer commonly sends values the current contract has stopped acting on —
a threshold it now derives itself, an identifier the route already carries — and those names appear
in no translation rule precisely because nothing consumes them. Enumerating the vocabulary from the
translation's own reads therefore misses them, and the omission is invisible while the translation
rebuilds the request, because rebuilding drops them silently. Refusing them once it stops rebuilding
turns a request the contract is required to accept into an error.

The system SHALL detect a write contract that neither refuses undeclared fields nor states why it
does not. The rule's failure mode is omission: it is enforced by writing nothing, so its absence is
invisible on inspection and its cost surfaces only when a caller sends the field. Any check
performed once decays at the next route added.

A write request that declares no contract for its body SHALL be detected by that same check. A body
accepted as an open mapping does not declare a field, so it cannot refuse one, and it evades a check
that inspects contracts by having none to inspect — the rule's absence is invisible there twice
over. Such a route SHALL either declare a contract or be recorded as declining, on the same terms as
any other exemption.

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

#### Scenario: A name the superseded writer emitted but nothing reads is accepted

- **WHEN** a caller submits a request in a superseded vocabulary carrying a name that writer emitted and the translation reads nowhere
- **THEN** the request is accepted and translated
- **AND** that name is not refused

#### Scenario: A superseded vocabulary carrying two names for one value is accepted

- **WHEN** a caller submits a request carrying two names the superseded vocabulary defines for the same value, of which the translation reads one
- **THEN** the request is accepted and translated
- **AND** the name the translation did not read is not refused

#### Scenario: A body with no declared contract is detected

- **WHEN** a write route accepts its body as an open mapping rather than as a declared contract
- **THEN** the system reports it as a defect
- **AND** reporting it does not depend on the route being sent an undeclared field

#### Scenario: A write contract that is silently lax is detected

- **WHEN** a write contract neither refuses undeclared fields nor states why it declines the rule
- **THEN** the system reports it as a defect
