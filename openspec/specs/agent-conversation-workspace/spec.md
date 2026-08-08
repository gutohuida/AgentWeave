# agent-conversation-workspace Specification

## Purpose

The AgentWeave conversation is the primary workspace surface: navigation reaches an agent's
conversation directly, the operator can keep talking to an agent while it is running, and the
composer is a bounded, draft-persisting input with a minimal always-visible control set.

Everything that is not a per-conversation control has left the composer. Navigation is a tree of
project → agent → conversation, and it is where conversations are selected, started, and acted on;
agent settings are reached from the agent's row; handoff and fold-all sit on the conversation
header. The conversation-actions overflow menu is gone, and no menu on the conversation surface
serves as a conversation switcher.

AgentWeave owns a durable `conversation_id` that exists before any provider process starts and
never changes across runs, retries, stops, or provider-session binding; the provider session is
nullable continuation data beneath it, never the operator-facing identity. Conversations are
labelled by title, never by identifier — the title, origin, rename and archival rules themselves
belong to `conversation-lifecycle`.
## Requirements
### Requirement: AgentWeave owns the durable conversation identity

The system SHALL allocate a stable `conversation_id` before starting a provider process. A
conversation SHALL belong to exactly one project and one immutable target agent, SHALL remain the
same across runs, retries, stops, failures, and provider-session binding, and SHALL treat provider
session identity as nullable continuation data rather than as the conversation's identity.

Every newly created run, inbound queue entry, and recorded agent output SHALL carry its
`conversation_id`. An outbound peer message SHALL carry its sender conversation, and its recipient
queue entry SHALL carry the recipient conversation selected by the queue-routing contract.

#### Scenario: A new conversation is returned synchronously

- **WHEN** the operator submits input without a `conversation_id`
- **THEN** the server creates a conversation and its first queue entry atomically
- **AND** the response contains the new `conversation_id` whether its status is `running` or `queued`
- **AND** the response does not wait for a provider session ID

#### Scenario: Immediate follow-up targets the same conversation

- **WHEN** the operator submits another input with the returned `conversation_id` before provider binding completes
- **THEN** the new queue entry carries that `conversation_id`
- **AND** no second provider session is started for that conversation while its first run is active

#### Scenario: Provider binding does not replace application identity

- **WHEN** runner output first reports a provider session ID for an unbound conversation
- **THEN** the run and conversation are bound to that provider session before the output is recorded
- **AND** the conversation retains its original `conversation_id`

#### Scenario: Conflicting provider binding is refused

- **WHEN** runner output reports a provider session ID different from the conversation's existing binding
- **THEN** the existing binding is not overwritten
- **AND** the run fails with a recorded binding-conflict event

#### Scenario: Conversation scope is enforced

- **WHEN** a trigger supplies a conversation belonging to another project, another agent, or an archived conversation
- **THEN** the request is rejected
- **AND** no queue entry or run is created

#### Scenario: Runs are attempts within a conversation

- **WHEN** a run completes, fails, is interrupted, or is stopped
- **THEN** the conversation remains open
- **AND** a retry creates another run carrying the same `conversation_id`

#### Scenario: Different conversations never share one provider turn

- **WHEN** one agent has eligible queued entries for multiple conversations
- **THEN** the scheduler chooses the conversation of the oldest eligible entry
- **AND** the resulting run drains only entries for that conversation in arrival order up to the existing cap

#### Scenario: History uses recorded conversation association

- **WHEN** the selected conversation history is requested
- **THEN** runs, output, peer traffic, delivered input, and still-queued input are selected by recorded `conversation_id`
- **AND** neither provider session matching nor timestamp proximity determines membership

#### Scenario: Legacy state is migrated without deletion

- **WHEN** existing session-based records are migrated
- **THEN** records with the same non-null project, agent, and provider session are attached to one conversation
- **AND** each unbound legacy run receives its own conversation
- **AND** ambiguous orphan records remain available to migration diagnostics rather than being guessed or deleted

#### Scenario: Reset is the only destructive lifecycle operation

