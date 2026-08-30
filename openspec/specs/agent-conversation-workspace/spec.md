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

The conversation header SHALL expose fold-all and, while the agent is running, stop beside the
current turn's state. The resting composer SHALL expose only submit, the active-agent indicator,
and context usage.

New conversation, conversation selection, durable handoff, and agent details SHALL be reachable
from one overflow menu that is fully operable by keyboard.

An action that is unavailable SHALL be presented disabled with its reason rather than omitted, so
that the menu's contents do not shift between agents.

#### Scenario: The resting control set is minimal

- **WHEN** a conversation is open and the agent is idle
- **THEN** the composer exposes submit, the active-agent indicator, and context usage
- **AND** the header exposes fold-all when the conversation has more than one turn
- **AND** no provider-session selector, handoff button, or scroll toggle is exposed on the surface

#### Scenario: Stop appears with the running state

- **WHEN** the agent is running
- **THEN** a stop control is visible in the header beside the running-state indication
- **AND** no stop control is duplicated in the composer

#### Scenario: The overflow menu is operable by keyboard alone

- **WHEN** the operator opens the overflow menu and moves through it using the keyboard
- **THEN** new conversation, conversation selection, handoff, and agent details are each reachable
  and activatable
- **AND** dismissing the menu returns focus to its trigger

#### Scenario: An unavailable action is disabled with its reason

- **WHEN** an action such as handoff is unavailable for the current agent
- **THEN** the action remains in the overflow menu in a disabled state
- **AND** its reason is available to the operator

#### Scenario: Agent details do not replace the conversation

- **WHEN** the operator activates agent details from the overflow menu
- **THEN** details for the current agent open without unmounting or navigating away from the
  conversation
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
bound to the sending conversation's **line of work**, creating that binding on first use.

This capability already requires that *"an outbound peer message SHALL carry its sender conversation,
and its recipient queue entry SHALL carry the recipient conversation selected by the queue-routing
contract"*, but the queue-routing contract is defined nowhere. This requirement defines it.

The binding is keyed on the sending conversation and the recipient agent. It is durable: every
later message from the same sending conversation to the same recipient reaches the same recipient
conversation.

A conversation's **line of work** is itself together with every conversation it succeeds or is
succeeded by through checkpoint cutover. Matching on the line rather than on a single conversation
identifier is what keeps a correspondent reaching the same thread after either side has been cut
over; a cutover replaces the identifier an existing binding was written against, so an identifier
match alone silently opens a new thread at the handover.

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

#### Scenario: The sender's own cutover does not open a new recipient thread

- **WHEN** a sending conversation bound to a recipient thread is cut over to a successor
- **AND** the agent sends a further message to that recipient from the successor
- **THEN** delivery reaches the already-bound recipient conversation
- **AND** no further recipient conversation is created

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

### Requirement: Composed text begins at the composer's leading edge

The composer SHALL present its text area on its own row, occupying the full width of the composer
surface. No control SHALL precede the text area on that row.

Controls belonging to the composer SHALL occupy a control row beneath the text area.

#### Scenario: Text starts at the leading edge

- **WHEN** the operator focuses the composer and types
- **THEN** the text begins at the composer surface's leading edge, inset only by the surface's own
  padding

#### Scenario: The text area keeps the full measure at a narrow viewport

- **WHEN** the conversation is displayed at a narrow viewport
- **THEN** the text area's width is the composer surface's width less its padding
- **AND** no control reduces the width available to text

#### Scenario: Controls are reachable beneath the text

- **WHEN** the composer is displayed
- **THEN** the agent target control and the send control are presented in a row beneath the text
  area

### Requirement: The composer control row is an extensible pair of slots

The composer's control row SHALL be composed of a leading slot and a trailing slot. The trailing
slot SHALL hold the send control. The leading slot SHALL hold target and per-turn controls.

Adding a control to either slot MUST NOT require changing the composer's layout.

#### Scenario: Controls are added without relayout

- **WHEN** a further per-turn control is added to the leading slot
- **THEN** the composer's text area, autogrow behaviour, and send control are unchanged

#### Scenario: Existing composer behaviour survives the layout change

- **WHEN** the composer is presented as a column
- **THEN** draft persistence, autogrow within bounds, the trigger menu, submission on Enter, and
  input while the agent is running all behave as previously specified

### Requirement: The conversation is a single plane, not stacked boxes

The conversation SHALL read as one continuous surface. Its header and the region containing its
composer MUST NOT be drawn as filled bands closed by dividing rules.

The header SHALL sit on the same ground plane as the stream, separating itself from scrolled content
by translucency rather than by a fill and a border. The transition from the stream to the composer
region SHALL be a fade to the ground plane rather than a drawn edge.

#### Scenario: No band encloses the header

- **WHEN** an agent conversation is open
- **THEN** the header carries no fill distinct from the ground plane and no dividing rule beneath it

#### Scenario: No band encloses the composer

- **WHEN** an agent conversation is open
- **THEN** the region containing the composer carries no fill distinct from the ground plane and no
  dividing rule above it

#### Scenario: Scrolled content stays legible behind the header

- **WHEN** the operator scrolls the stream upward beneath the header
- **THEN** the header remains readable and the content passing behind it does not compete with it

### Requirement: The composer is the conversation's only lifted surface

The composer SHALL be presented as a surface lifted above the ground plane: its own fill, its own
outline, a soft shadow, and the application's content radius. It SHALL indicate focus by treating
the whole surface, not only its text area.

No other element of the conversation region SHALL be lifted in the same way.

#### Scenario: The composer reads as lifted

