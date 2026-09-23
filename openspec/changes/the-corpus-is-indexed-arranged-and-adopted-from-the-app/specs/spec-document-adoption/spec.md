## ADDED Requirements

### Requirement: An untracked document is adoptable from where it is listed

Where the operator's document browser lists a specification file that exists on disk and has no document record, the interface SHALL offer to adopt it there, and SHALL offer to adopt every such file at once.

A clone, a restore or a second machine produces a corpus whose files predate its records. The browser
already shows those files; showing them without a way to track them leaves the operator looking at
documents the Hub cannot move through any phase.

Each refusal or skip SHALL be shown with the reason the Hub gave, including the disagreements an
already-tracked path reports, and a corpus-wide adoption SHALL show its discovery diagnostics, so a
truncated sweep is not presented as a complete one.

#### Scenario: One untracked document is adopted from its row

- **WHEN** the browser lists a file with no document record
- **AND** the operator adopts it from that row
- **THEN** a document record exists for it
- **AND** the row no longer offers adoption

#### Scenario: Every untracked document is adopted at once

- **WHEN** several listed files have no document record
- **AND** the operator adopts them all
- **THEN** each adoptable file gains a record
- **AND** each skipped file is shown with its reason