- **WHEN** AgentWeave starts, migrates, stops a run, archives a conversation, or reopens a project
- **THEN** conversation records and history are retained
- **AND** they are deleted only through the existing explicitly confirmed reset operation

### Requirement: An agent conversation is reached directly, without an intermediate list

Selecting an agent from the navigation rail or from the project overview's agent roster SHALL open
that agent's conversation occupying the full content area.

There MUST NOT be an intermediate agent list, filter tab bar, or detail-panel selection step between
choosing an agent and reading its conversation.

#### Scenario: An agent chosen in the rail opens its conversation

- **WHEN** the operator activates an agent in the navigation rail
- **THEN** that agent's conversation is rendered as the whole content area
- **AND** no agent list, filter tab bar, or "select an agent" placeholder is present

#### Scenario: An agent chosen in the overview roster opens the same conversation

- **WHEN** the operator activates an agent in the project overview's roster
- **THEN** that agent's conversation opens directly, in the same state as if opened from the rail

#### Scenario: The conversation carries exactly one header

- **WHEN** an agent conversation is open
- **THEN** the agent's name appears in exactly one header region
- **AND** no second header or status strip repeating it is present

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

### Requirement: The containing project is reachable from a conversation

From an open agent conversation, the containing project's overview SHALL be reachable in a single
action.

#### Scenario: One action returns to the project

- **WHEN** the operator activates the back-to-project control from a conversation
- **THEN** the project overview opens
- **AND** no intermediate destination is passed through

### Requirement: Agents and Messages are removed as navigation destinations

Navigation MUST NOT offer an *Agents* destination or a *Messages* destination.

Message records, the messages API, agent records, and the agents API MUST remain unchanged. They are
still the source data for routing, attribution, and history, and peer traffic in both directions is
already merged into the conversation timeline, so the destinations are redundant rather than the
records.

#### Scenario: The destinations are absent

- **WHEN** the Hub is loaded
- **THEN** navigation offers no *Agents* destination and no *Messages* destination

#### Scenario: The underlying records and endpoints are untouched

- **WHEN** the messages and agents endpoints are exercised by their existing tests
- **THEN** every test passes unmodified

### Requirement: The composer accepts input while the agent is running

WHEN the operator submits composer input while the agent is running, THE SYSTEM SHALL enqueue that
input and SHALL display it in the conversation timeline in the undelivered state without requiring a
manual refresh.

The composer's text input and its submit control MUST NOT be disabled on account of the agent's
running state. They MAY be disabled only while a submission of their own is in flight.

The interface MUST NOT branch on the agent's running state when deciding whether to submit. The
trigger endpoint reports whether a turn started or the input was queued, and that report is the only
source of truth for the outcome.

#### Scenario: Input submitted during a run is queued and shown

- **WHEN** the operator submits input to a running agent
- **THEN** the trigger endpoint is called
- **AND** on a queued outcome the input appears in the timeline in the undelivered state without a refresh

#### Scenario: Further input can be submitted immediately

- **WHEN** the operator submits a second input while the first is still queued
- **THEN** it is also queued
- **AND** it appears in arrival order after the first

#### Scenario: Follow-up input stays in a newly started conversation

- **WHEN** the operator starts a new conversation and submits further input before the runner reports its provider session ID
- **THEN** the further input is associated with the same AgentWeave conversation
- **AND** it MUST NOT start a second provider session merely because the first session ID is not known yet

#### Scenario: The running state never disables the composer

- **WHEN** an agent's status is running
- **THEN** neither the composer text input nor the submit control carries a disabled state attributable to that status

#### Scenario: An in-flight submission may disable submission only briefly

- **WHEN** a submission is in flight
- **THEN** the submit control may be disabled until that submission settles
- **AND** it is enabled again afterwards

#### Scenario: A failed submission returns the operator's text

- **WHEN** a submission fails
- **THEN** the typed text is restored into the composer
- **AND** the failure is reported in the banner region

#### Scenario: Queued input is rendered from recorded entries only

- **WHEN** input is queued
- **THEN** the timeline entry shown for it originates from the server's recorded queue entry
- **AND** no locally synthesized entry is added

### Requirement: The composer grows with its content within bounds

