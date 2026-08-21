## MODIFIED Requirements

### Requirement: A loop that is still running cannot be archived

The Hub SHALL refuse to archive a loop that has neither completed nor stopped, so that archiving can
never conceal work that is still firing.

Archiving a loop's job SHALL retire the loop with it. A loop has exactly one job, and an archived job
never fires — so a loop whose job is archived is not firing and SHALL NOT be treated as though it
were. Retiring it in that one operation is what satisfies the rule above, not an exception to it.

Measured 2026-08-21: archiving a job left its loop active and listed, and archiving that loop was
then refused as *"still running"* although nothing could fire it. Clearing it took setting a stop
time in the past, firing once so the stop condition was evaluated, and only then archiving — three
steps, none of them discoverable from the refusal.

#### Scenario: Archiving a running loop is refused

- **GIVEN** a loop that is still enabled and firing
- **WHEN** the operator attempts to archive it
- **THEN** the request is refused, stating that it must be stopped or complete first

#### Scenario: A stopped loop can be archived

- **GIVEN** a loop that has stopped or completed
- **WHEN** the operator archives it
- **THEN** the loop is archived and no longer appears in default listings

#### Scenario: Archiving a job retires its loop

- **GIVEN** an enabled loop whose job has not been archived
- **WHEN** the operator archives that job
- **THEN** the loop is retired in the same operation
- **AND** it no longer appears in default loop listings
- **AND** the operator is not required to stop it first

#### Scenario: A loop retired with its job keeps everything

- **GIVEN** a loop with a queue history, firings, and a purpose
- **WHEN** its job is archived
- **THEN** its purpose, queue history, firings, and stop state are all still retrievable
