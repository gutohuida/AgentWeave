## ADDED Requirements

### Requirement: One conversation timeline shows every exchange involving the agent

The agent conversation view SHALL present a single chronological timeline containing operator input,
the agent's own output, messages received from other agents, and messages the agent sent to other
agents.

Each entry SHALL identify its participant. The timeline MUST NOT require the operator to open a
separate inbox to see agent-to-agent traffic.

#### Scenario: Peer traffic appears inline in both directions

- **WHEN** an agent receives a message from a second agent and later sends one to a third
- **THEN** both appear in the conversation timeline in chronological position
- **AND** each identifies the other participant

#### Scenario: Operator input and agent output remain distinguishable

- **WHEN** the timeline contains operator input and agent output
- **THEN** each is visually distinct from the other and from peer traffic

### Requirement: The timeline renders typed entries, not uniform conversation bubbles

Timeline entries SHALL be typed, and each type SHALL be presented in the form that suits it.
Conversational exchange is one type among several and MUST NOT be the presentation for every entry.

At minimum the timeline SHALL distinguish conversational exchange, the agent's intermediate work,
and self-contained structured results.

#### Scenario: Work is distinguishable from conversation

- **WHEN** an agent performs intermediate work such as tool activity during a turn
- **THEN** that work is presented distinctly from conversational exchange

#### Scenario: Intermediate work can be collapsed

- **WHEN** a turn contains extensive intermediate work
- **THEN** the operator can collapse it to inspect the conversation without it
- **AND** can expand it again to inspect the detail

#### Scenario: A completed turn can be folded

- **WHEN** a turn has completed
- **THEN** the operator can fold it into a summary occupying materially less space
- **AND** unfold it to restore its full content

#### Scenario: Structured results are presented as self-contained surfaces

- **WHEN** an entry carries a substantial self-contained result, such as a proposed plan or a
  decision awaiting response
- **THEN** it is presented as a distinct surface rather than as a conversation bubble

#### Scenario: Clipped content is signalled

- **WHEN** an entry's content exceeds the height allotted to it
- **THEN** the interface indicates that further content exists

### Requirement: Each agent has a stable, assigned identity color

Every agent SHALL be assigned a color that remains stable for the lifetime of that agent, including
across restarts and renames. Assignment MUST NOT be derived from the agent's name.

An agent's color SHALL be used consistently wherever that agent is represented.

#### Scenario: Color survives restart and rename

- **WHEN** the Hub restarts, or an agent is renamed
- **THEN** that agent's assigned color is unchanged

#### Scenario: Concurrently registered agents are visually distinct

- **WHEN** several agents are registered
- **THEN** each is assigned a distinct color until the available set is exhausted

#### Scenario: Color is never the only identifier

- **WHEN** any entry or element is tinted with an agent's color
- **THEN** that agent's name is also present in text

#### Scenario: Colors are legible in both themes

- **WHEN** the interface is viewed in either light or dark mode
- **THEN** every agent color renders with legible text and a discernible boundary

### Requirement: Peer messages are tinted with the other agent's color

An entry representing a message received from another agent SHALL be tinted with the **sending**
agent's color. An entry representing a message sent to another agent SHALL be accented with the
**receiving** agent's color while remaining on the subject agent's side of the conversation.

#### Scenario: Inbound entries carry the sender's color

- **WHEN** the timeline shows a message received from another agent
- **THEN** it is tinted with that sending agent's color and labelled with its name

#### Scenario: Outbound entries carry the recipient's color

- **WHEN** the timeline shows a message the agent sent to another agent
- **THEN** it is accented with that recipient's color and labelled with its name
- **AND** it is positioned as the subject agent's own contribution

### Requirement: Queued entries are visible before delivery

An entry that has arrived but not yet been delivered to the agent SHALL appear in the timeline in a
distinct undelivered state, and SHALL adopt its normal appearance once delivered.

When an entry is waiting because the hop budget is exhausted, the timeline SHALL say so.

#### Scenario: The queue is watchable in real time

- **WHEN** entries arrive while the agent is running
- **THEN** they appear immediately in an undelivered state
- **AND** they change to their delivered appearance when the next turn receives them

#### Scenario: Operator input is queued visibly

- **WHEN** the operator submits input while the agent is running
- **THEN** that input appears in the timeline in the undelivered state
- **AND** the operator may continue submitting further input

#### Scenario: A suspended chain explains itself

- **WHEN** entries are waiting because the hop budget is exhausted
- **THEN** the timeline states that autonomous continuation is paused and that operator input will resume it

### Requirement: Undelivered entries can be withdrawn

An operator SHALL be able to withdraw an entry that has not yet been delivered. Withdrawal MUST NOT
be offered for an entry already delivered to a turn.

#### Scenario: A queued entry is withdrawn before delivery

- **WHEN** the operator withdraws an undelivered entry
- **THEN** it is removed from the queue and is never delivered
- **AND** the timeline reflects its removal

#### Scenario: Delivered entries cannot be withdrawn

- **WHEN** an entry has already been delivered to a turn
- **THEN** no withdrawal action is offered for it

### Requirement: The timeline is built from stored turn and message records

The conversation timeline SHALL be derived from recorded turns, agent output, and message records.
It MUST NOT attribute entries to a conversation by inferring from timestamp proximity.

#### Scenario: Attribution is recorded, not inferred

- **WHEN** the timeline is assembled for a given session
- **THEN** each entry is placed by its recorded association with that session
- **AND** no entry is placed by comparing its timestamp against session start or end times

#### Scenario: Concurrent sessions do not cross-contaminate

- **WHEN** an agent has run several sessions with overlapping activity
- **THEN** each session's timeline contains only its own entries
