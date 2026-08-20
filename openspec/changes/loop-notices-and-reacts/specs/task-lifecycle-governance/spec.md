## ADDED Requirements

### Requirement: Every task status is classified into exactly one lifecycle band

The Hub SHALL classify every task status the transition machine defines into exactly one lifecycle
band, and SHALL fail to start when a status is classified into none or into more than one.

A status is defined by the transition machine when it appears as an origin or a destination in the
project's task transition map. The classification SHALL be checked against that map rather than
against a hand-maintained list of statuses.

#### Scenario: Every defined status has a band

- **WHEN** the set of statuses in the transition map is compared against the classification
- **THEN** every status appears in exactly one band

#### Scenario: An unclassified status is refused at startup

- **WHEN** a status exists in the transition map and is absent from the classification
- **THEN** the Hub fails to start, naming the unclassified status

#### Scenario: A doubly-classified status is refused at startup

- **WHEN** a status appears in more than one band
- **THEN** the Hub fails to start, naming the status and the bands

### Requirement: Status sets are derived from the classification, not listed independently

Any set of task statuses used to answer whether a task is live, claimable, terminal or active SHALL
be derived from the lifecycle classification rather than enumerated at its point of use.

Deriving these sets SHALL NOT change which statuses any of them contains. Each set SHALL contain
exactly the statuses it contained before being derived.

#### Scenario: A derived set matches what it replaced

- **WHEN** a status set is derived from the classification
- **THEN** its members are identical to the members it was defined with beforehand

#### Scenario: Two sets that answer the same question are one set

- **WHEN** two call sites need the same classification of task statuses
- **THEN** they read the same derived set rather than each defining one

#### Scenario: A new status reaches every derived set

- **WHEN** a status is added to the transition map and classified into a band
- **THEN** every derived set that includes that band includes the new status, with no further edits
