## MODIFIED Requirements

### Requirement: Every agent-caused effect retains run attribution

The system SHALL ensure every message, task creation/update, question, scheduled-work mutation, and
agent request caused by the agent plane durably identifies the responsible agent and run. Event logs MUST NOT be the
only source of that attribution. Historical/operator effects MAY remain unattributed where no run
exists.

For **task status** specifically, last-writer attribution is insufficient: approval is a judgement
about work a different run performed, so a single mutable field cannot express the question of
whether author and reviewer differ. Task status attribution SHALL therefore be an append-only
sequence, one record per accepted transition, each naming its own responsible run. A materialised
"latest responsible run" MAY be retained for convenience but MUST NOT be the only durable record.

#### Scenario: Persisted effect names its run

- **WHEN** an authenticated run causes an allowed effect
- **THEN** the resulting durable record identifies that run
- **AND** its project and agent are consistent with the authenticated actor

#### Scenario: Updates retain the latest responsible run

- **WHEN** an authenticated run updates a mutable task or job
- **THEN** the record identifies the run responsible for that update

#### Scenario: Task status attribution survives a later transition

- **WHEN** one authenticated run moves a task to `completed` and a later run moves it to another
  status
- **THEN** the run responsible for the earlier transition is still identifiable
- **AND** the later transition has not overwritten it
