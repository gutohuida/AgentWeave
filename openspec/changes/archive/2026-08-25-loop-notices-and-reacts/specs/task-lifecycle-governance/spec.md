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

Any set of task statuses SHALL be derived from the lifecycle classification rather than enumerated
at its point of use — including every set used to answer whether a task is live, claimable,
terminal, active, or the current item of a queue.

Deriving these sets SHALL NOT change which statuses any of them contains. Each set SHALL contain
exactly the statuses it contained before being derived.

**A derived set SHALL be defined by the question it answers, and two sets answering different
questions SHALL NOT be merged even where their members overlap.** Deriving from one classification
is a requirement about where membership comes from, never a licence to collapse distinct questions
into one set.

#### Scenario: A derived set matches what it replaced

- **WHEN** a status set is derived from the classification
- **THEN** its members are identical to the members it was defined with beforehand

#### Scenario: Two sets that answer the same question are one set

- **WHEN** two call sites need the same classification of task statuses
- **THEN** they read the same derived set rather than each defining one

#### Scenario: Two sets that answer different questions stay distinct

- **WHEN** one call site asks which statuses a firing may claim and another asks which statuses can
  be a queue's current item
- **THEN** they read different derived sets
- **AND** a status that is claimable by neither, yet is a queue's current work, appears in the
  second and not the first

#### Scenario: Deriving a set does not remove a status from a surface that showed it

- **WHEN** a set is replaced by a derivation
- **THEN** no surface that displayed a task before the change stops displaying it

#### Scenario: A new status reaches every derived set

- **WHEN** a status is added to the transition map and classified into a band
- **THEN** every derived set that includes that band includes the new status, with no further edits
