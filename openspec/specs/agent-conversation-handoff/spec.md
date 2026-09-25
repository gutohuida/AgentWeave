# agent-conversation-handoff Specification

## Purpose

Durable conversation transitions from the agent conversation workspace: preserve the current
AgentWeave conversation in a checkpoint, create one successor conversation, resume from the
checkpoint, and then continue that successor conversation normally. Conversation identity is
AgentWeave's own `conversation_id`, allocated before any provider process starts; the provider
session is nullable continuation data beneath it, never the operator-facing identity a handoff
transitions between.
## Requirements
### Requirement: Agent Output distinguishes continuation, fresh start, and handoff

The conversation workspace MUST present existing AgentWeave conversations as resumable choices, a
`New conversation (start fresh)` choice that deliberately creates a new unbound conversation, and a
`Handoff` action that produces a checkpoint before creating a successor conversation.

The prior wording described handoff as preserving context *"through a durable checkpoint"* written
by the agent. Production of the checkpoint is now the Hub's, so the action is a request rather than
an instruction relayed to the agent.

Readiness MUST reflect that a checkpoint exists and passed verification. It MUST NOT be derived from
the agent's run ending, which reported success for a run that produced nothing and returned a
question to the operator.

The normal picker and continuity controls MUST use `conversation_id` and MUST NOT use provider
session IDs as conversation labels or values. The agent-detail header MUST NOT present the legacy
`Compact` and `Reset` actions as primary conversation controls.

#### Scenario: Existing conversation is selected

- **WHEN** the user selects an existing conversation and sends a message
- **THEN** the trigger includes its exact `conversation_id`
- **AND** the server derives provider continuation from that conversation's binding

#### Scenario: User starts fresh without a handoff

- **WHEN** the user selects `New conversation (start fresh)` and sends a message
- **THEN** the trigger omits `conversation_id` so the server creates one synchronously
- **AND** no checkpoint is delivered into it

#### Scenario: Readiness follows the checkpoint, not the run

- **WHEN** a run ends without a verified checkpoint having been produced
- **THEN** the handoff is not reported as ready

#### Scenario: Legacy context actions are absent

- **WHEN** the agent conversation renders
- **THEN** `Compact` and `Reset` buttons do not appear in its primary header
- **AND** durable transitions are initiated through `Handoff`

### Requirement: Handoff checkpoints the selected conversation

The `Handoff` action MUST cause the Hub to produce a checkpoint for the selected conversation, and
MUST NOT depend on the agent invoking a checkpoint workflow of its own.

The prior wording required the action to *"append a checkpoint request"* instructing the agent to
*"invoke its checkpoint workflow with reason `pre_handoff`"* and preserve state *"in the configured
durable checkpoint location"*. No such workflow is installed into any project, and the location lies
outside the agent's own working directory, so the instruction was unsatisfiable on both counts.
Where an artifact appeared at all it came from a skill belonging to the operator's environment
rather than to AgentWeave.

The content and verification of the checkpoint are governed by `conversation-checkpoint`. This
requirement governs only the action that requests one.

The action MAY request brief notes from the agent, but the checkpoint MUST be produced whether or
not the agent responds.

#### Scenario: User requests a handoff

- **WHEN** an automatically managed agent has an existing conversation selected
- **AND** the user activates `Handoff`
- **THEN** the Hub produces a checkpoint for that conversation
- **AND** the workspace is armed to create one successor conversation

#### Scenario: Handoff is being prepared

- **WHEN** the checkpoint is being produced
- **THEN** the UI indicates that the handoff is being prepared
- **AND** handoff controls remain disabled until it settles
- **AND** unrelated running-state logic does not disable ordinary queued composer input

#### Scenario: The agent does not cooperate

- **WHEN** the agent is asked for notes and does not answer, refuses, or returns unusable notes
- **THEN** the checkpoint is still produced
- **AND** the handoff is not reported as failed for that reason alone

#### Scenario: Agent cannot be triggered automatically

- **WHEN** the agent's runner is configured as manual
- **THEN** the `Handoff` action is disabled
- **AND** the UI explains that handoff requires an automatically managed runner

### Requirement: The next conversation resumes the durable handoff

