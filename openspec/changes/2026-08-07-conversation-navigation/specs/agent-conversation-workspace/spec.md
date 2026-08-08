## ADDED Requirements

### Requirement: An agent's conversations are listed beneath it in navigation

Navigation SHALL list an agent's open conversations as that agent's children, ordered by most
recent activity first, each labelled by its title.

Activating the agent's expander SHALL toggle its conversation list without navigating. Activating
the agent's name SHALL open that agent's most recent conversation, matching the behaviour that
existed before conversations were listed. The two MUST be separately activatable, as they already
are for the project entry.

Beyond a fixed number of conversations, the remainder SHALL be reachable through an explicit
expander that states how many are hidden, rather than being omitted silently or scrolling
unbounded.

#### Scenario: An agent expands to its conversations

- **WHEN** the operator activates an agent's expander
- **THEN** that agent's open conversations are listed beneath it, newest activity first
- **AND** the active destination is unchanged

#### Scenario: The agent's name still opens its most recent conversation

- **WHEN** the operator activates an agent's name
- **THEN** that agent's most recent conversation opens

#### Scenario: A conversation is opened from navigation

- **WHEN** the operator activates a conversation in navigation
- **THEN** that conversation opens in the content area
- **AND** the destination records the project, agent, and conversation

#### Scenario: The remainder is reachable, never silently dropped

- **WHEN** an agent has more conversations than the display limit
- **THEN** an expander states how many further conversations exist
- **AND** activating it lists them

#### Scenario: A peer-created conversation is listed like any other

- **WHEN** a conversation was created because a peer agent addressed this agent
- **THEN** it appears in that agent's conversation list
- **AND** its origin is distinguishable from a conversation the operator started

### Requirement: Navigation offers a recency view across agents

Navigation SHALL offer a view listing the project's conversations across all of its agents, ordered
by most recent activity first, as an alternative to the agent tree. The agent tree SHALL be the
default, and the chosen view SHALL persist across reloads.

In the recency view each conversation SHALL carry its agent's assigned identity colour as a
persistent leading edge, so the owning agent is readable without hovering or opening the
conversation. The colour MUST match the one used for that agent in the tree and in the conversation
timeline.

Archived conversations SHALL be excluded from the recency list, and SHALL be reachable from it
through an explicit control stating how many exist — the same affordance the tree offers per
agent, offered here across the project. Hiding them without saying they are there reads as data
loss to an operator who archives often.

#### Scenario: The tree is the default view

- **WHEN** the operator loads the Hub having never chosen a view
- **THEN** navigation shows the agent tree

#### Scenario: The recency view lists conversations across agents

- **WHEN** the operator switches to the recency view
- **THEN** conversations from every agent in the project are listed together, most recent activity first

#### Scenario: Agent identity is readable at rest

- **WHEN** the recency view is shown
- **THEN** each conversation carries its agent's identity colour without requiring hover
- **AND** that colour is the same one the agent carries in the tree and the timeline

#### Scenario: Archived conversations are reachable from the recency view

- **WHEN** the recency view is shown
- **THEN** archived conversations are not listed among the open ones
- **AND** a control states how many archived conversations the project has
- **AND** activating it lists them

#### Scenario: The chosen view survives reload

- **WHEN** the operator switches view and reloads
- **THEN** the chosen view is still shown

### Requirement: A conversation's attention state is visible in navigation

Navigation SHALL show, for each listed conversation, whether it is running, waiting on the operator,
or idle. A conversation is waiting on the operator when it holds an unanswered question, an
undecided permission request, or an undismissed unasked-question flag.

The waiting state MUST be distinguishable from the running state, because a waiting run consumes
its configured timeout while the operator is unaware of it.

#### Scenario: A blocked conversation is visible without opening it

- **WHEN** a run in one conversation opens a question and blocks
- **AND** the operator is looking at a different conversation
- **THEN** navigation shows that conversation as waiting on the operator

#### Scenario: Running and waiting are distinguishable

- **WHEN** one conversation is running and another is waiting on the operator
- **THEN** navigation presents the two states differently

#### Scenario: The state clears when the operator answers

- **WHEN** the operator answers the outstanding question
- **THEN** navigation no longer shows that conversation as waiting

#### Scenario: A permission request raises the same state

- **WHEN** a run opens a permission request and blocks
- **THEN** navigation shows that conversation as waiting on the operator

### Requirement: Navigation rows expose their actions through a visible menu

Every agent row and every conversation row in navigation SHALL expose its actions through a menu
opened from a control on the row itself. That control MUST be reachable by keyboard and MUST NOT
require a pointer gesture that has no visible affordance.

A conversation row's menu SHALL offer rename and archive. An agent row's menu SHALL offer new
conversation, agent settings, and the archived-conversation listing.

Agent settings SHALL open without unmounting or navigating away from the conversation that is
currently open.

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

#### Scenario: Agent settings do not replace the conversation

- **WHEN** the operator opens agent settings from an agent row's menu
- **THEN** settings for that agent open without unmounting the open conversation
- **AND** closing them returns focus to the invoking control

