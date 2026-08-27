## MODIFIED Requirements

### Requirement: Title generation is a project setting, off by default

A project SHALL carry a setting selecting how conversation titles are produced: truncation of the
first message (the default), or generation by a model. This setting, and the runner used to produce
a generated title, SHALL be presented as a control the operator can change from the project's
settings surface — not reachable only by a direct API call or by editing the stored project row.

When generation is selected, the title SHALL be produced by a one-shot run of a runner already
configured for that project. That run MUST NOT be bound to the conversation being titled, MUST NOT
resume any provider session, and MUST NOT appear in any conversation timeline. Generation SHALL run
after the agent's first response has been recorded, and SHALL replace the truncated title only when
the operator has not set one.

A failed or timed-out generation SHALL leave the truncated title in place and MUST NOT fail the
conversation or the agent's run.

#### Scenario: Truncation is the default

- **WHEN** a project is created and its title setting has never been changed
- **THEN** titles are produced by truncation
- **AND** no model run is spawned for titling

#### Scenario: The operator can turn generation on from settings

- **WHEN** the operator opens the project's settings surface
- **THEN** a control is present that lets the operator select generation instead of truncation
- **AND** a control is present that lets the operator choose which configured runner produces the
  title

#### Scenario: Generation replaces a truncated title

- **WHEN** title generation is enabled and an agent's first response has been recorded
- **THEN** a one-shot titling run is spawned that is bound to no conversation
- **AND** the conversation's title is replaced with the generated title

#### Scenario: A titling run is invisible in the conversation

- **WHEN** a titling run completes
- **THEN** the conversation's timeline contains no entry for it
- **AND** the agent's context usage is unchanged by it

#### Scenario: A failed generation is not fatal

- **WHEN** a titling run fails or exceeds its time limit
- **THEN** the conversation keeps its truncated title
- **AND** the agent's own run is unaffected
