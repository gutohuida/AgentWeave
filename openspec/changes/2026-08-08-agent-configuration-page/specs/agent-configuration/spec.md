## ADDED Requirements

### Requirement: Agent configuration is a destination rather than a surface inside a conversation

The Hub SHALL present an agent's configuration as its own addressable destination, and MUST NOT
require an operator to open a conversation to reach it.

A conversation is transient and an agent may have many; its configuration is durable and singular.
Reaching configuration through a conversation makes it depend on which conversation happens to be
selected, and places durable settings behind a transient surface.

The destination MUST be linkable and MUST survive a reload, so configuration can be returned to
directly.

#### Scenario: Configuration is reached without opening a conversation

- **WHEN** the operator opens an agent's configuration from navigation
- **THEN** the configuration destination opens
- **AND** no conversation is required to have been selected

#### Scenario: The destination is durable

- **WHEN** the operator reloads while viewing an agent's configuration
- **THEN** the same agent's configuration is shown

### Requirement: Configuration navigation replaces the surrounding navigation with a return control

An agent's configuration SHALL present its sections in place of the surrounding navigation, and
SHALL offer a control returning to the context the operator came from.

This follows the project's own settings pattern, where a section list replaces the tab strip rather
than nesting inside it. A settings surface is somewhere an operator goes and comes back from, not
somewhere they browse laterally, so the lateral navigation is what gives way.

Returning MUST lead to the originating context rather than to a fixed location, because an operator
who opened configuration from a conversation is mid-task in that conversation.

#### Scenario: Sections replace lateral navigation

- **WHEN** an agent's configuration is shown
- **THEN** its sections are presented in place of the surrounding navigation

#### Scenario: Returning leads back to the origin

- **WHEN** the operator opens configuration from a conversation and then returns
- **THEN** that conversation is shown again

#### Scenario: Returning from a different origin

- **WHEN** the operator opens configuration from navigation and then returns
- **THEN** the context they came from is shown rather than a conversation

### Requirement: Configuration is separated from observation

An agent's configuration destination SHALL present only settings, and observations about a running
agent SHALL remain with the agent's conversation.

Status, the latest status message, last-seen time and the session list change without anyone
configuring anything, and they are useful while working rather than while configuring. Mixing them
with settings produces a surface that changes under the reader and a conversation stripped of the
context it needs.

No setting SHALL be editable from more than one surface.

#### Scenario: Observations are not on the configuration destination

- **WHEN** an agent's configuration is shown
- **THEN** live status and session history are not presented there

#### Scenario: Observations remain available while working

- **WHEN** the operator is working in an agent's conversation
- **THEN** that agent's status and sessions remain available there

#### Scenario: A setting has one home

- **WHEN** a setting is presented on the configuration destination
- **THEN** it is not also editable elsewhere

### Requirement: Configuration sections are named for operator intent

An agent's configuration SHALL be divided into sections named for what an operator is trying to do,
covering identity, execution, charter, interaction, context, access, and workspace.

Naming sections after operator intent rather than after data shape is what allows a later capability
to add settings without the section having to be renamed or restructured. *Context* and *Access* are
defined here and are populated further by conversation checkpointing.

A section MUST NOT be named for a concept the product no longer has.

#### Scenario: A new setting joins an existing section

- **WHEN** a capability introduces an agent-level setting for automatic checkpointing
- **THEN** it is presented within the context section
- **AND** no section is renamed or restructured to accommodate it

#### Scenario: Bindings are bound, not edited

- **WHEN** the operator views the runner or charter an agent is bound to
- **THEN** the binding can be changed
- **AND** the runner or charter record itself is not edited from this destination

### Requirement: A setting with no backing state is not presented

The Hub SHALL NOT present an agent setting that has no state behind it, and SHALL NOT expose such a
field on the agent's API representation.

An agent's stored record has no role and no autonomy-flag state. Both were nonetheless carried on
the response schema and rendered, one of them as a badge that could only ever report a single value
because its source was a constant. A control that cannot report anything but one state is not a
control; it is a claim that something is configurable when it is not.

The operator MUST NOT be asked to choose a persona or organizational role, which
`operator-agent-creation` already requires of creation and which applies equally to configuration.

#### Scenario: A field without stored state is absent from the API

- **WHEN** an agent is returned by the API
- **THEN** no field is present that has no corresponding stored state

#### Scenario: No persona or role is configurable

- **WHEN** an agent's configuration is shown
- **THEN** no persona or organizational role is offered
