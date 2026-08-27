## MODIFIED Requirements

### Requirement: Operator-facing severity values are the ones the operator's view understands

Events persisted for the operator's attention SHALL use the severity vocabulary the operator's views
filter and style by. The persistence layer SHALL enforce this by normalising any severity value
against an enumerated set before writing, rather than relying on every caller to pass an already-
correct value. Any live notification of the same event, such as a real-time broadcast to connected
views, SHALL carry the same normalised value, not the caller's original string.

A severity that no view recognises is worse than none: the row renders unmarked and is hidden by the
filter intended to reveal it, so the events most needing attention are the ones least likely to be
seen.

#### Scenario: A refused action is recorded

- **WHEN** the system records that an agent's action was refused
- **THEN** the stored severity is one the operator's activity view filters and styles by

#### Scenario: A caller supplies a severity outside the enumerated set

- **WHEN** any caller, internal or external, persists an event with a severity value that is not in
  the enumerated set the operator's views understand
- **THEN** the value that is actually written is a value from the enumerated set, not the caller's
  original string

#### Scenario: An externally-submitted event cannot bypass the vocabulary

- **WHEN** an event is submitted through an API that accepts a caller-supplied severity string
- **THEN** the same normalisation applies as for events persisted from within the system

#### Scenario: A live broadcast matches the persisted value

- **WHEN** an event with a severity outside the enumerated set is submitted through an API that both
  persists the event and broadcasts it to connected views in real time
- **THEN** the severity carried by the broadcast is the same normalised value that was written, not
  the caller's original string
