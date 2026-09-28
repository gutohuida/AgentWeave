## ADDED Requirements

### Requirement: A run states how it reached the Hub

The system SHALL show, for each run, which surface the run was told to reach the Hub through and whether its harness started the Hub's tool server, and when a run given the server did not start it, SHALL say so once in that run's own activity, naming the surface the run was actually told to use.

An operator whose machine blocks tool-protocol servers learns it today only from the harness's own
wording, if it appears at all, while the run quietly behaves differently. Stating it once, where the
run's activity is read, turns a silent degradation into a fact the operator can act on.

A run is not always told its surface after its own test. Some runners are told before they start,
from the agent's history, and their own test can then come back negative. The statement names what
that run was told, not what the next run will be, because a statement that the run was told the call
command, made about a run told the tool-protocol surface, is the very disagreement between telling
and fact this requirement exists to expose. Where the runner's own failure message already states
it, that message is the one statement, and it too names the surface the run was told: a message
saying the run had no way to reach the Hub, about a run told the call command, is false in the same
way. Where the operator has declared the surface the agent uses, the statement does not promise that
the next run is told otherwise.

Where the harness gives its own account of the server, that account SHALL be quoted verbatim beside
the statement and SHALL NOT be what the system decides from.

#### Scenario: A run's facts carry its surface

- **WHEN** a run's facts are read
- **THEN** they state the surface the run was told and whether its harness started the server, or
  that it was not tested

#### Scenario: A run whose server did not start says so once

- **WHEN** a run was given the Hub's tool server, was told the call command, and its harness did
  not start the server
- **THEN** that run's activity holds exactly one statement saying so and naming the call command as
  the surface it was told

#### Scenario: A run told the tool surface whose server then failed says so truthfully

- **WHEN** a run was told the tool-protocol surface from its agent's history, and its own harness then
  reported that the server failed or was left out
- **THEN** that run's activity holds exactly one statement saying the server did not start although
  the run was told to use it
- **AND** it does not say the run was told the call command

#### Scenario: A runner's own failure message names the surface the run was told

- **WHEN** a runner reports in its own message that the Hub's tool server failed to start, for a run
  that was told the call command
- **THEN** that message states that the run was told to reach the Hub through the call command
- **AND** it does not state that the run had no way to send messages, update tasks or ask questions

#### Scenario: The harness's own words are quoted, not interpreted

- **WHEN** the harness reports its own reason for not starting the server
- **THEN** the statement quotes it
- **AND** what the run is told does not depend on its wording
