## ADDED Requirements

### Requirement: A run states how it reached the Hub

The system SHALL show, for each run, which surface the run was told to reach the Hub through and whether its harness started the Hub's tool server, and when a run given the server did not start it, SHALL say so once in that run's own activity, naming the surface the run was told to use instead.

An operator whose machine blocks tool-protocol servers learns it today only from the harness's own
wording, if it appears at all, while the run quietly behaves differently. Stating it once, where the
run's activity is read, turns a silent degradation into a fact the operator can act on.

Where the harness gives its own account of the server, that account SHALL be quoted verbatim beside
the statement and SHALL NOT be what the system decides from.

#### Scenario: A run's facts carry its surface

- **WHEN** a run's facts are read
- **THEN** they state the surface the run was told and whether its harness started the server, or
  that it was not tested

#### Scenario: A run whose server did not start says so once

- **WHEN** a run was given the Hub's tool server and its harness did not start it
- **THEN** that run's activity holds exactly one statement saying so and naming the call command as
  the surface it was told

#### Scenario: The harness's own words are quoted, not interpreted

- **WHEN** the harness reports its own reason for not starting the server
- **THEN** the statement quotes it
- **AND** what the run is told does not depend on its wording
