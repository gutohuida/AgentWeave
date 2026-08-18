## ADDED Requirements

### Requirement: Each agent has one ordered inbound queue

Every agent SHALL have a single ordered queue of inbound entries. Both operator-authored input and
messages from other agents SHALL enter that same queue. An entry SHALL record its origin, its
content, its arrival time, its hop depth, and its delivery state.

The Hub MUST NOT distinguish operator input from peer messages by inspecting a sender name or
message subject text. Origin SHALL be a typed property of the entry.

#### Scenario: Operator input and peer messages share one queue

- **WHEN** an operator submits input to an agent and another agent sends that agent a message
- **THEN** both are recorded as entries on the same queue in arrival order
- **AND** each carries a typed origin identifying it as operator input or as a message from a named agent

#### Scenario: An agent may legally be named like a reserved word

- **WHEN** an agent is registered under a name that resembles an internal marker, such as `user`
- **THEN** entry origin remains unambiguous
- **AND** no routing or attribution depends on that name

### Requirement: Turns start whenever the queue is non-empty and the agent is idle

An agent SHALL begin a turn whenever its queue holds undelivered entries and it is not already
running. A turn MUST NOT wait for operator input to begin.

When a turn ends with undelivered entries still queued, a further turn SHALL begin.

#### Scenario: An idle agent starts work on arrival

- **WHEN** an entry arrives for an agent that is idle and launchable
- **THEN** a turn starts without further operator action

#### Scenario: Arrivals during a turn are queued, not dropped

- **WHEN** entries arrive while the agent is running
- **THEN** they are queued
- **AND** they are delivered at the start of the next turn

#### Scenario: Work continues across turn boundaries without prompting

- **WHEN** a turn ends and undelivered entries remain
- **THEN** a further turn begins and delivers them

#### Scenario: An unlaunchable agent accumulates its queue

- **WHEN** entries arrive for an agent that cannot currently be launched
- **THEN** the entries remain queued and are not lost
- **AND** the interface reports that entries are waiting, with the reason the agent is not running

### Requirement: A turn delivers queued content directly, up to a configured cap

At the start of a turn the agent SHALL receive the content of its queued entries in arrival order,
each attributed to its origin. Content MUST be delivered inline. The agent MUST NOT be told merely
that input exists and asked to retrieve it separately.

A configurable maximum number of entries SHALL be delivered per turn. Entries beyond that maximum
SHALL remain queued rather than being discarded or summarized.

Delivery SHALL be atomic with the start of the turn: entries marked delivered MUST be exactly those
the started turn received.

#### Scenario: Content arrives inline with attribution

- **WHEN** a turn starts with queued entries
- **THEN** the agent receives their content directly, in arrival order, each attributed to its origin
- **AND** the agent is not instructed to call a retrieval tool to obtain them

#### Scenario: The per-turn cap defers rather than discards

- **WHEN** the queue holds more entries than the configured per-turn maximum
- **THEN** the turn delivers up to the maximum in arrival order
- **AND** the remaining entries stay queued and are delivered by the turns that follow

#### Scenario: Interrupted delivery neither duplicates nor loses entries

- **WHEN** turn startup fails after entries are selected for delivery
- **THEN** no entry is recorded as delivered
- **AND** every entry remains queued for the next attempt

### Requirement: A hop budget bounds autonomous agent-to-agent chains

Each entry SHALL carry a hop depth. Operator-authored entries SHALL have depth zero. A turn's depth
SHALL be the lowest depth among the entries it received, and any message the agent emits during that
turn SHALL carry that depth plus one.

When an arriving entry's depth exceeds the configured hop budget, it SHALL be queued but MUST NOT
cause a turn to start. Such an entry SHALL be delivered on the next turn that starts for any other
reason.

Because operator-authored entries have depth zero, operator input SHALL always be able to restart a
stalled chain.

#### Scenario: Depth increases along an agent-to-agent chain

- **WHEN** an operator's input causes an agent to message a second agent, which messages a third
- **THEN** the entries carry increasing depth along that chain

#### Scenario: Exceeding the budget suspends autonomy without losing content

- **WHEN** an arriving entry's depth exceeds the hop budget
- **THEN** it is queued and no turn starts on its account
- **AND** the interface shows it as waiting because the hop budget is exhausted

#### Scenario: Operator input resets the chain

- **WHEN** an operator submits input to an agent whose queue holds budget-exhausted entries
- **THEN** a turn starts
- **AND** that turn receives both the operator's input and the waiting entries
- **AND** messages emitted during that turn carry depth one

#### Scenario: A mixed batch resets to the operator's depth

- **WHEN** a turn receives both operator input and a deep peer entry
- **THEN** the turn's depth is zero
- **AND** messages it emits carry depth one

### Requirement: A running turn can be stopped without losing queued work

The operator SHALL be able to stop a running turn. Stopping SHALL terminate the agent process for
that turn and record the turn as stopped rather than as completed or failed.

Entries already delivered to the stopped turn MUST NOT be redelivered. Entries still queued MUST
survive the stop and be delivered by the following turn.

#### Scenario: A turn is stopped on request

- **WHEN** the operator stops a running turn
- **THEN** the agent process for that turn terminates
- **AND** the turn is recorded as stopped

#### Scenario: Queued entries survive a stop

- **WHEN** a turn is stopped while entries remain queued
- **THEN** those entries remain queued
- **AND** a following turn delivers them

#### Scenario: Delivered entries are not redelivered after a stop

- **WHEN** a turn is stopped after receiving its entries
- **THEN** those entries are not delivered again

#### Scenario: Stopping is distinguishable from failure

- **WHEN** the timeline shows a stopped turn
- **THEN** it is presented as deliberately stopped, not as an error

### Requirement: Queue limits are configurable

The hop budget and the per-turn delivery maximum SHALL both be configurable, with documented
defaults that apply when unset. Changing them MUST NOT require modifying source code.

The default hop budget SHALL be **6**, accommodating a realistic delegation chain while halting
runaway exchanges. The default per-turn delivery maximum SHALL be **10** entries.

#### Scenario: Defaults apply when unconfigured

- **WHEN** no values are configured
- **THEN** the hop budget is 6 and the per-turn maximum is 10
- **AND** the effective values are inspectable

#### Scenario: Configured values take effect

- **WHEN** an operator sets either limit
- **THEN** subsequent turns and deliveries observe the configured value

#### Scenario: Invalid configuration is rejected visibly

- **WHEN** a limit is configured to a non-positive or unparseable value
- **THEN** the Hub reports the invalid configuration rather than silently applying it