The composer SHALL present at least 3 text rows at rest, SHALL grow with its content to at least 12
rows, and SHALL scroll rather than grow beyond its maximum.

#### Scenario: The resting composer is multi-line

- **WHEN** the composer is empty
- **THEN** its rendered height is at least 3 text rows

#### Scenario: Growth stops and scrolling begins

- **WHEN** the operator enters content exceeding the maximum height
- **THEN** the composer stops growing
- **AND** the content scrolls within it

### Requirement: Unsent composer text survives navigation and reload

Unsent composer text SHALL be retained per project and AgentWeave conversation across navigation
away and back and across a page reload, SHALL be cleared on successful submission, and MUST NOT be
visible in or overwritten by another project, agent, or conversation.

Where persistent storage is unavailable, the composer SHALL remain fully functional; only persistence
is lost.

#### Scenario: A draft survives leaving and returning

- **WHEN** the operator types unsent text for one agent, navigates to another agent, and returns
- **THEN** the first agent's text is present
- **AND** the second agent's composer was empty

#### Scenario: A draft survives reload

- **WHEN** the page is reloaded with an unsent draft present
- **THEN** the draft is still present

#### Scenario: Drafts do not leak between conversations of one agent

- **WHEN** one agent has unsent drafts in two different conversations
- **THEN** each conversation shows only its own draft

#### Scenario: Submission clears the draft

- **WHEN** a draft is submitted successfully
- **THEN** the stored draft for that conversation is cleared
- **AND** no delayed persistence write restores the submitted text

#### Scenario: Unavailable storage degrades to no persistence

- **WHEN** persistent storage cannot be written
- **THEN** the composer still accepts and submits input
- **AND** only draft retention is lost

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

### Requirement: Autoscroll follows the operator's scroll position

The manual pause/resume-scroll control SHALL be removed. Following of new output SHALL be determined
by scroll position: pinned while the operator is at the bottom, suspended once they scroll away, and
resumed when they return to the bottom.

The scroll position already expresses the intent the removed control duplicated.

#### Scenario: Output is followed while at the bottom

- **WHEN** the conversation is scrolled to the bottom and new output arrives
- **THEN** the view stays pinned to the newest entry
- **AND** no scroll toggle control is present

#### Scenario: Scrolling away suspends following

- **WHEN** the operator scrolls up and new output arrives
- **THEN** the viewport does not move

#### Scenario: Returning to the bottom resumes following

- **WHEN** the operator scrolls back to the bottom
- **THEN** following of new output resumes

### Requirement: Conditions are reported in a banner stack above the composer

A banner region directly above the composer SHALL display run failure, stream loss, and
blocked-queue conditions. Simultaneous conditions SHALL stack in a stable order, each stating its own
condition.

#### Scenario: Simultaneous conditions stack

- **WHEN** the last run failed and the event stream is disconnected
- **THEN** two banners are shown above the composer in a stable order
- **AND** each names its own condition

#### Scenario: A cleared condition leaves the others in place

- **WHEN** one condition clears
- **THEN** its banner is removed
- **AND** the remaining banner keeps its position

### Requirement: Context-window usage is shown in the composer

The composer SHALL display the agent's context-window consumption using the existing indicator,
derived from the most recent context-usage event reported for that agent.

Where no context-usage event has been received, the composer SHALL render no indicator rather than a
zero value, because a zero would assert a measurement that was never taken.

#### Scenario: Reported usage is shown

- **WHEN** a context-usage event has been received for the displayed agent
- **THEN** the composer shows the usage indicator reflecting that event

#### Scenario: Absent usage renders nothing

- **WHEN** no context-usage event has been received for the displayed agent
- **THEN** no usage indicator and no zero value is rendered

### Requirement: Existing conversation behaviour is preserved

Provider continuity, durable handoff, stop, withdraw, and deliver-now SHALL CONTINUE TO behave as
specified after the stable-conversation migration, including successor-conversation handoff.

Queue semantics — hop budget, per-turn delivery cap, and delivery ordering — SHALL CONTINUE TO be
unchanged by this change.

#### Scenario: Existing conversation suites still pass

