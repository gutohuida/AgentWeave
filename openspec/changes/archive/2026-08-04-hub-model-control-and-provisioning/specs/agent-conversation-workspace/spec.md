## ADDED Requirements

### Requirement: The operator sets model and effort from the conversation

The composer SHALL present the model and the runtime controls declared by the target agent's
provider, and SHALL allow the operator to change them without leaving the conversation.

The controls presented SHALL be those the catalog declares for that provider. When the target agent
changes to one on a different provider, the presented controls SHALL change with it.

#### Scenario: Model and effort are changed in place

- **WHEN** the operator changes the model or an effort control in the composer
- **THEN** the next message runs under the chosen values
- **AND** the operator has not navigated away from the conversation

#### Scenario: Controls follow the provider

- **WHEN** the operator changes the target agent to one on a different provider
- **THEN** the composer presents that provider's models and controls

#### Scenario: The current selection is visible at rest

- **WHEN** a conversation is open
- **THEN** the model and control values that the next message will use are visible without opening a
  menu

### Requirement: A conversation remembers its runtime overrides

A conversation SHALL retain the runtime overrides chosen for it. Subsequent turns in that
conversation SHALL run under those overrides until the operator changes them.

Overrides SHALL be stored keyed by control identity, so that a newly declared control requires no
change to how a conversation is stored.

A new conversation SHALL begin with no overrides, inheriting the values from its agent's bound
runner and the catalog's declared defaults.

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

#### Scenario: Changing a conversation's model does not change the agent

- **WHEN** the operator changes the model for one conversation
- **THEN** the agent's bound runner is unchanged
- **AND** the agent's other conversations are unaffected

### Requirement: A message is routed to a stated conversation

The composer SHALL let the operator state whether a message continues the current conversation or
begins a new one with the target agent.

The routing choice SHALL be visible before the message is sent.

#### Scenario: A message continues the current conversation

- **WHEN** the operator sends a message with the current conversation selected
- **THEN** the message is delivered into that conversation

#### Scenario: A message begins a new conversation

- **WHEN** the operator selects a new conversation and sends a message
- **THEN** a new conversation is created for the target agent and the message is delivered into it
- **AND** the previous conversation is left intact

#### Scenario: Routing is visible before sending

- **WHEN** the composer is displayed
- **THEN** the conversation the next message will reach is identifiable without sending it
