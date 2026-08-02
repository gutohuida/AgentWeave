## ADDED Requirements

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

Unsent composer text SHALL be retained per agent conversation across navigation away and back and
across a page reload, SHALL be cleared on successful submission, and MUST NOT be visible in or
overwritten by another agent's conversation.

Where persistent storage is unavailable, the composer SHALL remain fully functional; only persistence
is lost.

#### Scenario: A draft survives leaving and returning

- **WHEN** the operator types unsent text for one agent, navigates to another agent, and returns
- **THEN** the first agent's text is present
- **AND** the second agent's composer was empty

#### Scenario: A draft survives reload

- **WHEN** the page is reloaded with an unsent draft present
- **THEN** the draft is still present

#### Scenario: Submission clears the draft

- **WHEN** a draft is submitted successfully
- **THEN** the stored draft for that agent is cleared

#### Scenario: Unavailable storage degrades to no persistence

- **WHEN** persistent storage cannot be written
- **THEN** the composer still accepts and submits input
- **AND** only draft retention is lost

### Requirement: Only high-frequency controls remain visible

The resting composer SHALL expose only these controls: submit, stop while the agent is running, the
active-agent indicator, and context usage.

New conversation, session selection, durable handoff, fold-all, and agent details SHALL be reachable
from one overflow menu that is fully operable by keyboard.

An action that is unavailable SHALL be presented disabled with its reason rather than omitted, so
that the menu's contents do not shift between agents.

#### Scenario: The resting control set is minimal

- **WHEN** a conversation is open and the agent is idle
- **THEN** the composer exposes submit, the active-agent indicator, and context usage
- **AND** exposes no session selector, handoff button, fold-all control, or scroll toggle

#### Scenario: Stop appears only while running

- **WHEN** the agent is running
- **THEN** a stop control is additionally visible

#### Scenario: The overflow menu is operable by keyboard alone

- **WHEN** the operator opens the overflow menu and moves through it using the keyboard
- **THEN** new conversation, session selection, handoff, fold-all, and agent details are each reachable and activatable
- **AND** dismissing the menu returns focus to its trigger

#### Scenario: An unavailable action is disabled with its reason

- **WHEN** an action such as handoff is unavailable for the current agent
- **THEN** it is present in the menu, disabled, with the reason stated

### Requirement: Session identity is readable without a selector control

The session selection control SHALL be removed from the resting conversation surface. The current
session's continuity state SHALL remain visible as text, and session selection SHALL be performed
from the overflow menu.

#### Scenario: Continuity is readable at rest

- **WHEN** a conversation is continuing an existing session
- **THEN** its continuity state is readable as text on the resting surface

#### Scenario: Session selection still works from the menu

- **WHEN** the operator selects a different session from the overflow menu
- **THEN** the conversation switches to it with the same effect the removed selector had

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

The composer SHOULD display the agent's context-window consumption using the existing indicator,
derived from the most recent context-usage event reported for that agent.

Where no context-usage event has been received, the composer SHALL render no indicator rather than a
zero value, because a zero would assert a measurement that was never taken.

#### Scenario: Reported usage is shown

- **WHEN** a context-usage event has been received for the displayed agent
- **THEN** the composer shows the usage indicator reflecting that event

#### Scenario: Absent usage renders nothing

- **WHEN** no context-usage event has been received for the displayed agent
- **THEN** no usage indicator and no zero value is rendered

### Requirement: Navigation reads from a project collection populated with one project

Navigation SHALL read its project and agent tree from a single adapter whose shape is a collection of
projects, populated with exactly the one authenticated project.

No control may offer project creation or project switching, or otherwise imply that more than one
project is reachable. Authentication binds one API key to one project, so such a control would be a
claim the backend cannot honour.

#### Scenario: One project is rendered from the collection

- **WHEN** the rail is rendered from the adapter
- **THEN** the adapter returns a collection containing exactly one project
- **AND** the rail renders it

#### Scenario: No project management is offered

- **WHEN** the interface is inspected
- **THEN** no control offering to add, create, or switch projects is present

#### Scenario: The adapter shape accepts more projects without a rail change

- **WHEN** the adapter is supplied a second project
- **THEN** the rail renders both
- **AND** the rail component is unchanged

### Requirement: Existing conversation behaviour is preserved

Session continuity, durable handoff, stop, withdraw, and deliver-now SHALL CONTINUE TO behave as
they do today, including the new-session binding and the handoff state machine.

Queue semantics — hop budget, per-turn delivery cap, and delivery ordering — SHALL CONTINUE TO be
unchanged by this change.

#### Scenario: Existing conversation suites still pass

- **WHEN** the existing conversation, timeline, handoff, and status suites are run against the reworked surface
- **THEN** every assertion about continuity, handoff, stop, withdraw, and deliver-now passes
- **AND** the only changes to those suites are to how the surface is mounted and queried