- **WHEN** the existing conversation, timeline, handoff, and status suites are run against the reworked surface
- **THEN** every assertion about continuity, handoff, stop, withdraw, and deliver-now passes
- **AND** the only changes to those suites are to how the surface is mounted and queried

#### Scenario: Queue controls remain available in the conversation

- **WHEN** an undelivered entry or hop-budget-blocked chain is shown
- **THEN** the operator can still withdraw the undelivered entry or deliver the blocked chain now

### Requirement: Navigation reads from the registered project collection

Navigation SHALL read its project and agent tree from one adapter containing every registered
project the local operator can reach. The operator SHALL be able to open an existing project
directory, explicitly create a new one, and switch projects without changing credentials.

The adapter SHALL preserve project and agent live state for inactive projects. Project switching
MUST NOT leak conversations, drafts, cached server state, or in-flight mutation results across
project identifiers.

#### Scenario: Multiple projects are rendered from the collection

- **WHEN** the local instance has two registered projects
- **THEN** the adapter returns both projects with their agents
- **AND** the unchanged collection rail renders both

#### Scenario: Project management is offered

- **WHEN** the operator inspects the project collection controls
- **THEN** distinct actions to open an existing directory and create a new directory are available

#### Scenario: Switching preserves isolation

- **WHEN** the operator switches projects while a request or agent run remains active in the first
  project
- **THEN** the first project's state continues under its identity
- **AND** none of it is rendered as belonging to the selected project

### Requirement: Conversation navigation is URL-backed and project-scoped

Normal project, agent, and conversation navigation SHALL be represented in the browser URL using
stable project and AgentWeave conversation identity. Reload and back/forward navigation SHALL
restore the represented destination. Provider session identifiers MUST NOT be used as URL identity.

#### Scenario: A conversation URL reloads

- **WHEN** the operator reloads an agent conversation in one project
- **THEN** the same project, agent, and AgentWeave conversation are restored

#### Scenario: Browser history crosses projects

- **WHEN** the operator visits project A, then project B, then activates Back
- **THEN** project A and its prior destination are restored without changing credentials

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

---

### Requirement: A delivered turn reaches the model intact

Every queued input the Hub marks as delivered SHALL reach the agent's model in full. The Hub
MUST NOT report an input as delivered when the mechanism used to start the run cannot carry it.

Where a platform's process-launch path can alter, truncate, or reinterpret a run's arguments —
for example a command interpreter that parses a command line before the target program receives
it — the Hub SHALL use a launch path that preserves them exactly, including argument content
that spans multiple lines.

#### Scenario: A multi-line turn prompt is delivered whole

- **WHEN** the Hub starts a run whose turn prompt spans several lines
- **THEN** the agent receives every line of that prompt

#### Scenario: Delivery state reflects what the model actually received

- **WHEN** a queued input is marked delivered against a run
- **THEN** that input's full content formed part of the prompt that run was started with

---

### Requirement: A turn's folded state is set by the operator, never by its position

A turn SHALL render expanded unless the operator has folded it. Foldedness MUST NOT be derived from
a turn's position in the conversation, and appending a new turn MUST NOT change the folded state of
any existing turn.

Every turn SHALL be foldable, including the most recent one. A turn the operator has folded SHALL
stay folded, and a turn the operator has expanded SHALL stay expanded, as the conversation grows.

#### Scenario: Sending a message does not collapse what the operator was reading

- **WHEN** the operator is reading an expanded turn and submits a new message
- **THEN** that turn remains expanded when the new turn appears

#### Scenario: Every turn can be folded

- **WHEN** a conversation contains a single turn
- **THEN** a control to fold that turn is available

#### Scenario: A manual fold survives new turns

- **WHEN** the operator folds a turn and a new turn is then appended
- **THEN** the folded turn remains folded

---

### Requirement: The operator's own messages are neutral, not accented

An operator message SHALL be distinguished from an agent message by placement and by neutral
surface treatment. It MUST NOT be tinted with the interface's chromatic accent colour, which is
reserved for focus and selection state.

#### Scenario: The operator's message carries no accent hue

