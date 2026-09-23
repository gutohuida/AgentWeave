## ADDED Requirements

### Requirement: A run an earlier Hub process left running SHALL be cleared by the operator's Stop

The Hub SHALL, when the operator stops an agent whose running run was started by an earlier Hub process, end that run's process if it is still alive, record the run as interrupted exactly as it would at its own start, and answer that it did so, and SHALL NOT refuse the stop as not stoppable.

A Hub that starts while an earlier process's agent is still alive leaves that run recorded as
running, because nothing asked for the process to be killed. No part of the new process reads that
run's output or will see it end, so the run stays running for as long as the Hub stays up. Every
route then reports the agent as busy: new turns wait, a direct trigger is refused, and the stop that
exists to end a run was refused as not stoppable. The only way through was a restart, and a restart
does not help while the process is still alive.

A run this process started and has not yet registered SHALL keep being refused as not yet stoppable,
because it will reach a terminal status on its own.

Where a turn is refused or waits because such a run is recorded, the reason given SHALL say that the
run was left by an earlier Hub process and that stopping the agent clears it.

#### Scenario: Stop clears a run left by an earlier Hub

- **GIVEN** a run recorded as running that an earlier Hub process started
- **WHEN** the operator stops that agent
- **THEN** the answer says the run was left by an earlier Hub and has been recorded as interrupted
- **AND** the run is recorded as interrupted
- **AND** its input is handed back to the queue as at a restart
- **AND** the agent accepts its next turn without a restart

#### Scenario: A surviving process is ended before the run is released

- **GIVEN** such a run whose recorded process is still alive
- **WHEN** the operator stops that agent
- **THEN** that process is ended before the run is recorded as interrupted

#### Scenario: A process that cannot be ended leaves the run as it was

- **WHEN** ending the surviving process fails
- **THEN** the stop is refused with the reason
- **AND** the run is still recorded as running

#### Scenario: This process's own unregistered run is still refused

- **GIVEN** a run this Hub process started a moment ago and has not yet registered
- **WHEN** the operator stops that agent
- **THEN** the stop is refused as not yet stoppable, as before

#### Scenario: The busy reason names the way out

- **GIVEN** a run left running by an earlier Hub process
- **WHEN** a turn for that agent is triggered or queued
- **THEN** the reason given says the run was left by an earlier Hub and that stopping the agent
  clears it
