## MODIFIED Requirements

### Requirement: The queue-routing contract binds peer delivery to the sender's conversation

A peer message that names no recipient conversation SHALL be delivered to the recipient conversation
bound to the sending conversation's **line of work**, creating that binding on first use.

This capability already requires that *"an outbound peer message SHALL carry its sender conversation,
and its recipient queue entry SHALL carry the recipient conversation selected by the queue-routing
contract"*, but the queue-routing contract is defined nowhere. This requirement defines it.

The binding is keyed on the sending conversation and the recipient agent. It is durable: every
later message from the same sending conversation to the same recipient reaches the same recipient
conversation.

A conversation's **line of work** is itself together with every conversation it succeeds or is
succeeded by through checkpoint cutover. Matching on the line rather than on a single conversation
identifier is what keeps a correspondent reaching the same thread after either side has been cut
over; a cutover replaces the identifier an existing binding was written against, so an identifier
match alone silently opens a new thread at the handover.

Delivery MUST NOT be selected by recency. Omitting a recipient conversation is the ordinary path,
because a sender does not hold the recipient's conversation identifiers, so a recency rule governs
almost all peer traffic rather than an exceptional case. Observed consequence: three messages of one
exchange between two agents were delivered into three unrelated conversations of the recipient, one
of them titled for an unrelated file-creation task.

A recipient conversation created by this contract carries `origin: peer`.

#### Scenario: A first message binds a recipient conversation

- **WHEN** an agent sends a peer message from a conversation that has no binding to that recipient
- **THEN** a recipient conversation is created and bound to the sending conversation
- **AND** the queue entry carries that recipient conversation

#### Scenario: Later messages from the same conversation reach the same thread

- **WHEN** the same sending conversation sends another message to the same recipient
- **THEN** the queue entry carries the previously bound recipient conversation
- **AND** no further recipient conversation is created

#### Scenario: Separate sending conversations reach separate threads

- **WHEN** one agent sends peer messages to the same recipient from two different conversations
- **THEN** each is delivered to a different recipient conversation
- **AND** neither is selected by which conversation the recipient touched most recently

#### Scenario: The recipient's unrelated activity does not change delivery

- **WHEN** the recipient becomes active in a conversation unrelated to the binding
- **AND** the sender then sends another message from the bound sending conversation
- **THEN** delivery still reaches the bound recipient conversation

#### Scenario: The sender's own cutover does not open a new recipient thread

- **WHEN** a sending conversation bound to a recipient thread is cut over to a successor
- **AND** the agent sends a further message to that recipient from the successor
- **THEN** delivery reaches the already-bound recipient conversation
- **AND** no further recipient conversation is created

## ADDED Requirements

### Requirement: A reply continues the conversation it is replying to

When a peer message names no recipient conversation and no binding resolves forward, delivery SHALL
resolve the sending conversation's own binding in reverse: if the sending conversation is bound to a
conversation whose owning agent is the recipient, the message SHALL be delivered into that
conversation's line of work rather than into a newly created conversation.

Delivery resolves in a fixed order — an explicitly named conversation, then the forward binding,
then this reverse rule, then creating a conversation. The forward binding is tried first so that
every delivery that resolves today resolves identically; the reverse rule SHALL only apply where a
conversation would otherwise have been created.

Without this rule the binding is one-directional and a reply cannot find the thread it answers.
Observed consequence: three messages between two agents produced three conversations, and a later
exchange in the same session produced three more.

#### Scenario: A reply reaches the thread it is answering

- **WHEN** an agent receives a peer message into a bound conversation
- **AND** replies to the sender from that conversation, naming no recipient conversation
- **THEN** the reply is delivered into the sending agent's original conversation
- **AND** no conversation is created

#### Scenario: An exchange settles into one thread per participant

- **WHEN** two agents exchange several messages, each replying from the conversation it received in
- **THEN** every message after the first reaches an existing conversation
- **AND** exactly two conversations exist for the exchange

#### Scenario: A reply to a third agent does not continue an unrelated thread

- **WHEN** an agent receives a message from a first agent into a bound conversation
- **AND** sends a message to a second agent from that conversation
- **THEN** the reverse rule does not apply, because the bound conversation is not owned by the
  recipient
- **AND** a conversation is created for the second agent, bound to the sending conversation

#### Scenario: A reply continues into an operator-origin conversation

- **WHEN** an agent is asked something in a conversation the operator started
- **AND** delegates to a second agent, which replies naming no recipient conversation
- **THEN** the reply is delivered into that operator-origin conversation
- **AND** the entry records the second agent as its originating agent

#### Scenario: Continuation survives the replying side's cutover

- **WHEN** the conversation a reply would continue into has been cut over to a successor
- **THEN** the reply is delivered into the newest open conversation of that line of work
- **AND** no conversation is created

#### Scenario: A closed line of work does not capture a reply

- **WHEN** the conversation a reply would continue into is archived and has no open successor
- **THEN** the reverse rule does not resolve
- **AND** a conversation is created, bound to the sending conversation

### Requirement: An agent can start a new thread deliberately

The outbound message surface SHALL accept an explicit request to start a new recipient conversation,
defaulting to continuing. When the request is made, delivery SHALL create a conversation bound to
the sending conversation without consulting either the forward or the reverse binding, and later
messages on that line SHALL reach the newly created conversation.

A new thread otherwise starts only at a checkpoint cutover. Without an explicit request there is no
way for an agent to separate a genuinely new line of work from the one it is already holding, which
is the only legitimate reason to open a thread outside a cutover.

Requesting a new thread while also naming a recipient conversation SHALL be refused. Naming a
conversation selects an existing thread and requesting a new one creates one; honouring either
silently would discard a caller's stated intent.

#### Scenario: An explicit request creates a thread

- **WHEN** an agent sends a peer message asking for a new thread
- **AND** a binding to that recipient already exists
- **THEN** a conversation is created and bound to the sending conversation
- **AND** the message is delivered into it rather than into the previously bound conversation

#### Scenario: The new thread becomes the bound one

- **WHEN** an agent has started a new thread with a recipient
- **AND** sends a further message to that recipient from the same conversation, without asking again
- **THEN** delivery reaches the most recently created conversation
- **AND** no conversation is created

#### Scenario: Continuing is the default

- **WHEN** an agent sends a peer message without asking for a new thread
- **THEN** delivery resolves by binding, forward then reverse
- **AND** a conversation is created only when neither resolves

#### Scenario: Naming a conversation and asking for a new one is refused

- **WHEN** an agent sends a peer message that both names a recipient conversation and asks for a new
  thread
- **THEN** the message is refused
- **AND** no conversation is created and no message is delivered