- **WHEN** an operator message is rendered in the conversation
- **THEN** its background and border derive from the neutral surface and border scales
- **AND** neither derives from the accent colour

---

### Requirement: The composer is separated from the conversation by its border alone

The composer surface SHALL be distinguished from the page ground plane by its border and its own
surface colour. It MUST NOT be surrounded by a shadow, gradient, or fill that reads as a second,
darker region enclosing it.

#### Scenario: No enclosing dark region

- **WHEN** the composer is displayed against the conversation background
- **THEN** no shadow or gradient draws a darker area around it
- **AND** its separation is carried by its border and surface colour

---

### Requirement: A conversation opens at its most recent activity

Opening or switching to a conversation SHALL place the view at its newest entry, and SHALL resume
following new output.

The most recent activity is what an operator opening a conversation is looking for; landing on the
oldest entry of a long history buries it.

#### Scenario: Opening a conversation with history

- **WHEN** the operator opens a conversation that already has entries
- **THEN** the view is positioned at the newest entry

#### Scenario: Switching conversations

- **WHEN** the operator switches from one conversation to another
- **THEN** the newly shown conversation is positioned at its newest entry
- **AND** following of new output is active

---

### Requirement: Following tracks the entries the conversation renders

Whether the view follows new output SHALL be determined by the conversation entries actually
displayed, not by any other stream.

Following that observes a different source than the one being rendered will either fail to move when
content arrives or move when nothing visible has changed.

#### Scenario: New conversation content is followed

- **WHEN** the view is at the bottom and a new entry is added to the conversation
- **THEN** the view moves to keep the newest entry visible

---

### Requirement: A suspended conversation offers a way back to the newest entry

While following is suspended, the conversation SHALL offer a control that returns the view to the
newest entry and resumes following.

That control SHALL appear only while following is suspended. It is not a toggle: it expresses
"return me to the newest entry", and following remains governed by scroll position.

#### Scenario: The control appears only when suspended

- **WHEN** the view is following new output
- **THEN** no return-to-newest control is shown

#### Scenario: The control returns and resumes

- **WHEN** following is suspended and the operator activates the return-to-newest control
- **THEN** the view moves to the newest entry
- **AND** following resumes

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

Beyond a fixed number of conversations, the recency list SHALL place the remainder behind an
explicit expander that states how many are hidden, and SHALL offer a way back to the capped list
once expanded. The limit applies per project, since this view has no agent to apply it per.

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

#### Scenario: The recency list is capped per project

- **WHEN** a project has more conversations than the recency view's display limit
- **THEN** an expander states how many further conversations exist
- **AND** activating it lists them
- **AND** a control returns the list to its capped length

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

### Requirement: Starting a conversation is a navigation action with a dedicated surface

Starting a new conversation SHALL be initiated from navigation and SHALL open a surface whose
composer is the primary element, rather than an empty transcript.

A conversation started from an agent's row SHALL open with that agent already selected. That
selection is a default and not a binding: the surface SHALL let the operator retarget the unsent
message to any other agent in the project, and the message SHALL then go to the agent they chose.
A conversation started from the recency view, where no agent is implied, SHALL require the
operator to choose the agent on that surface before the first message can be sent.

The surface SHALL lead with a prominent question naming the bound agent. Where no agent is bound
that question SHALL instead ask which agent should take the work, so the line states what has to
happen next rather than sitting above a separate instruction.

No conversation record SHALL be created until the first message is sent, so an abandoned start
leaves nothing behind.

#### Scenario: Starting from an agent selects the agent

- **WHEN** the operator starts a conversation from an agent's row menu
- **THEN** the new-conversation surface opens with that agent already selected
- **AND** no agent choice is required

#### Scenario: A pre-selected agent can still be changed

- **WHEN** the operator started from one agent's row menu and then chooses a different agent
- **THEN** the surface retargets to the agent they chose
- **AND** the first message goes to that agent
- **AND** anything already typed is kept

#### Scenario: The surface leads by naming the agent

- **WHEN** the new-conversation surface opens bound to an agent
- **THEN** its leading question names that agent

#### Scenario: With no agent bound, the leading question asks for one

