## ADDED Requirements

### Requirement: Sidebar is 220px wide with text labels and grouped sections
The sidebar SHALL be 220px wide. Each nav item SHALL display a text label alongside its icon. Nav items SHALL be organized into named sections separated by uppercase section heading labels. The sidebar SHALL replace the existing 80px icon-only nav rail entirely.

#### Scenario: Sidebar renders at correct width
- **WHEN** the app renders on any page
- **THEN** the sidebar element has a computed width of 220px

#### Scenario: All nav items display text labels
- **WHEN** the sidebar is visible
- **THEN** each nav item shows both an icon and a text label, never icon alone

#### Scenario: Section labels separate item groups
- **WHEN** the sidebar is visible
- **THEN** the following section labels are rendered in order: "WORK", "COMMUNICATION", "OBSERVE"
- **THEN** each section label is styled in 10px uppercase zinc/text-3 color

### Requirement: Sidebar navigation items are organized into five groups
The sidebar SHALL contain the following items in order, grouped as specified:

**Top (ungrouped):**
- Overview (icon: grid or dashboard symbol)
- Agents (icon: robot/agent symbol)

**WORK section:**
- Tasks
- Jobs

**COMMUNICATION section:**
- Messages
- Questions

**OBSERVE section:**
- Logs
- Activity
- Quality

**Bottom (pinned, separated by a border):**
- Settings / Setup

#### Scenario: Overview is the first nav item
- **WHEN** the sidebar renders
- **THEN** "Overview" is the topmost nav item

#### Scenario: Settings is pinned at the bottom
- **WHEN** the sidebar renders
- **THEN** "Settings" (or "Setup") is pinned to the bottom of the sidebar, visually separated from the nav items above it by a 1px border

#### Scenario: All nine navigable pages remain accessible
- **WHEN** a user clicks each sidebar item
- **THEN** the corresponding page content renders in the main area

### Requirement: Active nav item shows a left-border accent indicator
The active nav item SHALL be indicated by a 2px solid left border in `--text` color, a background of `rgba(255,255,255,0.06)`, and text in `--text`. No pill-shaped or container-based active indicator is used.

#### Scenario: Active item has left border
- **WHEN** a nav item is the currently active page
- **THEN** a 2px solid `var(--text)` border is rendered on the left edge of that item
- **THEN** the item background is `rgba(255,255,255,0.06)`

#### Scenario: Inactive items have no left border
- **WHEN** a nav item is not the currently active page
- **THEN** no left border is rendered on that item

### Requirement: Nav item badges show unread/active counts
Nav items SHALL display a badge with count when the following conditions are true:
- **Messages**: badge shown when unread message count > 0 (neutral style: `--surface-3` bg, `--text-2` text)
- **Questions**: badge shown when unanswered question count > 0 (urgent style: `--red` bg, white text)
- **Agents**: badge shown when active agent count > 0 (neutral style)
- **Tasks**: badge shown when total active task count > 0 (neutral style)

#### Scenario: Questions badge is urgent red when unanswered exist
- **WHEN** `questions.unanswered > 0`
- **THEN** the Questions nav item shows a red badge with the count

#### Scenario: Messages badge is neutral when unread exist
- **WHEN** `messages.unread > 0`
- **THEN** the Messages nav item shows a neutral (zinc) badge with the unread count

#### Scenario: No badge is shown when count is zero
- **WHEN** a count is 0
- **THEN** no badge element is rendered for that nav item

### Requirement: Sidebar has a logo mark at the top
The top of the sidebar SHALL display a small "AW" or AgentWeave logo mark above all nav items. Clicking the logo mark SHALL have no navigation effect (it is decorative).

#### Scenario: Logo mark is visible
- **WHEN** the sidebar renders
- **THEN** a logo mark is displayed above all nav items