- **WHEN** an agent conversation is open
- **THEN** the composer is bounded by its own surface, outline, shadow, and content radius

#### Scenario: Focus is expressed on the surface

- **WHEN** the operator focuses the composer's text area
- **THEN** the composer surface indicates focus

#### Scenario: Nothing else competes with it

- **WHEN** the conversation region is displayed
- **THEN** the header, banners, and continuity line are not drawn as lifted surfaces

### Requirement: Turn-level controls sit with the turn's state

Turn-level controls SHALL be presented in the conversation header, beside the agent's identity and
run state. These are the controls that fold the conversation's turns and stop a running turn.

Lower-frequency conversation actions — switching or starting a conversation, preparing a handoff,
and opening agent details — SHALL remain in an overflow menu.

#### Scenario: Stopping a turn is immediate

- **WHEN** a turn is running
- **THEN** a control to stop it is visible in the header beside the running-state indication
- **AND** reaching it requires no menu

#### Scenario: Folding is immediate

- **WHEN** a conversation has more than one turn
- **THEN** a control to fold its turns is visible in the header

#### Scenario: Infrequent actions stay behind the menu

- **WHEN** the operator looks for conversation switching, handoff, or agent details
- **THEN** they are found in the overflow menu rather than on the surface

### Requirement: The stream is bounded to the reference measure

Conversation entries SHALL be laid out in a centred column bounded to the measure and gutters of the
approved design mock, with the mock's spacing between entries.

#### Scenario: The column matches the reference

- **WHEN** the conversation is displayed at a wide viewport
- **THEN** entries are centred within the mock's bounded measure rather than filling the viewport
- **AND** the spacing between entries matches the mock

### Requirement: Conversation disclosures respond to the pointer

The work disclosure and the folded-turn control SHALL present the hover and pressed treatments
required of every activatable element, and the work disclosure SHALL be drawn as a bounded surface
rather than as an outline alone.

#### Scenario: The work disclosure answers the pointer

- **WHEN** the operator hovers the work disclosure's summary
- **THEN** it takes on a hover treatment
- **AND** its expanded and collapsed states are distinguishable at a glance

#### Scenario: A folded turn answers the pointer

- **WHEN** the operator hovers a folded turn
- **THEN** it takes on a hover treatment indicating it can be reopened

### Requirement: Repeated delivery failure does not wedge an agent

The system SHALL return a failed run's input to the queue however that run failed, SHALL count how many times a queued input has failed to be delivered, and SHALL stop retrying it before it can block an agent indefinitely.

When a run fails before it completes, the input it was carrying returns to the queue so nothing is
lost. This SHALL hold for every abnormal ending, not only for those where the runtime never started.
A runtime that dies once the turn is under way is the failure most likely to occur, and returning
input only for the failures that happen earlier means the operator's message is consumed, never
retried, never given up on, and never reported — indistinguishable from never having been sent.

A run the operator deliberately stopped SHALL NOT return its input. The operator stopped the turn
knowing what it was carrying.

A run failed because the runtime reported a different provider session than the one the conversation
is bound to SHALL NOT return its input either. That failure is raised after the turn has run: the
work was done and its output delivered, so the input was processed rather than lost, and handing it
back would make the agent repeat a completed turn. Returning it would also defeat the check that
raised it — repeated failure gives up the conversation's provider session, so a later attempt would
adopt the very session the check refused, and a runtime that reports the wrong session would
overwrite the binding by being retried.

A returned input keeps its place in the queue and its binding to the conversation it arrived on, and
the queue is served in arrival order — so an input whose delivery kills the runtime is served again
immediately, and every later input, including a request to start a fresh conversation, waits behind
the one doing the killing. Nothing distinguishes an input returned five times from one that has
never been tried.

After repeated failure the system SHALL stop resuming the conversation's existing provider session
and start a new one, so that a provider session which cannot be resumed does not make the input
undeliverable forever.

After further failure the system SHALL stop attempting delivery, record why it gave up, and report
it to the operator. Retrying without limit is indistinguishable from being stuck, and an agent that
never accepts new input is worse than a message that was dropped loudly.

An input the system has given up on SHALL still name the run that was carrying it, so the operator
can find what happened to their message.

An input that is still being retried SHALL remain bound to its conversation. An input belonging to
no conversation cannot be scheduled at all, which would replace a visible wedge with a silent one.

Returning an input to the queue SHALL cause the system to attempt its delivery again without
requiring any further operator action. A limit on attempts protects nobody if nothing consumes the
attempts; an input left queued until an unrelated request happens to drain it is retried by
coincidence rather than by design.

Where a run's input has been returned, the system SHALL NOT report that run as having abandoned the
work it was bound to. The work is about to be handed to another run, so nothing has been dropped.

Where nothing else explains why an agent is not working, the wait SHALL be reported in terms of the
failed attempts.

#### Scenario: A returned input counts the attempt

- **WHEN** a run fails and its input returns to the queue
- **THEN** the input records that a delivery attempt failed

#### Scenario: A runtime that dies mid-turn returns its input

- **WHEN** a run's runtime ends abnormally after the turn has begun
- **THEN** the input it was carrying returns to the queue
- **AND** the attempt is counted

#### Scenario: A completed run keeps its input

- **WHEN** a run completes
- **THEN** its input is not returned to the queue

#### Scenario: A stopped run keeps its input

- **WHEN** the operator stops a run
- **THEN** its input is not returned to the queue

#### Scenario: A run failed over its provider session keeps its input

- **WHEN** a run fails because the runtime reported a different provider session than the one bound
- **THEN** its input is not returned to the queue
- **AND** the conversation's binding is unchanged

