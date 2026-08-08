# agent-capability-plane

## Purpose

One least-privilege, run-authenticated application contract for agent-caused effects and scoped
reads, shared identically by HTTP and MCP. Established by `openspec/changes/agent-capability-plane`.

**Reconciled 2026-08-07.** The equal-capability requirement below previously named "ordinary
commands" as a third adapter. No such command exists — the CLI was reduced to local instance
management — and `openspec/explorations/2026-08-02-product-direction.md` states that the reduced CLI
is not an agent capability adapter.

## Requirements

### Requirement: A live run credential is the only agent authentication

The system SHALL mint an unguessable credential for each Hub-owned run, store only a non-reversible
digest, and accept the credential only while that exact run is active. Authentication SHALL derive
the project, agent, and run from the matched row. The credential MUST NOT be exposed in output,
events, command arguments, or API responses.

#### Scenario: Active run resolves to one actor

- **WHEN** an agent request carries a valid credential for a running run
- **THEN** the server derives that run's project and agent
- **AND** the request supplies no actor identity

#### Scenario: Terminal run is revoked

- **WHEN** a credential belongs to a completed, failed, stopped, or interrupted run
- **THEN** the agent request is refused

#### Scenario: Credentials cannot cross privilege planes

- **WHEN** a project API key is presented to the agent API or a run credential is presented to an
  operator API
- **THEN** authentication is refused

### Requirement: The agent API is a least-privilege allowlist

The agent application API SHALL expose only peer messaging, shared task-ledger reads/writes,
operator questions and their answers, governed agent requests, and governed scheduled-work
mutations. It MUST NOT expose inbound queue/history, roster, project settings, agent configuration,
charter/scope, credentials, or other operator capabilities.

#### Scenario: Outbound intent is available

- **WHEN** an authenticated run messages a peer, works with the shared task ledger, or asks the
  operator a question
- **THEN** the permitted effect or read succeeds under the same validation as the operator system

#### Scenario: Coordination and configuration are absent

- **WHEN** an authenticated run tries to read undelivered input or alter project/agent configuration
- **THEN** no agent API operation provides that capability

#### Scenario: New operator APIs are denied by default

- **WHEN** an operator-only route is added without an explicit agent capability
- **THEN** a run credential cannot call it

### Requirement: Actor identity cannot be supplied or overridden

Agent-action payloads SHALL contain no project, agent, sender, assigner, requester, or run identity
field. Every affected service SHALL use only the authenticated actor. Caller headers or extra body
fields MUST NOT change attribution.

#### Scenario: Impersonation is structurally unavailable

- **WHEN** an agent constructs a valid action request
- **THEN** there is no supported field by which it can select another actor

#### Scenario: Override attempts do not change the actor

- **WHEN** a caller adds identity-like headers or unknown body fields
- **THEN** the effect is either rejected as invalid or remains attributed to the authenticated run

### Requirement: Every agent-caused effect retains run attribution

The system SHALL ensure every message, task creation/update, question, scheduled-work mutation, and
agent request caused by the agent plane durably identifies the responsible agent and run. Event logs MUST NOT be the
only source of that attribution. Historical/operator effects MAY remain unattributed where no run
exists.

#### Scenario: Persisted effect names its run

- **WHEN** an authenticated run causes an allowed effect
- **THEN** the resulting durable record identifies that run
- **AND** its project and agent are consistent with the authenticated actor

#### Scenario: Updates retain the latest responsible run

- **WHEN** an authenticated run updates a mutable task or job
- **THEN** the record identifies the run responsible for that update

### Requirement: HTTP and MCP access have equal capability

Direct HTTP SHALL be the application contract. MCP SHALL be a thin adapter over that contract with
the same operations, validation, governance, attribution, and typed failure meaning. An adapter MUST
NOT duplicate queue, budget, identity, or lifecycle business rules and MUST NOT silently convert
failures into empty or successful results.

Two adapters exist rather than one because MCP is convenient where it is permitted and some
environments forbid MCP servers while still allowing ordinary local API calls. The command-line
interface is **not** one of them: it manages the local application instance and carries no agent
capabilities.

#### Scenario: One operation has one persisted result

- **WHEN** equivalent valid actions are performed through HTTP and through MCP
- **THEN** their persisted effects have equivalent content and attribution

#### Scenario: Failure meaning survives adaptation

