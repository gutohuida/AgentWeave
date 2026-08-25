## ADDED Requirements

### Requirement: A flow that stops when its queue empties SHALL NOT fire against an empty queue

A firing SHALL NOT spawn a turn when the loop declares that it stops once its queue empties and no
claimable work remains; the loop SHALL end instead.

Measured on 2026-08-25: a flow with an empty queue and that flag set fired a real turn, on a real
model, against nothing to do. The failure mode is not "nothing happens" — it is "an agent is spawned
with nothing to do", on a cron, indefinitely. The declared intent is already recorded; it SHALL be
honoured before the spawn rather than after it.

#### Scenario: An empty queue under the stop condition
- **WHEN** a loop declaring `stop_when_queue_empties` fires and no task is claimable
- **THEN** no turn SHALL be spawned
- **AND** the loop SHALL end, recording why

#### Scenario: An empty queue without the stop condition
- **WHEN** a loop not declaring that stop condition fires and no task is claimable
- **THEN** the existing stall reporting SHALL apply unchanged

#### Scenario: A queue with claimable work
- **WHEN** a loop declaring the stop condition fires and a task is claimable
- **THEN** the turn SHALL be spawned as before