#### Scenario: A conversation that cannot be resumed is started afresh

- **WHEN** an input has failed to be delivered twice
- **THEN** the next delivery starts a new provider session rather than resuming the old one

#### Scenario: The system gives up and says so

- **WHEN** an input has failed to be delivered three times
- **THEN** it is no longer delivered
- **AND** the reason it was given up on is recorded
- **AND** the operator is told

#### Scenario: Giving up unblocks the agent

- **WHEN** an input the system has given up on was blocking the queue
- **THEN** a later input for the same agent is delivered

#### Scenario: A dropped input names the run that was carrying it

- **WHEN** the system gives up on an input
- **THEN** the record still names the run it was last delivered to

#### Scenario: A returned input is retried without being asked for

- **WHEN** a run fails and its input returns to the queue
- **THEN** the system attempts to deliver it again
- **AND** no operator action is required to make that happen

#### Scenario: A run whose input was returned is not reported as abandoning its work

- **WHEN** a run bound to a task fails and its input returns to the queue
- **THEN** the run is not reported as having left that task's work behind

#### Scenario: A run that dropped its input is still reported

- **WHEN** a run bound to a task fails and none of its input returns to the queue
- **THEN** the run is reported as having left that task's work behind

### Requirement: A re-delivered turn says the earlier attempt was cut off

Input delivered to an agent after an earlier delivery failed SHALL say so, naming which attempt this is.

An agent handed the same instruction a second time has no way to tell that it is a second time. It
may find its own half-finished work in the checkout and read it as someone else's, or repeat work
that is already done, or treat a partial state as the starting state. The system knows the attempt
count and the agent does not, and the cost of that asymmetry is paid in wasted turns.

What to do about half-finished work SHALL be left to the agent. It depends on what the work was, and
a general instruction to check or to redo would be wrong often enough to be worse than the bare fact.

Input on its first delivery SHALL carry no such note, so that the ordinary case is unchanged.

#### Scenario: A second delivery is announced as one

- **WHEN** input is delivered to an agent after one failed attempt
- **THEN** the delivered turn states that an earlier attempt did not finish
- **AND** it names which attempt this is

#### Scenario: A first delivery is unchanged

- **WHEN** input is delivered to an agent for the first time
- **THEN** the delivered turn says nothing about earlier attempts

#### Scenario: Only the retried input is annotated

- **WHEN** a turn carries both a retried input and one never tried before
- **THEN** only the retried one states that an earlier attempt did not finish

### Requirement: Message-level conversation entries render Markdown, safely

Operator input, agent text output, and peer traffic SHALL be rendered as Markdown — fenced code,
emphasis, lists, links, and tables render as their formatted equivalents rather than as literal
syntax characters. A single newline with no following blank line SHALL render as a line break within
the same paragraph, not be collapsed into it.

The renderer MUST NOT interpret raw HTML found in entry content as markup. Content that is not valid
or recognized Markdown SHALL render as plain text, visually equivalent to rendering it with no
Markdown syntax present at all.

This requirement covers message-level text only. Tool-call content (a tool's input or output, and
its summary label) is governed by the tool-call formatting requirement below and is unaffected by
this one.

#### Scenario: Formatting syntax renders as formatting

- **WHEN** a conversation entry's content contains Markdown syntax (a fenced code block, a bulleted
  list, bold or italic emphasis, or a link)
- **THEN** it is rendered as the corresponding formatted element
- **AND** no literal Markdown syntax character is visible in the rendered output

#### Scenario: A single newline is preserved as a line break

- **WHEN** an entry's content contains two lines separated by exactly one newline, with no blank
  line between them
- **THEN** both lines are rendered with a visible break between them
- **AND** they are not collapsed into a single unbroken line

#### Scenario: Raw HTML in content is never interpreted as markup

- **WHEN** an entry's content contains a literal HTML tag
- **THEN** the tag's characters are rendered as visible text
- **AND** no corresponding DOM element is created from it

#### Scenario: Plain text is unaffected

- **WHEN** an entry's content contains no Markdown syntax
- **THEN** its rendered appearance is unchanged from rendering it as plain text

### Requirement: A tool call is formatted by what kind of tool it was

A tool-call entry in the conversation timeline SHALL be presented with an icon and a label specific
to the tool it names, drawn from a fixed mapping keyed on the tool's recorded name. A tool name the
mapping does not recognize SHALL fall back to a generic icon and label rather than rendering no icon
or throwing.

Where a tool call's recorded input can be parsed as carrying both a prior and a new value for the
same content — the shape a file-editing tool call carries — its expanded view SHALL render that
change as a diff, distinguishing added and removed content, rather than as two independent blocks of
raw text.

Where a tool call's recorded input cannot be parsed this way, was truncated before being recorded, or
does not carry both values, its expanded view SHALL render the existing raw input and output text
unchanged. A diff MUST NOT be attempted against content known to have been truncated.

#### Scenario: A recognized tool shows its own icon and label

- **WHEN** a tool-call entry names a tool the mapping recognizes
- **THEN** it is rendered with that tool's icon and label
- **AND** a different recognized tool in the same conversation renders with a different icon and
  label

#### Scenario: An unrecognized tool falls back, not blank

- **WHEN** a tool-call entry names a tool the mapping does not recognize
- **THEN** it is rendered with the fallback icon and label
- **AND** rendering does not fail

#### Scenario: An edit-shaped tool call renders as a diff

- **WHEN** a tool-call entry's recorded input parses to an object carrying both a prior and a new
  value for the same content