- **WHEN** the new-conversation surface opens with no agent bound
- **THEN** its leading question asks which agent should take the work
- **AND** choosing one changes the question to name that agent

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

### Requirement: The queue-routing contract binds peer delivery to the sender's conversation


A peer message that names no recipient conversation SHALL be delivered to the recipient conversation
bound to the sending conversation, creating that binding on first use.

This capability already requires that *"an outbound peer message SHALL carry its sender conversation,
and its recipient queue entry SHALL carry the recipient conversation selected by the queue-routing
contract"*, but the queue-routing contract is defined nowhere. This requirement defines it.

The binding is keyed on the sending conversation and the recipient agent. It is durable: every
later message from the same sending conversation to the same recipient reaches the same recipient
conversation.

Delivery MUST NOT be selected by recency. Omitting a recipient conversation is the ordinary path,
because a sender does not hold the recipient's conversation identifiers, so a recency rule governs
almost all peer traffic rather than an exceptional case. Observed consequence: three messages of one
exchange between two agents were delivered into three unrelated conversations of the recipient, one
of them titled for an unrelated file-creation task.

A recipient conversation created by this contract carries `origin: peer`.

#### Scenario: A first message binds a recipient conversation

- **WHEN** an agent sends a peer message from a conversation that has no binding to that recipient
- **THEN** a recipient conversation is created and bound to the sending conversation
- **AND** the queue entry carries that recipient conversation

#### Scenario: Later messages from the same conversation reach the same thread

- **WHEN** the same sending conversation sends another message to the same recipient
- **THEN** the queue entry carries the previously bound recipient conversation
- **AND** no further recipient conversation is created

#### Scenario: Separate sending conversations reach separate threads

- **WHEN** one agent sends peer messages to the same recipient from two different conversations
- **THEN** each is delivered to a different recipient conversation
- **AND** neither is selected by which conversation the recipient touched most recently

#### Scenario: The recipient's unrelated activity does not change delivery

- **WHEN** the recipient becomes active in a conversation unrelated to the binding
- **AND** the sender then sends another message from the bound sending conversation
- **THEN** delivery still reaches the bound recipient conversation

### Requirement: Traffic with no sending conversation binds to its sender identity


A message originating from a source that has no conversation SHALL be delivered to a recipient
conversation bound to that source's identity.

Hub-originated and scheduler-originated messages have no sending conversation, so the binding above
has no key. Binding them to the sender's identity gives one durable thread per source and recipient,
and leaves no path on which recency routing survives.

#### Scenario: System-originated messages reach a stable thread

- **WHEN** the Hub or the scheduler sends a message to an agent
- **THEN** it is delivered to the recipient conversation bound to that source
- **AND** later messages from that source reach the same conversation

### Requirement: An archived thread is handled according to who selected it


Delivery to an archived recipient conversation SHALL be refused when the sender named it, and SHALL
continue into a successor when the binding resolved it.

An agent that explicitly names an archived conversation has made an error it can correct, and is
already refused with its content returned so it need not reconstruct the message. An agent whose
message was routed to a thread the operator archived made no such choice, and refusing it would
penalise the sender for an operator action.

#### Scenario: A named archived conversation is refused

- **WHEN** a sender names a recipient conversation that is archived
- **THEN** the send is refused
- **AND** the refusal returns the message content

#### Scenario: A bound archived conversation continues into a successor

- **WHEN** the binding resolves to a recipient conversation the operator archived
- **THEN** a successor recipient conversation is created with `origin: peer`
- **AND** the binding moves to that successor
- **AND** the message is delivered rather than refused

### Requirement: Existing conversations bind on next use rather than by backfill


Peer bindings SHALL be established when a conversation next sends, and historical traffic SHALL NOT
be reassigned.

Traffic delivered under recency routing is already distributed across unrelated conversations, so
reconstructing which recipient conversation a past message "belonged" to would be a guess. Leaving
it in place keeps the record honest.

#### Scenario: A conversation with prior traffic binds on its next message

- **WHEN** a conversation that sent peer messages before this contract sends another
- **THEN** a binding is established at that point
- **AND** previously delivered messages remain in the conversations that received them