### Requirement: Starting a conversation is a navigation action with a dedicated surface

Starting a new conversation SHALL be initiated from navigation and SHALL open a surface whose
composer is the primary element, rather than an empty transcript.

A conversation started from an agent's row SHALL already be bound to that agent. A conversation
started from the recency view, where no agent is implied, SHALL require the operator to choose the
agent on that surface before the first message can be sent.

No conversation record SHALL be created until the first message is sent, so an abandoned start
leaves nothing behind.

#### Scenario: Starting from an agent binds the agent

- **WHEN** the operator starts a conversation from an agent's row menu
- **THEN** the new-conversation surface opens already bound to that agent
- **AND** no agent choice is required

#### Scenario: Starting from the recency view requires an agent

- **WHEN** the operator starts a conversation from the recency view
- **THEN** the new-conversation surface requires an agent to be chosen
- **AND** the message cannot be sent until one is

#### Scenario: An abandoned start leaves no record

- **WHEN** the operator opens the new-conversation surface and navigates away without sending
- **THEN** no conversation record exists
- **AND** navigation lists no additional conversation

#### Scenario: The first message creates the conversation

- **WHEN** the operator sends the first message from the new-conversation surface
- **THEN** a conversation is created, titled, and listed in navigation
- **AND** the destination moves to it

### Requirement: Durable handoff has a persistent place on the conversation

The durable handoff control SHALL be present on the open conversation's own header, labelled, and
visible at rest. It MUST NOT be placed behind a menu, and it MUST NOT be a row action in navigation.

When the control is unavailable, it SHALL be presented disabled with its reason rather than
omitted, so its position does not change between agents.

#### Scenario: Handoff is visible without opening anything

- **WHEN** a conversation is open
- **THEN** a labelled handoff control is visible on its header

#### Scenario: An unavailable handoff states why

- **WHEN** handoff is unavailable for the current agent or conversation
- **THEN** the control is present, disabled, with its reason stated

## MODIFIED Requirements

### Requirement: Navigation lists the project and its agents as a tree

Navigation SHALL present the current project as a named entry whose children are its agents, and
each agent as an entry whose children are its conversations.

Activating the project's name SHALL navigate to the project overview. Activating its expander SHALL
toggle the agent list without navigating. The two MUST be separately activatable. An agent entry
SHALL follow the same rule: its name navigates, its expander toggles.

#### Scenario: The expander toggles without navigating

- **WHEN** the operator activates the project's expander
- **THEN** the agent list collapses
- **AND** the active destination is unchanged

#### Scenario: The project name navigates

- **WHEN** the operator activates the project's name
- **THEN** the project overview opens

#### Scenario: Agent identity colour appears beside the name

- **WHEN** the rail lists a project's agents
- **THEN** each entry shows that agent's assigned colour together with its name in text
- **AND** the colour matches the one used for that agent in the conversation timeline

#### Scenario: An agent's expander toggles without navigating

- **WHEN** the operator activates an agent's expander
- **THEN** that agent's conversation list toggles
- **AND** the active destination is unchanged

### Requirement: Only high-frequency controls remain visible

The resting composer SHALL expose only these controls: submit, stop while the agent is running, the
active-agent indicator, and context usage.

Conversation selection and starting a new conversation SHALL be performed from navigation. Agent
settings SHALL be reached from the agent's row menu in navigation. Durable handoff and fold-all
SHALL be present on the conversation header. The conversation-actions overflow menu SHALL be
removed; no menu on the conversation surface may serve as a conversation switcher.

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

#### Scenario: Agent settings do not replace the conversation

- **WHEN** the operator opens agent settings from navigation
- **THEN** details for that agent open without unmounting or navigating away from the conversation
- **AND** closing the details returns focus to the invoking control

### Requirement: Conversation identity is readable without exposing provider identity

The provider-session selection control SHALL be removed from the conversation surface. The current
AgentWeave conversation's continuity state SHALL remain visible as human-readable text, and
conversation selection SHALL be performed from navigation. Normal navigation, URLs, history, and
drafts MUST use `conversation_id`; provider session IDs MAY appear only in details or diagnostic
surfaces.

A conversation SHALL be labelled by its title wherever it is listed or named. Its identifier MUST
NOT be presented as its label.

#### Scenario: Continuity is readable at rest

- **WHEN** a conversation is continuing an existing session
- **THEN** its continuity state is readable as text on the resting surface

#### Scenario: Conversation selection works from navigation

- **WHEN** the operator selects a different AgentWeave conversation from navigation
- **THEN** the conversation switches to it with the same effect the removed selector had

#### Scenario: Provider identity is hidden from normal conversation controls

- **WHEN** the operator inspects the resting surface and navigation
- **THEN** no provider session ID is shown as a conversation label or selection value
- **AND** provider binding remains available in agent details or diagnostics

#### Scenario: Conversations are labelled by title

- **WHEN** navigation lists an agent's conversations
- **THEN** each is labelled by its title
- **AND** no conversation identifier is shown as a label