- **WHEN** the application API returns validation, denied, not-found, or conflict failure
- **THEN** MCP callers receive the same failure meaning

#### Scenario: The CLI offers no agent capability

- **WHEN** an agent attempts to affect shared state through a command-line invocation
- **THEN** no such command exists

#### Scenario: No full project credential is present

- **WHEN** the Hub starts an agent with either adapter available
- **THEN** the process receives its run credential
- **AND** it does not receive a project/operator API key

### Requirement: A turn that ends on an unasked question is surfaced to the operator

The system SHALL durably record, and show the operator, any run that completes having produced a
trailing question without opening a question of record.

An agent that ends a turn on an unanswered question has stopped working and is waiting for an answer
that cannot arrive, because nothing was ever asked. From the operator's side this is
indistinguishable from a completed turn. Detection is the only available remedy: no provider
protocol permits requiring that a turn end through a particular tool.

#### Scenario: A completed run ends in a question and opened no question row

- **WHEN** a run completes, its final assistant text ends in a question, and the run opened no
  question of record
- **THEN** a pending record of the unasked question is stored, carrying the agent, the run, the
  conversation and the question text
- **AND** an event is broadcast so the operator's view updates without a reload

#### Scenario: The run asked properly

- **WHEN** a run completes having opened a question of record
- **THEN** no unasked-question record is created, regardless of how its final text ends

#### Scenario: The run did not end in a question

- **WHEN** a run completes and its final assistant text does not end in a question
- **THEN** no unasked-question record is created

#### Scenario: The turn is about to continue

- **WHEN** a run completes ending in a question and the agent still has queued input
- **THEN** no unasked-question record is created, because the next turn starts on its own

#### Scenario: The run did not complete

- **WHEN** a run ends in any status other than completed
- **THEN** no unasked-question record is created

### Requirement: The operator can convert an unasked question into a real one

The system SHALL offer the operator, for each pending unasked question, an action that re-prompts the
agent to ask that same question through the question tool, and an action that dismisses it.

Answering the detected question directly is not possible: the turn has ended and no tool call is
waiting on a value. Re-prompting is the only action that restores the intended flow.

#### Scenario: The operator re-prompts the agent

- **WHEN** the operator chooses to have the question asked properly
- **THEN** the record moves out of pending
- **AND** the agent is triggered with an instruction naming that question and requiring it be asked
  through the question tool with its required structure

#### Scenario: The operator dismisses it

- **WHEN** the operator dismisses a pending unasked question
- **THEN** the record moves out of pending and the operator is not shown it again

#### Scenario: A record is acted on twice

- **WHEN** an action is taken on a record that is no longer pending
- **THEN** the request is refused rather than silently repeated

### Requirement: Operator-facing severity values are the ones the operator's view understands

Events persisted for the operator's attention SHALL use the severity vocabulary the operator's views
filter and style by.

A severity that no view recognises is worse than none: the row renders unmarked and is hidden by the
filter intended to reveal it, so the events most needing attention are the ones least likely to be
seen.

#### Scenario: A refused action is recorded

- **WHEN** the system records that an agent's action was refused
- **THEN** the stored severity is one the operator's activity view filters and styles by

### Requirement: An agent can ask several questions in one turn

The question tool SHALL accept a list of questions and hold the turn until every one has been
answered or the wait expires.

An agent needing several decisions before it can start would otherwise block its turn once per
question and interrupt the operator once per question, or decide some of them itself. Asking together
is one interruption and one wait.

#### Scenario: A batch is asked and answered

- **WHEN** an agent asks several questions in one call
- **AND** the operator answers all of them
- **THEN** the tool returns every answer, each identified with the question it answers

#### Scenario: The wait expires with a batch partly answered

- **WHEN** the wait expires before every question in a batch is answered
- **THEN** the tool returns without an answer for the unanswered ones and states plainly that they
  went unanswered

#### Scenario: A single question is still a single question

- **WHEN** an agent asks one question
- **THEN** it behaves exactly as an unbatched question does, with no extra step for the operator

#### Scenario: Each question keeps its required structure

- **WHEN** any question in a batch is submitted without its header, its options, or its
  multi-select flag
- **THEN** the call is rejected rather than partially accepted

### Requirement: The operator answers a batch one question at a time

The operator SHALL be shown one question of a batch at a time, told which step they are on and how
many there are, and advanced to the next once the current one is answered.

