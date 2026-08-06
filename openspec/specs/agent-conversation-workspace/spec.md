# agent-conversation-workspace Specification

## Purpose

The AgentWeave conversation is the primary workspace surface: navigation reaches an agent's
conversation directly, the operator can keep talking to an agent while it is running, and the
composer is a bounded, draft-persisting input with a minimal always-visible control set and
everything else — new conversation, conversation selection, handoff, fold-all, agent details —
behind one keyboard-operable overflow menu. AgentWeave owns a durable `conversation_id` that exists
before any provider process starts and never changes across runs, retries, stops, or provider-session
binding; the provider session is nullable continuation data beneath it, never the operator-facing
identity.
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

Navigation SHALL present the current project as a named entry whose children are its agents.

Activating the project's name SHALL navigate to the project overview. Activating its expander SHALL
toggle the agent list without navigating. The two MUST be separately activatable.

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

New conversation, conversation selection, durable handoff, fold-all, and agent details SHALL be
reachable from one overflow menu that is fully operable by keyboard.

An action that is unavailable SHALL be presented disabled with its reason rather than omitted, so
that the menu's contents do not shift between agents.

#### Scenario: The resting control set is minimal

- **WHEN** a conversation is open and the agent is idle
- **THEN** the composer exposes submit, the active-agent indicator, and context usage
- **AND** exposes no provider-session selector, handoff button, fold-all control, or scroll toggle

#### Scenario: Stop appears only while running

- **WHEN** the agent is running
- **THEN** a stop control is additionally visible

#### Scenario: The overflow menu is operable by keyboard alone

- **WHEN** the operator opens the overflow menu and moves through it using the keyboard
- **THEN** new conversation, conversation selection, handoff, fold-all, and agent details are each reachable and activatable
- **AND** dismissing the menu returns focus to its trigger

#### Scenario: An unavailable action is disabled with its reason

- **WHEN** an action such as handoff is unavailable for the current agent
- **THEN** it is present in the menu, disabled, with the reason stated

#### Scenario: Agent details do not replace the conversation

- **WHEN** the operator activates agent details from the overflow menu
- **THEN** details for the current agent open without unmounting or navigating away from the conversation
- **AND** closing the details returns focus to the invoking control

### Requirement: Conversation identity is readable without exposing provider identity

The provider-session selection control SHALL be removed from the conversation surface. The current
AgentWeave conversation's continuity state SHALL remain visible as human-readable text, and
conversation selection SHALL be performed from the overflow menu. Normal navigation, URLs, history,
and drafts MUST use `conversation_id`; provider session IDs MAY appear only in details or diagnostic
surfaces.

#### Scenario: Continuity is readable at rest

- **WHEN** a conversation is continuing an existing session
- **THEN** its continuity state is readable as text on the resting surface

#### Scenario: Conversation selection works from the menu

- **WHEN** the operator selects a different AgentWeave conversation from the overflow menu
- **THEN** the conversation switches to it with the same effect the removed selector had

#### Scenario: Provider identity is hidden from normal conversation controls

- **WHEN** the operator inspects the resting surface and conversation picker
- **THEN** no provider session ID is shown as a conversation label or selection value
- **AND** provider binding remains available in agent details or diagnostics

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