After a handoff is ready, the next user message MUST create exactly one unbound successor
conversation, and the Hub MUST deliver the checkpoint into it rather than instructing the successor
to locate it.

The prior wording required the successor's prompt to instruct the new provider session to *"read the
newest checkpoint for its agent"* at a stated path. Both paths named were wrong: neither existed,
and one of the two runtimes recovered only by abandoning the instruction and searching its whole
working directory. The other appeared to succeed only because it had earlier written to the same
incorrect location, so two errors composed into a working round trip.

The checkpoint is delivered as conversation-scoped queued input. It MUST NOT be delivered through
the agent-scoped canonical context, which writes one file per agent and therefore cannot carry
something belonging to one successor conversation.

The successor's prompt MUST NOT instruct the agent to locate a checkpoint on the filesystem.

#### Scenario: First message after handoff

- **WHEN** the handoff is ready and the user sends the next message
- **THEN** the trigger omits `conversation_id` and returns the new successor `conversation_id`
- **AND** the checkpoint is delivered into that successor as queued input
- **AND** the user's original request remains present

#### Scenario: The successor is not asked to find anything

- **WHEN** the successor conversation receives the checkpoint
- **THEN** no instruction to read a checkpoint from a filesystem path is included

#### Scenario: Successor conversation identity is immediate

- **WHEN** the fresh trigger is accepted
- **THEN** the selector binds to its returned `conversation_id` without waiting for output
- **AND** the UI indicates that it is continuing the successor conversation

#### Scenario: Messages after the resumed handoff

- **WHEN** the user sends another message in the successor conversation
- **THEN** the trigger carries that successor `conversation_id`
- **AND** the checkpoint is not delivered again
- **AND** no further conversation is created

### Requirement: Conversation transition state is visible and scoped to the agent

The conversation workspace MUST visibly distinguish continuing an existing conversation, preparing
a handoff, a ready handoff, starting a fresh conversation, and continuing its successor. Transient
handoff state MUST be cleared when the selected agent changes or the user manually changes the
conversation selection. Provider-binding latency MUST NOT be represented as a pending application
identity state because `conversation_id` is already available.

#### Scenario: User changes agents

- **WHEN** the user selects a different agent
- **THEN** handoff state from the previous agent MUST be cleared
- **AND** the new agent's most recently active conversation MUST be selected when available

#### Scenario: User manually changes conversation

- **WHEN** the user changes the conversation selection during an idle state
- **THEN** any prepared handoff MUST be cancelled
- **AND** the continuity indicator MUST describe the newly selected conversation

### Requirement: A cutover carries the line of work to the successor in both directions

A successor conversation opened by checkpoint cutover SHALL belong to the same line of work as its
predecessor, and that membership SHALL be durably recorded on the conversation rather than inferred
from checkpoint history or from a derived title.

Peer delivery is resolved against a line of work, not a conversation identifier, so that
correspondents keep reaching the same thread across a handover. Today a cutover copies the
predecessor's inbound binding to the successor, which preserves delivery *into* the successor, and
records nothing that preserves delivery *out of* it: once an agent sends from the successor, no
recipient thread is bound to the identifier it is sending from, and a new thread is opened at the
handover. Both directions SHALL survive the cutover.

The recorded membership MUST be resolvable without reading checkpoint records, because a
conversation whose checkpoints have been pruned still has correspondents.

A conversation that is not a successor SHALL belong to a line of work containing only itself, so
that every conversation has one and delivery has no special case for the first conversation in a
chain.

#### Scenario: A successor shares its predecessor's line of work

- **WHEN** a checkpoint cutover opens a successor conversation
- **THEN** the successor records the same line of work as the predecessor
- **AND** the predecessor's recorded line of work is unchanged

#### Scenario: An agent sending from a successor reaches its established correspondents

- **WHEN** a conversation bound to a recipient thread is cut over
- **AND** the agent sends a peer message to that recipient from the successor
- **THEN** delivery reaches the already-bound recipient conversation
- **AND** no conversation is created

#### Scenario: A correspondent replying after a cutover reaches the successor

- **WHEN** an agent replies into a line of work whose conversation has been cut over
- **THEN** the reply is delivered into the newest open conversation of that line
- **AND** the archived predecessor receives nothing

