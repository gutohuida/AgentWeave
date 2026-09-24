## ADDED Requirements

### Requirement: The screen that says evidence awaits a decision can take it

Where the operator's coverage view reports that a requirement's evidence awaits a decision, the same view SHALL let the operator read each piece of that evidence and accept or reject it.

A screen that tells the operator a judgement is theirs and offers no way to make it leaves the
decision to a direct HTTP client, and accepted evidence is what approval merges.

Each piece SHALL be shown with what the operator needs to judge it: its summary, who recorded it,
its locator, the commit and branch its footprint names, the task it came from, its state, and for a
decided piece the latest decision's reason. Pieces SHALL be listed in the order the Hub records
them, with the most recently recorded marked. The mark SHALL NOT claim that piece is the one a
merge takes, because a merge is decided per task and per line of work, not per requirement.

Where accepting a piece can merge its commit into the main branch, the piece SHALL say so beside the
accept action, before the operator takes it: accepting evidence merges the work of an approved task
that was waiting for it, and a decision that can change the main branch must not look like a label.

A rejection SHALL carry a reason.

A refusal from the Hub SHALL be shown beside the piece it refused, in the Hub's words.

A decision SHALL be announced to every open view of the project, so coverage and the task board
reflect it without a reload. When a run that recorded evidence ends, that SHALL be announced too,
after the Hub has stopped counting the run as live, so a piece shown as still being recorded
becomes decidable without a reload.

#### Scenario: An awaiting piece can be accepted from the coverage view

- **WHEN** the operator opens a requirement in the coverage view whose evidence awaits a decision
- **THEN** each piece is listed with its summary, recorder, commit and branch
- **AND** accepting one records the operator's decision and the requirement's coverage updates

#### Scenario: A rejection needs a reason

- **WHEN** the operator rejects a piece without giving a reason
- **THEN** the rejection is not sent

#### Scenario: A refused decision says why

- **WHEN** the Hub refuses a decision
- **THEN** the Hub's sentence is shown beside that piece and its state is unchanged

#### Scenario: Another open view learns of the decision

- **WHEN** a piece of evidence is decided by the operator or by a granted agent
- **THEN** every open view of that project's coverage refreshes

#### Scenario: Accept says it may merge into main

- **WHEN** a piece awaiting a decision names a commit
- **THEN** the view states beside Accept that accepting may merge that commit into the main branch for an approved task waiting on it

#### Scenario: A piece still being recorded becomes decidable when its run ends

- **WHEN** the operator is viewing a piece shown as still being recorded, and the run that recorded it ends
- **THEN** the view refreshes without a reload and the piece can be decided
