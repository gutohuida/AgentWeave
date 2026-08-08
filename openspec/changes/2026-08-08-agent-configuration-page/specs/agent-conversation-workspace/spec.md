## MODIFIED Requirements

### Requirement: Navigation rows expose their actions through a visible menu

Every agent row and every conversation row in navigation SHALL expose its actions through a menu
opened from a control on the row itself. That control MUST be reachable by keyboard and MUST NOT
require a pointer gesture that has no visible affordance.

A conversation row's menu SHALL offer rename and archive. An agent row's menu SHALL offer new
conversation, agent settings, and the archived-conversation listing.

Agent settings SHALL open as the agent's configuration destination.

This replaces the previous rule that settings open "without unmounting or navigating away from the
conversation that is currently open". That rule was written when settings were a dialog the rail
hosted, and its purpose was to stop the conversation being destroyed by opening settings — a real
hazard when the only alternative on offer was a panel inside the conversation surface.

A destination does not carry that hazard, and it answers what the dialog could not. Configuration
outgrew a modal; it now has sections, and it must be linkable, survive a reload, and be somewhere
the operator can be *sent*. None of that is expressible as a dialog. The conversation is not lost
by navigating to configuration any more than it is lost by navigating to the project overview: it
is a durable record, and the destination carries a fixed way back to it.

#### Scenario: A conversation's actions are reachable

- **WHEN** the operator opens a conversation row's menu
- **THEN** rename and archive are offered

#### Scenario: An agent's actions are reachable

- **WHEN** the operator opens an agent row's menu
- **THEN** new conversation, agent settings, and the archived listing are offered

#### Scenario: The menu is operable by keyboard alone

- **WHEN** the operator reaches a row's menu control by keyboard and opens it
- **THEN** every action in the menu is reachable and activatable by keyboard
- **AND** dismissing the menu returns focus to its trigger

#### Scenario: Agent settings open as a destination

- **WHEN** the operator opens agent settings from an agent row's menu
- **THEN** the agent's configuration destination opens
- **AND** no dialog is presented

#### Scenario: The conversation is not lost by configuring its agent

- **WHEN** the operator opens agent settings and then activates the back control
- **THEN** the agent's most recent conversation opens
- **AND** its history is unchanged

### Requirement: Only high-frequency controls remain visible

The resting composer SHALL expose only these controls: submit, stop while the agent is running, the
active-agent indicator, and context usage.

Conversation selection and starting a new conversation SHALL be performed from navigation. Agent
settings SHALL be reached from the agent's row menu in navigation and from the conversation header,
both of which open the agent's configuration destination. Durable handoff and fold-all SHALL be
present on the conversation header. The conversation-actions overflow menu SHALL be removed; no menu
on the conversation surface may serve as a conversation switcher.

An action that is unavailable SHALL be presented disabled with its reason rather than omitted, so
that the control set does not shift between agents.

#### Scenario: The resting control set is minimal

- **WHEN** a conversation is open and the agent is idle
- **THEN** the composer exposes submit, the active-agent indicator, and context usage
- **AND** exposes no provider-session selector, conversation selector, or scroll toggle

#### Scenario: Stop appears only while running

- **WHEN** the agent is running
- **THEN** a stop control is additionally visible

#### Scenario: The overflow menu is gone

- **WHEN** a conversation is open
- **THEN** no conversation-actions overflow menu is present
- **AND** no control on the conversation surface lists the agent's other conversations

#### Scenario: An unavailable action is disabled with its reason

- **WHEN** an action such as handoff is unavailable for the current agent
- **THEN** it is present, disabled, with the reason stated

#### Scenario: Settings are reachable from the conversation header

- **WHEN** a conversation is open
- **THEN** a control on its header opens that agent's configuration destination
