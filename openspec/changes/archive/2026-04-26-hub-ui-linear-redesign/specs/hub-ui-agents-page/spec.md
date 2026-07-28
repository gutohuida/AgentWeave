## ADDED Requirements

### Requirement: AgentsPage uses a two-panel layout with agent list and detail panel
The Agents page SHALL render a two-panel layout. The left panel (240px fixed width, `--surface` background, right border) contains the agent list and any interrupt cards. The right panel (flex-1) contains the detail view for the selected agent. `MissionControlPage.tsx` SHALL be deleted; its functionality is absorbed into this page.

#### Scenario: Two panels render side by side
- **WHEN** the Agents page is active and at least one agent exists
- **THEN** a 240px left panel and a flex-1 right panel are rendered side by side

#### Scenario: MissionControlPage is no longer accessible
- **WHEN** a developer searches for `MissionControlPage` in the codebase
- **THEN** the file `hub/ui/src/components/agents/MissionControlPage.tsx` does not exist
- **THEN** no import of `MissionControlPage` exists in `App.tsx`

### Requirement: Agent list items show status dot, name, role tags, stats, and latest task preview
Each agent item in the left panel SHALL display:
- A status dot (7–8px circle, `--green` with glow animation if running, `--amber` if waiting, `--surface-3` if idle)
- Agent name in `--text`, 13px, font-weight 500–600
- Status label ("Running" / "Waiting" / "Idle") in the semantic color
- Role tags (principal, delegate; dev roles) as small pill badges below the name
- Stats row: task count, message count, last-seen relative time
- Context usage bar (2px height, colored by usage percentage)
- A single-line preview of the agent's `latest_status_msg` (truncated with ellipsis)

#### Scenario: Running agent shows animated green pulse
- **WHEN** an agent has `status === 'running'`
- **THEN** the status dot is `--green` with a CSS `animate-ping` ring around it

#### Scenario: Agent context bar reflects usage percentage
- **WHEN** `agent.context_usage.percent` is available
- **THEN** a 2px horizontal bar is shown; fill width equals the percentage; color is `--green` below 40%, `--amber` at 40–69%, `--red` at 70%+

#### Scenario: Latest status message is shown truncated
- **WHEN** `agent.latest_status_msg` is non-null
- **THEN** it renders on a single line below the stats row, truncated with `text-overflow: ellipsis`

### Requirement: Clicking an agent item selects it and populates the detail panel
Clicking any agent item in the left panel SHALL set that agent as selected. The selected item SHALL show a highlighted background (`rgba(255,255,255,0.05)`) and a `--border-hi` border. The detail panel SHALL update to show that agent's data.

#### Scenario: Selected agent item is visually distinct
- **WHEN** an agent item is selected
- **THEN** its background is `rgba(255,255,255,0.05)` and its border is `rgba(255,255,255,0.12)`

#### Scenario: Clicking a different agent updates the detail panel
- **WHEN** a user clicks a different agent item
- **THEN** the detail panel immediately updates to show the newly selected agent's output

### Requirement: Detail panel has a header bar with agent name, role tags, context stats, and action buttons
The detail panel header SHALL display (left to right): status dot, agent name, role tag pills, then (right-aligned): context percentage text, context bar (48px wide, 3px height), "Compact" button, "Reset" button.

#### Scenario: Detail header shows agent name and roles
- **WHEN** an agent is selected
- **THEN** the detail header shows the agent's name in 14px font-weight 600 and all role tags as pills

#### Scenario: Compact button sends compact request
- **WHEN** a user clicks "Compact"
- **THEN** `requestCompact(agent.name)` is called
- **THEN** the button shows a disabled loading state while the request is in flight
- **THEN** a transient feedback message "Compact request sent" appears for 3 seconds

#### Scenario: Reset button requires confirmation
- **WHEN** a user clicks "Reset"
- **THEN** the button changes to a confirmation state ("Confirm" / "Cancel")
- **WHEN** user clicks "Confirm"
- **THEN** `requestNewSession(agent.name)` is called

#### Scenario: Codex agents show "Auto-managed" instead of Compact button
- **WHEN** `agent.runner === 'codex'`
- **THEN** the Compact button is replaced with a non-interactive "Auto-managed" label

### Requirement: Detail panel has tabs for Output, Tasks, Messages, and Info
The detail panel SHALL have a tab bar with four tabs: Output, Tasks, Messages, Info. The active tab SHALL be indicated by a 1px bottom border in `--text` on the tab label. The default active tab is Output.

#### Scenario: Output tab shows live agent output
- **WHEN** the Output tab is active
- **THEN** `AgentOutputPanel` is rendered for the selected agent

#### Scenario: Tasks tab shows tasks filtered by selected agent
- **WHEN** the Tasks tab is active
- **THEN** a list of tasks where `task.assignee === agent.name` is rendered
- **THEN** each task shows its title, status badge, priority badge, and updated-at timestamp

#### Scenario: Messages tab shows agent message history
- **WHEN** the Messages tab is active
- **THEN** `AgentActivityTab` or equivalent message history for the selected agent is rendered

#### Scenario: Info tab shows agent configuration details
- **WHEN** the Info tab is active
- **THEN** `AgentInfoTab` is rendered for the selected agent

### Requirement: Grid view toggle shows all agents as health cards
A "Grid view" toggle button in the page header SHALL switch the right panel from the selected-agent detail view to a 3-column grid of compact agent health cards. Clicking any health card SHALL switch back to detail view with that agent selected.

#### Scenario: Grid view button toggles layout
- **WHEN** a user clicks "Grid view"
- **THEN** the right panel renders a 3-column grid of compact agent cards
- **THEN** the button label changes to "Detail view"

#### Scenario: Clicking a grid card selects that agent
- **WHEN** grid view is active and user clicks an agent card
- **THEN** the view switches to detail view with that agent selected

### Requirement: QuestionInterruptCard is shown at the top of the agent list when questions are unanswered
When `questions.unanswered > 0`, a `QuestionInterruptCard` (compact variant) SHALL be rendered pinned above all agent list items in the left panel.

#### Scenario: Interrupt card appears when questions exist
- **WHEN** `useQuestions()` returns one or more unanswered questions
- **THEN** a `QuestionInterruptCard` is rendered above the agent list items

#### Scenario: Interrupt card is absent when no questions exist
- **WHEN** `useQuestions()` returns an empty array
- **THEN** no `QuestionInterruptCard` is rendered in the agent list panel
