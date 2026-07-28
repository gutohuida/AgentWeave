## ADDED Requirements

### Requirement: OverviewPage component exists and is the default landing page
A new component `hub/ui/src/components/overview/OverviewPage.tsx` SHALL be created. The `Page` type union in `App.tsx` SHALL include `'overview'`. The default page state SHALL be `'overview'` (replacing `'messages'`). The sidebar SHALL have "Overview" as its first nav item.

#### Scenario: Overview page file exists
- **WHEN** a developer searches for OverviewPage
- **THEN** the file `hub/ui/src/components/overview/OverviewPage.tsx` exists and exports a named `OverviewPage` component

#### Scenario: App loads to Overview by default
- **WHEN** the app first renders (no prior navigation)
- **THEN** the Overview page content is displayed in the main area

#### Scenario: Overview is navigable from sidebar
- **WHEN** a user clicks "Overview" in the sidebar
- **THEN** the Overview page is displayed

### Requirement: Overview page shows an agent health grid
The Overview page SHALL render a row of compact agent cards displaying each agent's current status. The grid SHALL use `repeat(auto-fill, minmax(220px, 1fr))` or equivalent responsive columns. Each card SHALL show: status dot, agent name, role tags, task count, message count, last-seen, context bar, and a single-line task preview.

#### Scenario: Agent health grid renders all agents
- **WHEN** the Overview page renders and agents data is loaded
- **THEN** one compact card per agent is rendered in the grid

#### Scenario: Clicking an agent card navigates to Agents page
- **WHEN** a user clicks an agent card on the Overview page
- **THEN** the Agents page is shown with that agent pre-selected in the detail panel

#### Scenario: Empty state shown when no agents
- **WHEN** no agents are registered
- **THEN** an empty state is rendered with instructions to run `agentweave init`

### Requirement: Overview page shows QuestionInterruptCard when questions are unanswered
The Overview page SHALL render a `QuestionInterruptCard` (full variant, `compact={false}`) between the agent grid and the task summary when `questions.unanswered > 0`. It SHALL not render the card when there are no unanswered questions.

#### Scenario: Interrupt card shown on Overview when questions exist
- **WHEN** `useQuestions()` returns unanswered questions
- **THEN** a full-width QuestionInterruptCard is rendered between the agent grid and task summary on Overview

#### Scenario: Interrupt card absent on Overview when no questions
- **WHEN** no unanswered questions exist
- **THEN** no QuestionInterruptCard is rendered on Overview

### Requirement: Overview page shows a task summary section
Below the agent grid (and optional interrupt card), the Overview page SHALL render a task summary section showing per-status counts. Each status count SHALL be a clickable chip that navigates to the Tasks page.

#### Scenario: Task counts are shown per status
- **WHEN** tasks data is loaded
- **THEN** the Overview page shows counts for each status: Pending, In Progress, Under Review, Completed, and any others with count > 0

#### Scenario: Clicking a status count opens Tasks page
- **WHEN** a user clicks a status count chip
- **THEN** the active page changes to "tasks"

### Requirement: Overview page has a live activity ticker at the bottom
The bottom of the Overview page main content area SHALL have a 28px-tall activity ticker bar that displays a horizontally auto-scrolling feed of recent SSE events. Each event SHALL show an agent name, event type, and relative time.

#### Scenario: Ticker renders recent events
- **WHEN** the Overview page is active and SSE events have been received
- **THEN** the ticker bar shows the most recent N events (at least 5) as horizontal chips

#### Scenario: Ticker is empty when no events received yet
- **WHEN** the Overview page renders before any SSE events arrive
- **THEN** the ticker bar is visible but shows no event chips (or a subtle "No activity yet" placeholder)

#### Scenario: Ticker updates when new SSE events arrive
- **WHEN** a new SSE event is received
- **THEN** the ticker bar updates to include the new event without requiring a page reload

### Requirement: Overview page has a section header with title and subtitle
The Overview page SHALL have a page header with the title "Overview" and a subtitle showing the current system health summary (e.g., "3 agents · 7 tasks · myproject").

#### Scenario: Page header is rendered
- **WHEN** the Overview page renders
- **THEN** an "Overview" heading is visible
- **THEN** a subtitle showing agent count, task count, and project name is rendered
