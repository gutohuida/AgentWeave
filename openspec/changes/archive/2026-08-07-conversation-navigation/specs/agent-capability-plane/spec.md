## ADDED Requirements

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
