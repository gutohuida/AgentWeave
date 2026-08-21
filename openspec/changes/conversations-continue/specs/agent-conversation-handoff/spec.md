## ADDED Requirements

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