- **THEN** its expanded view renders the change as a diff
- **AND** added and removed content are visually distinguished from each other and from unchanged
  content

#### Scenario: A malformed or truncated tool call falls back to raw text

- **WHEN** a tool-call entry's recorded input cannot be parsed as carrying both a prior and a new
  value, or is recorded as truncated
- **THEN** its expanded view renders the existing raw input and output text
- **AND** no diff is attempted against it

### Requirement: A reply continues the conversation it is replying to

When a peer message names no recipient conversation and no binding resolves forward, delivery SHALL
resolve the sending conversation's own binding in reverse: if the sending conversation is bound to a
conversation whose owning agent is the recipient, the message SHALL be delivered into that
conversation's line of work rather than into a newly created conversation.

Delivery resolves in a fixed order — an explicitly named conversation, then the forward binding,
then this reverse rule, then creating a conversation. The forward binding is tried first so that
every delivery that resolves today resolves identically; the reverse rule SHALL only apply where a
conversation would otherwise have been created.

Without this rule the binding is one-directional and a reply cannot find the thread it answers.
Observed consequence: three messages between two agents produced three conversations, and a later
exchange in the same session produced three more.

#### Scenario: A reply reaches the thread it is answering

- **WHEN** an agent receives a peer message into a bound conversation
- **AND** replies to the sender from that conversation, naming no recipient conversation
- **THEN** the reply is delivered into the sending agent's original conversation
- **AND** no conversation is created

#### Scenario: An exchange settles into one thread per participant

- **WHEN** two agents exchange several messages, each replying from the conversation it received in
- **THEN** every message after the first reaches an existing conversation
- **AND** exactly two conversations exist for the exchange

#### Scenario: A reply to a third agent does not continue an unrelated thread

- **WHEN** an agent receives a message from a first agent into a bound conversation
- **AND** sends a message to a second agent from that conversation
- **THEN** the reverse rule does not apply, because the bound conversation is not owned by the
  recipient
- **AND** a conversation is created for the second agent, bound to the sending conversation

#### Scenario: A reply continues into an operator-origin conversation

- **WHEN** an agent is asked something in a conversation the operator started
- **AND** delegates to a second agent, which replies naming no recipient conversation
- **THEN** the reply is delivered into that operator-origin conversation
- **AND** the entry records the second agent as its originating agent

#### Scenario: Continuation survives the replying side's cutover

- **WHEN** the conversation a reply would continue into has been cut over to a successor
- **THEN** the reply is delivered into the newest open conversation of that line of work
- **AND** no conversation is created

#### Scenario: A closed line of work does not capture a reply

- **WHEN** the conversation a reply would continue into is archived and has no open successor
- **THEN** the reverse rule does not resolve
- **AND** a conversation is created, bound to the sending conversation

### Requirement: An agent can start a new thread deliberately

The outbound message surface SHALL accept an explicit request to start a new recipient conversation,
defaulting to continuing. When the request is made, delivery SHALL create a conversation bound to
the sending conversation without consulting either the forward or the reverse binding, and later
messages on that line SHALL reach the newly created conversation.

A new thread otherwise starts only at a checkpoint cutover. Without an explicit request there is no
way for an agent to separate a genuinely new line of work from the one it is already holding, which
is the only legitimate reason to open a thread outside a cutover.

Requesting a new thread while also naming a recipient conversation SHALL be refused. Naming a
conversation selects an existing thread and requesting a new one creates one; honouring either
silently would discard a caller's stated intent.

#### Scenario: An explicit request creates a thread

- **WHEN** an agent sends a peer message asking for a new thread
- **AND** a binding to that recipient already exists
- **THEN** a conversation is created and bound to the sending conversation
- **AND** the message is delivered into it rather than into the previously bound conversation

#### Scenario: The new thread becomes the bound one

- **WHEN** an agent has started a new thread with a recipient
- **AND** sends a further message to that recipient from the same conversation, without asking again
- **THEN** delivery reaches the most recently created conversation
- **AND** no conversation is created

#### Scenario: Continuing is the default

- **WHEN** an agent sends a peer message without asking for a new thread
- **THEN** delivery resolves by binding, forward then reverse
- **AND** a conversation is created only when neither resolves

#### Scenario: Naming a conversation and asking for a new one is refused

- **WHEN** an agent sends a peer message that both names a recipient conversation and asks for a new
  thread
- **THEN** the message is refused
- **AND** no conversation is created and no message is delivered

### Requirement: An outbound peer message renders folded, showing its subject

An outbound peer message SHALL render folded by default, showing its recipient and its subject on a
single line, and SHALL expand to its full content when the operator asks for it.

An outbound message is the agent's own act, not something addressed to the operator reading the
conversation. It is already announced twice: the `send_message` call renders as a tool row, and the
message renders again as a full bubble carrying the entire body. In a conversation where an agent
delegates several times, the bubbles crowd out the agent's own replies to the operator.

The folded line SHALL show the message's **subject**, which the outbound message surface already
requires as a short summary line and which the conversation currently discards. A fold that shows
only the recipient's name is not sufficient: several messages to the same recipient would fold to
identical rows, which is the failure the tool-row detail line already exists to prevent.

This does not conflict with the requirement that *a turn's folded state is set by the operator,
never by its position*. That requirement governs **turns** — an agent's own reply to the operator —
and a peer message is not a turn. Foldedness here is derived from the kind of entry, never from
where the entry sits in the conversation, and appending an entry SHALL NOT change the folded state
of any other.

An operator who expands an outbound message SHALL keep it expanded as the conversation grows, on
the same terms as any other manually expanded entry.

