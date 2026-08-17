# agent-conversation-workspace

## MODIFIED Requirements

### Requirement: A conversation remembers its runtime overrides

A conversation SHALL retain the runtime overrides chosen for it. Subsequent turns in that
conversation SHALL run under those overrides until the operator changes them.

Overrides SHALL be stored keyed by control identity, so that a newly declared control requires no
change to how a conversation is stored.

A new conversation the **operator** starts SHALL begin with no overrides, inheriting the values from
its agent's bound runner and the catalog's declared defaults. The operator is at the composer when
they start it and can choose; carrying a previous thread's settings in unasked would let one
conversation's choice quietly govern the next.

A new conversation opened by a **peer message or a scheduled job** SHALL inherit the runtime
overrides of its agent's most recent conversation. Nobody is at a composer when one of these opens,
so beginning clean does not mean "the operator accepted the defaults" — it means the choice they did
make was discarded at a boundary they cannot see. Observed: an operator set a posture, the agent
handed work to a peer, the peer replied, and the run that followed silently reverted to a posture
under which it could not execute anything, while still being asked to verify its own work.

A posture that removes every permission check SHALL NOT be inherited this way. That is a deliberate
choice for a thread being watched, and it must not reach runs the operator did not start by a route
they cannot see.

Inheritance SHALL copy values rather than share them: changing one conversation's overrides SHALL
NOT change another's.

#### Scenario: An override persists across turns

- **WHEN** the operator sets a model for a conversation and sends several messages
- **THEN** every one of those turns runs under that model

#### Scenario: An override survives reload

- **WHEN** the operator reloads the application and reopens the conversation
- **THEN** the conversation's chosen model and controls are still in effect and still displayed

#### Scenario: A new conversation inherits the agent's defaults

- **WHEN** the operator starts a new conversation with an agent
- **THEN** it runs under that agent's runner model and the catalog's control defaults
- **AND** it does not inherit the previous conversation's overrides

#### Scenario: A peer-opened conversation keeps what the operator chose

- **WHEN** an agent is triggered by another agent's message and no conversation is named
- **THEN** the conversation opened for it carries the overrides of that agent's most recent
  conversation

#### Scenario: A job-opened conversation keeps what the operator chose

- **WHEN** a scheduled job triggers an agent and no conversation is named
- **THEN** the conversation opened for it carries the overrides of that agent's most recent
  conversation

#### Scenario: Unrestricted access is not carried across

- **WHEN** a conversation's posture removes every permission check
- **AND** a peer message or a job opens a new conversation for that agent
- **THEN** that posture is not carried into it

#### Scenario: Inheritance does not couple two conversations

- **WHEN** a conversation inherits overrides from an earlier one
- **AND** the earlier conversation's overrides are later changed
- **THEN** the inheriting conversation's overrides are unchanged

#### Scenario: Changing a conversation's model does not change the agent

- **WHEN** the operator changes the model for one conversation
- **THEN** the agent's bound runner is unchanged
- **AND** the agent's other conversations are unaffected
