## ADDED Requirements

### Requirement: A conversation carries a human-readable title

Every conversation SHALL carry a `title` that is readable without knowing its identifier. A
conversation's identifier MUST NOT be presented as its label on any operator surface.

A title SHALL be set when the conversation's first message is recorded, derived from that message's
text, truncated at a word boundary. A conversation that has no message yet SHALL be labelled by its
surface as new rather than by its identifier.

#### Scenario: The first message names the conversation

- **WHEN** the first message is recorded against a conversation with no title
- **THEN** the conversation's title is set from that message's text, truncated at a word boundary
- **AND** the title is returned by the conversation listing

#### Scenario: A long first message is truncated without cutting a word

- **WHEN** the first message is longer than the title limit
- **THEN** the stored title ends at a word boundary at or before the limit
- **AND** the stored title contains no partial word

#### Scenario: Identifiers are never used as labels

- **WHEN** any operator surface lists or names a conversation
- **THEN** the conversation's title is shown
- **AND** its identifier is not shown as its label

### Requirement: A conversation records where it came from

Every conversation SHALL carry an `origin` recorded at creation, drawn from a closed set:
`operator`, `peer`, `handoff`, `spec`, `job`. A conversation created for a recipient agent because
a peer agent addressed it SHALL be recorded as `peer`; a conversation created because the operator
started one SHALL be recorded as `operator`.

Origin SHALL be immutable after creation.

#### Scenario: An operator-started conversation records its origin

- **WHEN** the operator starts a conversation and sends its first message
- **THEN** the conversation's origin is `operator`

#### Scenario: A peer-created conversation records its origin

- **WHEN** an agent sends a message to a peer that has no open conversation
- **THEN** the conversation created for the recipient has origin `peer`

#### Scenario: Origin does not change

- **WHEN** a conversation is renamed, archived, or unarchived
- **THEN** its origin is unchanged

### Requirement: The operator can rename a conversation

The operator SHALL be able to set a conversation's title. A title set by the operator SHALL be
recorded as operator-set and MUST NOT be replaced by any generated title thereafter.

A rename SHALL be rejected when the submitted title is empty or exceeds the stored length.

#### Scenario: A rename is persisted and shown

- **WHEN** the operator submits a new title for a conversation
- **THEN** the conversation's title is that value
- **AND** every surface listing that conversation shows it

#### Scenario: An operator title survives title generation

- **WHEN** a conversation whose title was set by the operator becomes eligible for a generated title
- **THEN** the generated title is discarded
- **AND** the operator's title is unchanged

#### Scenario: An empty title is rejected

- **WHEN** the operator submits an empty title
- **THEN** the request is rejected with a stated reason
- **AND** the existing title is unchanged

### Requirement: Title generation is a project setting, off by default

A project SHALL carry a setting selecting how conversation titles are produced: truncation of the
first message (the default), or generation by a model.

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

### Requirement: A conversation can be archived and unarchived

The operator SHALL be able to archive a conversation, setting its lifecycle to `archived` and
recording the time. An archived conversation SHALL be excluded from the default conversation
listing and reachable through an explicit archived listing.

The operator SHALL be able to unarchive an archived conversation, returning it to `open`.

#### Scenario: Archiving hides the conversation from the default listing

- **WHEN** the operator archives a conversation
- **THEN** its lifecycle is `archived` and its archived time is recorded
- **AND** the default conversation listing for that agent no longer includes it

#### Scenario: An archived conversation remains readable

- **WHEN** the operator opens an archived conversation from the archived listing
- **THEN** its full timeline is rendered
- **AND** its entries, runs, and usage records are unchanged

#### Scenario: Unarchiving restores the conversation

- **WHEN** the operator unarchives an archived conversation
- **THEN** its lifecycle is `open`
- **AND** it appears in the default conversation listing again

### Requirement: Archiving is refused while work is outstanding

Archiving SHALL be refused, with a stated reason naming the obstruction, when the conversation has a
run that has not ended, or when it has inbound queue entries that have not been delivered.

The system MUST NOT stop a run or discard a queue entry in order to satisfy an archive request.

#### Scenario: A live run blocks archiving

- **WHEN** the operator archives a conversation whose run has not ended
- **THEN** the request is refused with a reason naming the running run
- **AND** the run continues unaffected

#### Scenario: Undelivered queue entries block archiving

- **WHEN** the operator archives a conversation holding undelivered inbound queue entries
- **THEN** the request is refused with a reason naming the undelivered entries
- **AND** the entries remain queued

#### Scenario: Archiving succeeds once work has cleared

- **WHEN** the obstructing run has ended and the entries have been delivered
- **AND** the operator archives the conversation again
- **THEN** the conversation is archived

### Requirement: An agent addressing an archived conversation is told how to recover

When an agent sends a message whose recipient conversation is archived, the send SHALL fail with a
response that states the conversation is archived, instructs the agent to send to a new
conversation, and restates the content it submitted.

The archived conversation MUST NOT receive the message, and no queue entry MUST be created against
it.

#### Scenario: The send fails with recovery instructions

- **WHEN** an agent sends a message to an archived conversation
- **THEN** the send fails
- **AND** the response states that the conversation is archived, instructs the agent to send to a new conversation, and restates the submitted content

#### Scenario: Nothing is written to the archived conversation

- **WHEN** a send to an archived conversation has failed
- **THEN** the archived conversation has no new message and no new queue entry