#### Scenario: Membership does not depend on checkpoint history

- **WHEN** the checkpoint records associated with a cutover are no longer present
- **THEN** the successor's line of work is still resolvable from the conversation itself

#### Scenario: A conversation that never had a predecessor still has a line of work

- **WHEN** a conversation is created by any means other than a cutover
- **THEN** it records a line of work containing only itself

### Requirement: A conversation is handed over at most once, and its checkpoint records where it went

The Hub SHALL record on a checkpoint the successor conversation it was cut over to, in the same transaction that creates that successor, and SHALL refuse any cutover that would give a conversation a second successor, whatever the timing or order of the requests.

A cutover gives the successor the checkpoint as queued input. A second successor of the same
conversation receives the same work again and spends a turn rediscovering that it is done. It also
forks a line of work that the lineage requirement says is linear. The refusal SHALL NOT depend on
the predecessor's lifecycle: reopening an archived conversation is always permitted, so a guard
that reads the lifecycle can be erased by the route the refusal itself recommends.

The guarantee SHALL hold when two requests arrive at the same instant. It SHALL be enforced by the
database, as a claim on the checkpoint and a uniqueness constraint over handed-over checkpoints per
conversation, and not by reading state and then writing it. A refused request SHALL leave no
successor conversation and no queued entry behind.

The automatic checkpoint trigger SHALL NOT take a billed step for an open conversation that has
already been handed over, since no cutover of it can succeed: it SHALL NOT request notes, raise the
warning that a checkpoint is due, or generate a checkpoint. The final warning owed to a
conversation whose warning was dismissed costs nothing, and SHALL still be raised as the
requirement *Crossing the threshold warns before it spends* states.

A refusal SHALL name the successor that holds the work. A conversation that was archived by hand
and was never handed over MAY still be refused until it is reopened, and only that refusal SHALL
advise reopening it.

#### Scenario: A spent checkpoint names its successor

- **WHEN** a checkpoint has been cut over to a successor
- **THEN** the checkpoint records that successor's conversation id
- **AND** the operator's checkpoint listing reports it

#### Scenario: Reopening the predecessor does not re-arm its checkpoint

- **WHEN** a conversation is cut over, then reopened
- **AND** the same checkpoint is cut over again
- **THEN** the cutover is refused, naming the existing successor
- **AND** exactly one successor conversation and one checkpoint entry exist

#### Scenario: Two simultaneous presses produce one successor

- **WHEN** two cutover requests for the same ready checkpoint are processed concurrently
- **THEN** exactly one succeeds
- **AND** the other is refused, naming the successor the first created
- **AND** exactly one successor conversation and one checkpoint entry exist

#### Scenario: A second checkpoint cannot hand the same conversation over again

- **WHEN** a conversation has been cut over using one checkpoint
- **AND** it is reopened and a cutover is requested using a different checkpoint of the same conversation
- **THEN** the cutover is refused, naming the existing successor
- **AND** no second successor exists

#### Scenario: The trigger spends nothing on a conversation already handed over

- **WHEN** a conversation has been cut over and then reopened
- **AND** work in it crosses the checkpoint threshold under automatic checkpointing
- **THEN** no checkpoint is generated and no model is called
- **AND** no second successor exists

#### Scenario: A handed-over conversation still receives its final warning

- **WHEN** a conversation has been cut over and then reopened
- **AND** its checkpoint warning had been dismissed
- **AND** its context approaches the point at which the provider will compact it
- **THEN** it is given the final warning
- **AND** no checkpoint is generated and no model is called

#### Scenario: A reopened handed-over conversation is not warned that a checkpoint is due

- **WHEN** a conversation has been cut over and then reopened
- **AND** work in it crosses the checkpoint threshold under a configuration that involves the operator
- **THEN** no notes are requested and no checkpoint is reported as due
- **AND** no checkpoint is generated

#### Scenario: A conversation archived by hand is told to reopen first

- **WHEN** a conversation that was never handed over has been archived by hand
- **AND** a cutover is requested for it
- **THEN** the cutover is refused with advice to reopen it
- **AND** after it is reopened, the cutover succeeds

