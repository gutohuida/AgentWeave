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

A rejection SHALL carry a reason.

A refusal from the Hub SHALL be shown beside the piece it refused, in the Hub's words.

A decision SHALL be announced to every open view of the project, so coverage and the task board
reflect it without a reload.

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