Showing a batch at once turns a conversation into a form, and a count of outstanding questions
displayed where a step count belongs misrepresents how much is left.

#### Scenario: The step counter reflects position within the batch

- **WHEN** the operator is answering a batch
- **THEN** the displayed count is their position within that batch and its total, not the number of
  questions outstanding across the project

#### Scenario: Answering advances to the next question

- **WHEN** the operator answers the question on screen and others in its batch remain
- **THEN** the next unanswered question in that batch is shown

#### Scenario: The answer is recorded against the question that was displayed

- **WHEN** the operator answers
- **THEN** the answer is recorded against the question they were shown

#### Scenario: An answer survives an interruption

- **WHEN** the operator answers part of a batch and their view is reloaded
- **THEN** the answers already given are still recorded, and the batch resumes at the first
  unanswered question

### Requirement: How long an agent waits for the operator is a per-agent setting

Each agent SHALL carry its own limit for how long it waits on a permission decision and on an answer
to a question, and an agent with no limit set SHALL use the system default.

How long a wait is reasonable depends on the agent and on whether the operator is watching. A single
compiled-in number serves neither the agent being supervised closely nor the one left running while
the operator is elsewhere.

#### Scenario: A configured wait governs the run

- **WHEN** an agent with its own waiting limits starts a run
- **THEN** that run waits for the operator for the configured time rather than the default

#### Scenario: An unconfigured agent is unchanged

- **WHEN** an agent with no waiting limits set starts a run
- **THEN** it waits for the system default, exactly as it did before the setting existed

#### Scenario: A limit outside the permitted range is refused

- **WHEN** a waiting limit is set below the minimum or above the maximum
- **THEN** the change is refused and the stored value is unchanged

#### Scenario: An unreadable setting does not break the run

- **WHEN** a run's waiting limit cannot be read or understood
- **THEN** the run uses the default rather than failing

#### Scenario: A run in flight keeps the rules it started under

- **WHEN** an agent's waiting limit is changed while one of its runs is already in progress
- **THEN** that run continues under the limit it started with

### Requirement: Durable per-agent settings are edited on the agent, not in the composer

Settings that belong to an agent rather than to one conversation SHALL be presented on the agent's
own surface, reachable from a conversation without leaving it.

The composer's controls are per-conversation and chosen at the moment of sending. Mixing durable
per-agent configuration into them would make it unclear which choices persist, and adding a third
settings location would make it unclear where to look.

#### Scenario: The operator changes a durable setting mid-conversation

- **WHEN** the operator opens the agent's settings from a conversation
- **THEN** the setting is presented there
- **AND** the conversation is not discarded or reset

#### Scenario: Per-conversation controls stay per-conversation

- **WHEN** the operator views the composer's controls
- **THEN** they offer only choices scoped to that conversation, not durable agent settings

### Requirement: A send to an archived conversation fails with a recoverable instruction

An agent's `send_message` SHALL fail when the recipient's target conversation is archived, and the
failure response MUST carry three things: that the conversation is archived, an instruction to send
to a new conversation instead, and the content the agent submitted, restated verbatim.

Restating the content is the point of the requirement, not a courtesy. A blocked send that returns
only an error forces the agent to reconstruct its own message from a context it may have already
moved past; returning the content makes the retry mechanical.

The archived conversation MUST NOT receive the message, and no inbound queue entry MUST be created
against it. The failure MUST NOT silently redirect the message to a different conversation — the
agent decides where its message goes.

#### Scenario: The failure names the cause and the remedy

- **WHEN** an agent sends a message whose recipient conversation is archived
- **THEN** the send fails
- **AND** the response states that the conversation is archived and instructs the agent to send to a new conversation

#### Scenario: The submitted content is returned

- **WHEN** a send to an archived conversation has failed
- **THEN** the response restates the content the agent submitted, verbatim

#### Scenario: Nothing is written to the archived conversation

- **WHEN** a send to an archived conversation has failed
- **THEN** that conversation has no new message and no new inbound queue entry

#### Scenario: The message is not silently rehomed

- **WHEN** a send to an archived conversation has failed
- **THEN** no other conversation has received the message

#### Scenario: The same contract holds over HTTP and MCP

- **WHEN** the send is attempted over the direct HTTP API and over the MCP adapter
- **THEN** both fail
- **AND** both carry the cause, the instruction, and the restated content
