## MODIFIED Requirements

### Requirement: Job failure diagnostics
The system SHALL make scheduled and manually fired job failures durable and visible, and SHALL NOT record as failed a job run whose input is queued and whose turn has not started yet for a reason that can clear on its own.

A job run whose input is queued and whose turn could not start yet is waiting, not failed: the system
retries starting it (`agent-conversation-workspace`, *Input the system has accepted is answered as
accepted*). It becomes failed only if the start is refused terminally, or if no run is ever behind it
by the time the system reconciles stale job runs.

#### Scenario: Job run failure records summary
- **WHEN** a job run fails to start, fails to trigger an agent, or raises an internal scheduler error
- **THEN** the system records the run as failed with a secret-safe error summary and emits a structured diagnostic event

#### Scenario: A job run whose turn has not started yet is not a failure
- **WHEN** a job run has queued its input
- **AND** the attempt to start the agent's turn fails for a reason that can clear on its own
- **THEN** the run is not recorded as failed
- **AND** it stays in progress while the system retries starting the turn

#### Scenario: Job UI can distinguish failed from idle
- **WHEN** a job has a recent failed run
- **THEN** the Hub job view exposes that failed state separately from jobs that are merely disabled, pending, or idle