Inbound peer messages are unaffected. They are addressed to the agent whose conversation is being
read, and they carry content the operator has not otherwise seen.

#### Scenario: An outbound message is folded when it appears

- **WHEN** an agent sends a peer message from a conversation being read
- **THEN** the outbound entry renders folded
- **AND** the folded line shows the recipient and the message's subject

#### Scenario: The subject distinguishes messages to the same recipient

- **WHEN** an agent sends two peer messages with different subjects to the same recipient
- **THEN** the two folded lines differ

#### Scenario: Expanding shows the message

- **WHEN** the operator expands a folded outbound message
- **THEN** its full content is rendered

#### Scenario: An expanded outbound message stays expanded

- **WHEN** the operator expands an outbound message and further entries are appended
- **THEN** it remains expanded

#### Scenario: An inbound message is not folded

- **WHEN** a peer message arrives into the conversation being read
- **THEN** it renders with its content visible, as it does today

### Requirement: The hop budget bounds delivery, not only admission

An inbound queue entry whose hop depth exceeds the project's hop budget SHALL NOT be delivered to an
agent's turn, regardless of what other entries are delivered in the same turn.

A turn's depth SHALL be the depth of the entry that admitted the turn. It SHALL NOT be derived from
the lowest depth among the entries delivered, and a turn SHALL NOT be recorded at a depth lower than
that of any entry it delivers.

#### Scenario: An over-budget entry is not carried by an in-budget one

- **GIVEN** a project whose hop budget is exceeded by one queued agent-originated entry
- **AND** a second entry in the same conversation that is within budget
- **WHEN** the agent's turn starts
- **THEN** only the within-budget entry is delivered
- **AND** the over-budget entry remains queued

#### Scenario: An operator message does not release a blocked chain

- **GIVEN** an agent-originated entry held back because its hop depth exceeds the budget
- **WHEN** the operator sends a message into the same conversation
- **THEN** the operator's message is delivered
- **AND** the over-budget entry remains queued
- **AND** the resulting turn's depth is the operator message's depth

#### Scenario: The depth counter does not run backwards

- **GIVEN** a turn admitted by an entry at a given hop depth
- **WHEN** the agent sends a message during that turn
- **THEN** the resulting entry's hop depth is greater than the admitting entry's depth

### Requirement: An entry held back by the hop budget is visible and has a stated exit

The Hub SHALL report an entry that is queued because its hop depth exceeds the budget as held for
that reason, distinguishably from an entry queued for any other reason.

The operator SHALL be able to release such an entry deliberately. Releasing it SHALL re-base its
depth so that it and the chain it continues start again from the operator's own depth, and SHALL be
recorded as an operator decision.

The operator SHALL also be able to discard such an entry. An entry held by the budget SHALL NOT be
left with no way forward and no way out.

#### Scenario: The operator releases a held chain

- **GIVEN** an entry held back because its hop depth exceeds the budget
- **WHEN** the operator chooses to continue that chain
- **THEN** the entry is delivered on the agent's next turn
- **AND** the decision to release it is recorded
- **AND** messages the agent sends during that turn are within budget again

#### Scenario: The operator discards a held chain

- **GIVEN** an entry held back because its hop depth exceeds the budget
- **WHEN** the operator discards it
- **THEN** it is withdrawn and never delivered

#### Scenario: Raising the budget releases what it was holding

- **GIVEN** one or more entries held back because their hop depth exceeds the budget
- **WHEN** the operator raises the project's hop budget above those depths
- **THEN** those entries become deliverable without any further operator action

### Requirement: A review turn is given a checkout of the code under review

A review turn's workspace SHALL be a git checkout of the exact commit the reviewed work's evidence
names, and SHALL NOT be the reviewing agent's own working checkout.

The reviewing agent SHALL be able to read every file in that checkout, search it, and execute its
test suite. It SHALL NOT be able to reach the authoring agent's working checkout, which remains
outside its workspace boundary.

The checkout SHALL be detached from any branch, so that git itself reports the reviewing role and
an accidental commit is orphaned rather than accumulated.

The Hub SHALL provide the same shared dependencies to a review checkout that it provides to a
working checkout. A review checkout that cannot run the project's tests does not satisfy this
requirement.

#### Scenario: A reviewer reads code that is not on the main branch

- **GIVEN** an authoring agent has completed work on its own isolated checkout and recorded evidence naming a commit
- **AND** that commit has not been integrated into the project's main branch
- **WHEN** the Hub starts a review turn for a different agent
- **THEN** the reviewing agent's workspace contains that commit's version of the code
- **AND** the reviewing agent can read files the main branch does not contain

#### Scenario: A reviewer can run the tests it is asked to trust

- **GIVEN** a review turn whose workspace is a checkout of the commit under review
- **WHEN** the reviewing agent runs the project's test suite
- **THEN** the suite executes against the code under review
- **AND** the result is the reviewing agent's own observation rather than a claim it was given

#### Scenario: A reviewer cannot reach the author's working checkout

- **GIVEN** a review turn is in progress
- **WHEN** the reviewing agent attempts to read or write inside the authoring agent's working checkout
- **THEN** the attempt is refused as outside its workspace

#### Scenario: A review turn has exactly one workspace

- **GIVEN** a reviewing agent that also has a working checkout of its own
- **WHEN** it is given a review turn
- **THEN** its workspace for that turn is the review checkout alone
- **AND** its own working checkout is outside its workspace boundary for the duration of that turn

### Requirement: A review checkout names the commit the most recent evidence cites

The Hub SHALL resolve the commit for a review turn from the most recent evidence recorded for the
task under review.

