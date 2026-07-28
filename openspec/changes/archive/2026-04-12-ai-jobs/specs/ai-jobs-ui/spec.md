## ADDED Requirements

### Requirement: Jobs tab in Hub Sidebar
The Hub UI SHALL display a "Jobs" navigation item in the Sidebar, positioned after the existing "Activity" item. The Jobs tab SHALL show a badge with the count of enabled jobs when at least one job exists.

#### Scenario: Jobs tab visible in navigation
- **WHEN** user opens Hub UI
- **THEN** a "Jobs" tab is visible in the sidebar with a schedule/timer icon

#### Scenario: Badge shows enabled job count
- **WHEN** 3 jobs are enabled
- **THEN** the Jobs tab shows a badge with "3"

### Requirement: JobsPage with job list
The Jobs page SHALL display all jobs as cards. Each card SHALL show: job name, target agent, cron expression (human-readable hint below the raw cron), enabled/disabled status, last_run timestamp, next_run timestamp, and run_count. The page SHALL include a "New Job" button that opens the create form.

#### Scenario: Empty state
- **WHEN** no jobs exist
- **THEN** an empty state is shown with a prompt to create the first job

#### Scenario: Job list populated
- **WHEN** jobs exist
- **THEN** each job is rendered as a card with all required fields visible

### Requirement: JobCard enable/disable toggle
Each JobCard SHALL include a toggle switch for enabling or disabling the job. Toggling SHALL call PATCH /api/v1/jobs/{id} and update the UI optimistically.

#### Scenario: Disable job via toggle
- **WHEN** user clicks the enabled toggle on a job card
- **THEN** the job is immediately shown as disabled and PATCH /api/v1/jobs/{id} is called with enabled=false

### Requirement: JobForm create/edit modal
The Hub UI SHALL provide a modal form for creating and editing jobs. The form SHALL include: name (text), agent (dropdown from known agents), message (textarea), cron expression (text with validation feedback), session_mode (radio: new/resume). Submit SHALL call POST /api/v1/jobs (create) or PATCH /api/v1/jobs/{id} (edit).

#### Scenario: Create new job
- **WHEN** user fills form and clicks "Create"
- **THEN** POST /api/v1/jobs is called and the new job appears in the list

#### Scenario: Invalid cron shows inline error
- **WHEN** user types an invalid cron expression in the form
- **THEN** an inline error message explains the expected format before submission

#### Scenario: Edit existing job
- **WHEN** user clicks edit on a job card
- **THEN** the form opens pre-populated with existing job values

### Requirement: JobRunHistory panel
Each job card SHALL have an expandable history panel showing the last 10 runs. Each run entry SHALL display: fired_at (formatted timestamp), status (fired/failed), trigger (scheduled/manual), and session_id (as a truncated link to the agent session if available).

#### Scenario: History panel expands
- **WHEN** user clicks "History" on a job card
- **THEN** the last 10 run entries are shown below the card

#### Scenario: Manual trigger visible in history
- **WHEN** a run was triggered manually
- **THEN** the history entry shows "manual" trigger label

### Requirement: Immediate run from UI
Each JobCard SHALL include a "Run Now" action that calls POST /api/v1/jobs/{id}/run and shows a brief confirmation toast.

#### Scenario: Run now fires job
- **WHEN** user clicks "Run Now" on a job card
- **THEN** POST /api/v1/jobs/{id}/run is called and a success toast appears

### Requirement: Real-time job updates via SSE
The Hub UI SHALL invalidate the jobs React Query cache when SSE events of type `job_created`, `job_updated`, or `job_fired` are received, causing the job list to refresh without a full page reload.

#### Scenario: Job fires and run count updates live
- **WHEN** a scheduled job fires and the Jobs tab is open
- **THEN** the job card's run_count and last_run fields update automatically within 5 seconds
