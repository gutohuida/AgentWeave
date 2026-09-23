## ADDED Requirements

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

#### Scenario: A conversation archived by hand is told to reopen first

- **WHEN** a conversation that was never handed over has been archived by hand
- **AND** a cutover is requested for it
- **THEN** the cutover is refused with advice to reopen it
- **AND** after it is reopened, the cutover succeeds