Where earlier evidence for the same task names a different commit, the Hub SHALL state that in the
reviewing agent's turn context. It SHALL NOT silently present the newest commit as though it were
the only one.

#### Scenario: One piece of evidence

- **GIVEN** a task with a single piece of recorded evidence naming a commit
- **WHEN** a review turn begins
- **THEN** the review checkout is detached at that commit

#### Scenario: Evidence that names two different commits

- **GIVEN** a task with two pieces of recorded evidence naming different commits
- **WHEN** a review turn begins
- **THEN** the review checkout is detached at the commit named by the more recent evidence
- **AND** the reviewing agent is told that earlier evidence named a different commit

#### Scenario: A task with no evidence

- **GIVEN** a task that has reached completion with no recorded evidence
- **WHEN** a review turn is requested
- **THEN** no review checkout is created
- **AND** the reason states that there is no evidence naming a commit to review

### Requirement: A review checkout is bounded and reused

The Hub SHALL place a review checkout at a path it determines, keyed by the reviewing agent, and
SHALL reuse that path across successive reviews by the same agent rather than creating a new
location per review.

The reviewing agent SHALL NOT be required to construct, choose or be told a path by another agent.

#### Scenario: A second review reuses the same location

- **GIVEN** an agent that has already completed one review
- **WHEN** it is given a review turn for a different task
- **THEN** its review checkout is at the same path as before, now detached at the new commit

#### Scenario: The number of review checkouts is bounded by the roster

- **GIVEN** a project whose agents have performed many reviews
- **WHEN** the project's checkouts are enumerated
- **THEN** the number of review checkouts does not exceed the number of agents that have reviewed

### Requirement: A turn admits entries of one kind only

The system SHALL, where an agent's queue holds both a review entry and a work entry in the same
conversation, deliver a turn carrying only the controlling entry's kind — the same entry that
decides the turn's depth (see "The hop budget bounds delivery, not only admission"). An entry of the
other kind SHALL remain queued and SHALL be delivered on a later turn — held back, not refused and
not dropped, the same treatment an over-budget entry already gets.

#### Scenario: A turn admits only the controlling entry's kind

- **GIVEN** an agent's queue holds a review entry and a work entry in the same conversation
- **WHEN** the review entry is the earliest admitted
- **THEN** the delivered turn carries only the review entry
- **AND** the work entry remains queued

#### Scenario: The reverse arrival order gives the reverse outcome

- **GIVEN** an agent's queue holds a review entry and a work entry in the same conversation
- **WHEN** the work entry is the earliest admitted
- **THEN** the delivered turn carries only the work entry
- **AND** the review entry remains queued

#### Scenario: A deferred entry is not starved

- **GIVEN** an entry left queued because a turn admitted only the other kind
- **WHEN** the agent's next turn is scheduled
- **THEN** the deferred entry is delivered

### Requirement: A delivered turn carries a review or ordinary work, never both

The system SHALL refuse to start a turn whose queued input asks the agent both to review a task and
to work on a task. The refusal SHALL name both tasks and SHALL state that a turn has one subject.

A turn has one workspace. A turn asked to do both is given the review checkout, because that is what
preparing a review means — and is then bound to whichever task an ordering rule happens to select,
which need not be the one it is looking at. A run bound to work the agent was never shown is worse
than an unbound run: an unbound run is exempt from the check that asks whether it moved its task,
while this one fails that check against work it was never given.

This is defence in depth. The requirement above already keeps the normal scheduling path from ever
assembling a mixed batch; this refusal is what catches a caller that hands `queue_entry_ids` to the
trigger directly, bypassing that narrowing.

Refusing SHALL happen before the agent is started, so that no workspace is prepared and no turn is
delivered.

#### Scenario: A turn batching a review and a work item is refused

- **GIVEN** queued input containing an entry naming a task to review and an entry naming a different
  task to work on
- **WHEN** a turn is started from that input
- **THEN** the turn is refused
- **AND** the reason names both tasks and states that a turn has one subject
- **AND** no agent process is started

#### Scenario: A review batched with a work item naming the same task is still refused

- **GIVEN** queued input containing an entry naming a task to review and an entry naming that same
  task to work on
- **WHEN** a turn is started from that input
- **THEN** the turn is refused

#### Scenario: Several work items in one turn are still allowed

- **GIVEN** queued input containing more than one entry naming a task to work on and no review
- **WHEN** a turn is started from that input
- **THEN** the turn is delivered
- **AND** the run is bound to one of those tasks by the existing ordering rule

#### Scenario: A review alone is unaffected

- **GIVEN** queued input containing one or more entries naming the same task to review and no work
- **WHEN** a turn is started from that input
- **THEN** the turn is delivered with the review checkout
- **AND** the run is bound to the task under review

#### Scenario: Refusal leaves the input where it was

- **GIVEN** a turn refused for batching a review and ordinary work
- **WHEN** the operator inspects the agent's queue
- **THEN** the entries are still queued
- **AND** none is marked delivered

### Requirement: A request refused for what it asked is answered as refused

A request submitting input to an agent SHALL be answered as a failure, carrying the refused
condition's own status and its own sentence, where the system determines while handling it that the
input cannot be delivered because of what the request asked for.

It SHALL NOT answer such a request as accepted. An acknowledgement that carries the refusal inside
a field named for waiting, under a flag saying the request succeeded, tells the operator the
opposite of what happened, and is worse than no explanation: the operator has been given a reason
to wait for something that will never occur.

