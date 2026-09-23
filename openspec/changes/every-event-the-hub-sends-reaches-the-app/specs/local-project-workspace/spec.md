## ADDED Requirements

### Requirement: The app receives every event kind the Hub broadcasts
The Hub SHALL declare every event kind it broadcasts in one server-side registry, and the app MUST NOT discard a received event because its kind is absent from a client-side list.

A broadcast of a kind the registry does not declare SHALL fail the Hub's test suite, and so SHALL a
registered kind that no code broadcasts. At runtime such a broadcast SHALL still be sent and SHALL
be logged as a warning; it MUST NOT fail the operation that sent it. The app's copy of the
vocabulary SHALL be generated from the registry, and a stale copy SHALL fail the Hub's test suite.

#### Scenario: An event the app has handling code for reaches it
- **WHEN** the Hub broadcasts `checkpoint_ready` for a conversation whose agent panel is open
- **THEN** the panel's checkpoint list is refetched and the checkpoint offer appears without a reload

#### Scenario: Archiving a job refreshes the job list
- **WHEN** the operator archives a job and the Hub broadcasts `job_archived`
- **THEN** the project's job list is refetched

#### Scenario: A kind the app has no case for is still delivered
- **WHEN** the app receives an event whose kind it has no specific handling for
- **THEN** the event is dispatched to listeners and appears in the live Activity feed

#### Scenario: A broadcast of an undeclared kind is caught
- **WHEN** Hub code broadcasts a kind that is not in the registry
- **THEN** the Hub's test suite fails, naming the file and line of the broadcast
