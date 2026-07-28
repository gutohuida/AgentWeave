## ADDED Requirements

### Requirement: TasksBoard renders all seven task status columns
`hub/ui/src/components/tasks/TasksBoard.tsx` SHALL render columns for all seven task statuses in the following order: `pending`, `assigned`, `in_progress`, `under_review`, `completed`, `approved`, `revision_needed`. A collapsed "Rejected" section SHALL appear below `revision_needed` for `rejected` tasks (not a full column).

#### Scenario: All seven columns are rendered
- **WHEN** the Tasks page is active and tasks data is loaded
- **THEN** exactly seven column headers are rendered: Pending, Assigned, In Progress, Under Review, Completed, Approved, Needs Revision

#### Scenario: Rejected tasks appear in a collapsed section
- **WHEN** tasks with `status === 'rejected'` exist
- **THEN** they appear in a collapsible section below the Needs Revision column, not in a full-width column

#### Scenario: Columns are empty when no tasks have that status
- **WHEN** no tasks exist with status `assigned`
- **THEN** the Assigned column renders with a count of 0 and no task cards

### Requirement: Column accent colors match the task lifecycle semantics
The following columns SHALL have accent colors applied to their header and background:
- `in_progress`: blue accent (`--blue`, background `rgba(59,130,246,0.05)`, border `rgba(59,130,246,0.12)`)
- `under_review`: amber accent (`--amber`, background `rgba(245,158,11,0.05)`, border `rgba(245,158,11,0.12)`)
- `approved`: green accent (`--green`, background `rgba(34,197,94,0.05)`, border `rgba(34,197,94,0.12)`)
- `revision_needed`: red accent (`--red`, background `rgba(239,68,68,0.05)`, border `rgba(239,68,68,0.12)`)
- All other columns: neutral (no accent)

#### Scenario: In Progress column has blue accent
- **WHEN** the Tasks board renders
- **THEN** the "In Progress" column header text color is `--blue`

#### Scenario: Approved column has green accent
- **WHEN** the Tasks board renders
- **THEN** the "Approved" column header text color is `--green`

#### Scenario: Needs Revision column has red accent
- **WHEN** the Tasks board renders
- **THEN** the "Needs Revision" column header text color is `--red`

### Requirement: An agent filter chip row above the board filters visible tasks
Above the kanban columns, a row of filter chips SHALL be rendered. The first chip is "All" (default selected). Additional chips are rendered for each unique agent name found in the task list. Selecting a chip filters all columns to show only tasks where `task.assignee === agentName`.

#### Scenario: Filter chips render for each agent
- **WHEN** tasks exist assigned to agents "claude" and "codex"
- **THEN** filter chips "All", "claude", and "codex" are rendered above the board

#### Scenario: Selecting an agent chip filters all columns
- **WHEN** a user clicks the "claude" chip
- **THEN** all columns show only tasks where `task.assignee === 'claude'`
- **THEN** columns with no matching tasks show a count of 0 and no task cards

#### Scenario: Selecting "All" chip shows all tasks
- **WHEN** a user clicks the "All" chip
- **THEN** all tasks are shown in their respective columns regardless of assignee

#### Scenario: Active filter chip is visually distinct
- **WHEN** a filter chip is selected
- **THEN** it renders with a distinct background (e.g., `--surface-3`) and text color (`--text`), different from unselected chips

### Requirement: TaskCard renders status, priority, assignee, assigner, and timestamp
`hub/ui/src/components/tasks/TaskCard.tsx` SHALL render: task title (13px, `--text`), status badge, priority badge, assignee badge (`@name`), assigner badge (`from: name`) when different from assignee, and updated-at relative timestamp. Expanding the card (click) shows full description, requirements list, acceptance criteria, deliverables, notes, and task ID. The card background SHALL use `--surface-2` and border `--border`, with `--border-hi` on hover.

#### Scenario: Task card shows title and badges in collapsed state
- **WHEN** a task card is in its default collapsed state
- **THEN** the task title, status badge, priority badge, and assignee badge are all visible

#### Scenario: Clicking the card expands full details
- **WHEN** a user clicks a task card that has a description or additional fields
- **THEN** the card expands to show full description, requirements, acceptance criteria, deliverables, notes, and task ID

#### Scenario: Card uses correct background tokens
- **WHEN** a task card renders
- **THEN** its background is `var(--surface-2)` and its border is `1px solid var(--border)`

#### Scenario: Card border highlights on hover
- **WHEN** a user hovers over a task card
- **THEN** the border color changes to `var(--border-hi)`

### Requirement: TasksBoard supports horizontal scroll when columns overflow the viewport
The kanban container SHALL allow horizontal scrolling when the total column width exceeds the available viewport width (e.g., on displays narrower than 1280px).

#### Scenario: Kanban scrolls horizontally when viewport is narrow
- **WHEN** the browser window is narrower than the total width of all 7 columns
- **THEN** a horizontal scrollbar appears on the kanban container and all columns remain accessible via scroll