The refusal's status SHALL be the one the refused condition already carries, so that conditions the
system distinguishes — a request forbidden to this agent, a target in the wrong state, a runner with
no implementation — remain distinguishable to the caller. A single flattened status would discard
distinctions the system has already made correctly.

A refusal about **what was asked** SHALL be distinguished from a refusal about **the environment the
agent would run in**. The system deliberately accepts and holds input that cannot be delivered yet
because the environment is not ready — no runner is bound, the bound runner's program is not
installed, an isolated workspace could not be prepared — precisely so that repairing the environment
delivers it. Answering those as failures would discard input the system has promised to keep, and
would report as broken the behaviour that makes the repair worth performing. Input waiting for a turn
in flight, a queue another request has already drained, or a budget that will reset is likewise not
a failure.

#### Scenario: A submission refused for what it asked answers with the refusal

- **WHEN** an operator submits input to an agent
- **AND** the system determines the input cannot be delivered because of what the request asked for
- **THEN** the request is answered as a failure
- **AND** the answer carries the refused condition's own status
- **AND** the answer carries the refusal's own sentence

#### Scenario: A submission refused because the environment is not ready is still accepted

- **WHEN** an operator submits input to an agent
- **AND** delivery is refused because the environment the agent would run in is not ready
- **THEN** the request is answered as accepted
- **AND** the answer states the refusal's own sentence as what the input is waiting for
- **AND** the input remains queued, so that repairing the environment delivers it

#### Scenario: A submission that merely has to wait is still accepted

- **WHEN** an operator submits input to an agent
- **AND** delivery is deferred for a reason that can clear on its own
- **THEN** the request is answered as accepted
- **AND** the answer states what the input is waiting for

#### Scenario: A submission delivered by a concurrent drain is not reported as failed

- **WHEN** an operator submits input to an agent
- **AND** another delivery in progress takes that input before this request examines the queue
- **THEN** the request is answered as accepted

### Requirement: A refusal is reported only to the input it is about

Where the system refuses to start a turn, it SHALL attribute that refusal to the specific inputs the
refused turn would have carried, and SHALL report it only to a request that submitted one of them.

An agent's queue may hold input from several conversations, and the turn the system attempts is
built from the oldest eligible input, which is not necessarily the input the current request just
submitted. A refusal reported to whichever request happened to arrive describes a conversation the
caller did not ask about, cannot act on, and may not be permitted to see.

Where a request's own input was not part of the refused turn, the system SHALL report that the input
is waiting behind other input rather than repeating a refusal about it.

#### Scenario: A refusal about another conversation is not reported as this request's reason

- **WHEN** an operator submits input to an agent
- **AND** the system refuses a turn it was building from an older input belonging to another conversation
- **THEN** this request is answered as accepted
- **AND** the answer states that the input is waiting behind other input
- **AND** the answer does not carry the other conversation's refusal

### Requirement: A start is reported only to the input it is about

Where the system starts a turn in answer to a request naming one conversation, it SHALL report that request as started only where the started turn carried that conversation's input, and SHALL otherwise report that the input is waiting behind other input.

This is the start-direction counterpart of "A refusal is reported only to the input it is about",
and it exists for the same reason. An agent's queue may hold input from several conversations, and
the turn the system attempts is built from the oldest eligible input, which is not necessarily the
input the current request names. Reporting a start to whichever request happened to arrive describes
a turn in a conversation the caller did not ask about — and unlike a refusal, it is
indistinguishable from success, so the caller has no reason to look further. Someone watching the
conversation they named sees no run, no output and no error, and the next act available to them is
to ask again.

The response SHALL identify the conversation whose input the turn actually carried, so that a
request answered as waiting can be acted on rather than only retried.

Where the named conversation had no input queued at all, the answer SHALL say that rather than that
its input is waiting. "Waiting behind other input" describes input the system is holding; saying it
of a conversation that submitted none reports a queue position that does not exist, and directs the
caller to wait for a delivery that will never arrive.

Reporting SHALL NOT be corrected by changing which input is selected. The turn is the agent's and
its input is taken in arrival order; selecting a later input because a request names its
conversation would let that request overtake input that arrived first, and would leave a quiet
conversation waiting for as long as a busy one is asked about.

#### Scenario: The turn carried the named conversation's input

- **WHEN** a request names a conversation and the started turn carried that conversation's input
- **THEN** the request is answered as started
- **AND** the conversation identified as started is the one named

#### Scenario: The turn carried another conversation's input

- **WHEN** a request names a conversation and the started turn carried a different conversation's input
- **THEN** the request is not answered as started
- **AND** the answer states that the named conversation's input is waiting behind other input
- **AND** the answer identifies the conversation whose input the turn carried
- **AND** the named conversation's input remains queued

#### Scenario: The named conversation had nothing queued

- **WHEN** a request names a conversation that has no input queued
- **AND** the started turn carried another conversation's input
- **THEN** the request is not answered as started
- **AND** the answer states that the named conversation had nothing queued
- **AND** the answer does not state that its input is waiting behind other input

#### Scenario: No turn started

- **WHEN** a request names a conversation and no turn started
- **THEN** the request is not answered as started
- **AND** the answer states the reason no turn started
- **AND** no conversation is identified as started

#### Scenario: A diagnostic about a turn names the conversation the turn belongs to

- **WHEN** the system records that a turn did not start, in answer to an act addressed to one conversation
- **THEN** the record names the conversation the reason belongs to rather than the conversation addressed

### Requirement: The operator is told when the turn that began is not the one they asked for

The interface offering to start a conversation's queued work SHALL distinguish a turn that began in that conversation from one that began elsewhere, and SHALL identify the other conversation when it is not the one asked for.

