## MODIFIED Requirements

### Requirement: Introducing an enforced posture does not change existing runs

The built-in posture a run receives when neither its conversation nor its agent states one SHALL be decided in one place per provider, and every surface that shows a posture at rest SHALL show that posture.

For a run the Hub can answer, that posture is the one in which the Hub decides each tool call
against the run's workspace. A posture that accepts edits but leaves execution to a prompt nobody
can answer lets an agent write code and never run it. A run the Hub cannot answer receives the
posture that accepts edits, and a provider whose own default already confines the run to its
workspace keeps that default.

Flags that serve the enforced posture SHALL be emitted only for that posture, and only where the
mechanism answering them is present.

#### Scenario: The default spawned is the default shown

- **WHEN** a non-yolo run is spawned with no posture selected by its conversation or its agent
- **THEN** it is spawned under the built-in posture for its provider
- **AND** that is the posture the app showed for it at rest

#### Scenario: Other postures carry no enforcement machinery

- **WHEN** a run selects a posture other than the enforced one
- **THEN** its command carries nothing referring to the enforcement mechanism

#### Scenario: No enforcement is claimed without an answerer

- **WHEN** the enforced posture is selected but no mechanism is present to answer its requests
- **THEN** the command does not claim enforcement it cannot perform
