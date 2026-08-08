## ADDED Requirements

### Requirement: The queue-routing contract binds peer delivery to the sender's conversation

A peer message that names no recipient conversation SHALL be delivered to the recipient conversation
bound to the sending conversation, creating that binding on first use.

This capability already requires that *"an outbound peer message SHALL carry its sender conversation,
and its recipient queue entry SHALL carry the recipient conversation selected by the queue-routing
contract"*, but the queue-routing contract is defined nowhere. This requirement defines it.

The binding is keyed on the sending conversation and the recipient agent. It is durable: every
later message from the same sending conversation to the same recipient reaches the same recipient
conversation.

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

### Requirement: Traffic with no sending conversation binds to its sender identity

A message originating from a source that has no conversation SHALL be delivered to a recipient
conversation bound to that source's identity.

Hub-originated and scheduler-originated messages have no sending conversation, so the binding above
has no key. Binding them to the sender's identity gives one durable thread per source and recipient,
and leaves no path on which recency routing survives.

#### Scenario: System-originated messages reach a stable thread

- **WHEN** the Hub or the scheduler sends a message to an agent
- **THEN** it is delivered to the recipient conversation bound to that source
- **AND** later messages from that source reach the same conversation

### Requirement: An archived thread is handled according to who selected it

Delivery to an archived recipient conversation SHALL be refused when the sender named it, and SHALL
continue into a successor when the binding resolved it.

An agent that explicitly names an archived conversation has made an error it can correct, and is
already refused with its content returned so it need not reconstruct the message. An agent whose
message was routed to a thread the operator archived made no such choice, and refusing it would
penalise the sender for an operator action.

#### Scenario: A named archived conversation is refused

- **WHEN** a sender names a recipient conversation that is archived
- **THEN** the send is refused
- **AND** the refusal returns the message content

#### Scenario: A bound archived conversation continues into a successor

- **WHEN** the binding resolves to a recipient conversation the operator archived
- **THEN** a successor recipient conversation is created with `origin: peer`
- **AND** the binding moves to that successor
- **AND** the message is delivered rather than refused

### Requirement: Existing conversations bind on next use rather than by backfill

Peer bindings SHALL be established when a conversation next sends, and historical traffic SHALL NOT
be reassigned.

Traffic delivered under recency routing is already distributed across unrelated conversations, so
reconstructing which recipient conversation a past message "belonged" to would be a guess. Leaving
it in place keeps the record honest.

#### Scenario: A conversation with prior traffic binds on its next message

- **WHEN** a conversation that sent peer messages before this contract sends another
- **THEN** a binding is established at that point
- **AND** previously delivered messages remain in the conversations that received them