Rendering the same confirmation for both outcomes leaves the operator watching a conversation where
nothing will appear. Because the control remains available, the act available to them is to press it
again, starting a further turn they did not ask for and did not observe.

#### Scenario: The turn began in the conversation on screen

- **WHEN** the started conversation is the one displayed
- **THEN** the interface confirms that this conversation is continuing

#### Scenario: The turn began in another conversation

- **WHEN** a turn began in a conversation other than the one displayed
- **THEN** the interface states that the displayed conversation's work is waiting behind other input
- **AND** identifies the conversation that began

#### Scenario: Nothing began

- **WHEN** no turn started
- **THEN** the interface states that nothing started
- **AND** gives the stated reason

### Requirement: Input refused for what it asked does not stay queued for retry

Input SHALL NOT remain queued for further delivery attempts where the request that submitted it has
been answered with a refusal about what that request asked for.

Retrying is pointless where nothing about the environment changing would alter the answer, and it is
worse than pointless once the operator has been told synchronously that the request failed: the
input goes on working behind them, and the report that the system gave up arrives later for a
request that already reported failure.

This SHALL NOT extend to input refused because the environment is not ready. That input stays queued
and keeps its existing delivery-attempt bookkeeping, because the repair that makes it deliverable is
exactly what the operator has been told to perform.

Input withdrawn this way SHALL NOT be reported as input the system gave up on after trying. Nothing
carried it — no turn was ever started for it — so there is no run for it to name and no attempt
count to report. The operator was told synchronously; a later report that the system stopped trying
would describe an effort that never happened.

Where the system has already told the operator that input is queued, and then withdraws it in the
same request, it SHALL report the withdrawal. An operator holding both an error and a queue that
still counts the input is being told two different things about one request, which is the same
failure this behaviour exists to remove.

#### Scenario: The queue agrees with the answer the operator was given

- **WHEN** a request is answered with a refusal about what that request asked for
- **THEN** the input that request submitted is no longer queued for delivery
- **AND** the record of why it will not be delivered names the refusal

#### Scenario: Input awaiting a repairable environment is still queued

- **WHEN** a request is answered as accepted because the environment the agent would run in is not ready
- **THEN** the input that request submitted remains queued for delivery

#### Scenario: The withdrawal is reported, and not as an abandonment

- **WHEN** a request is answered with a refusal about what that request asked for
- **AND** the system had already reported that request's input as queued
- **THEN** the system reports that the input has been withdrawn
- **AND** it does not report that it gave up on the input after failed delivery attempts

### Requirement: The operator reads why a submission was refused

Where a submission is answered with a refusal, the interface SHALL present the refusal's own
sentence to the operator.

Presenting only that a request failed, or only its status, replaces a wrong explanation with no
explanation. The operator's ability to see the stated reason is the outcome this behaviour exists
to produce; a correct status code that reaches a message the operator cannot read has not produced
it.

#### Scenario: A refused submission shows its reason

- **WHEN** a submission to an agent is refused
- **THEN** the operator is shown the refusal's own sentence

### Requirement: A delivery attempt is counted only where a delivery was attempted

The system SHALL NOT count a delivery attempt against queued input where nothing was delivered and
the reason nothing was delivered prevents the agent from running at all.

Input refused for a reason that prevents the agent from running **at all** SHALL NOT have a delivery
attempt counted against it, and SHALL NOT be given up on for that reason. No delivery was attempted:
the refusal was raised before anything carried it anywhere, and while the reason holds no other
input for that agent could have run in its place either, so giving up on this input buys nothing.
Counting it means the operator's own activity — sending another message, or asking the system to
start the work already waiting — consumes the allowance that exists to detect repeated failure, and
destroys input that nothing ever tried to deliver.

This SHALL NOT extend to a refusal that prevents only this input from being delivered. Where other
queued input could have run, the input at the head of the queue is in the way, and the system SHALL
go on counting its attempts and SHALL still give up on it at the limit.

Where the system gives up on input, the reason it records SHALL describe what actually happened to
that input. Input that was never carried anywhere has not failed to be delivered.

#### Scenario: Sending more input does not consume the earlier input's allowance

- **WHEN** an operator submits input to an agent whose environment is not ready
- **AND** the operator submits further input to the same agent
- **THEN** no delivery attempt is counted against the earlier input
- **AND** the earlier input remains queued

#### Scenario: The input is still there when the agent becomes able to run

- **WHEN** input has been waiting for an agent that cannot run at all
- **AND** the operator has submitted further input and asked the system to start the waiting work
- **AND** the operator then makes the agent able to run
- **THEN** every input they submitted is delivered
- **AND** none of it was discarded while they were making the agent able to run

#### Scenario: Asking the system to start waiting work does not destroy it

- **WHEN** input is waiting for an agent whose environment is not ready
- **AND** the operator asks the system to start the waiting work without submitting anything new
- **THEN** no delivery attempt is counted against that input
- **AND** the input remains queued

#### Scenario: Unrelated activity does not consume it either

- **WHEN** input is waiting for an agent whose environment is not ready
- **AND** another agent's turn ends, causing every queued agent to be re-evaluated
- **THEN** no delivery attempt is counted against that input

#### Scenario: A run that carried the input and failed still counts

- **WHEN** a run carrying queued input fails
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it

#### Scenario: A refusal about what was asked still counts

- **WHEN** a turn is refused because of what the queued input asked for
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it

#### Scenario: A refusal that blocks only this input still counts

- **WHEN** a turn is refused for a reason that would not prevent the agent's other queued input from
  being delivered
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it, so it cannot hold the queue indefinitely
