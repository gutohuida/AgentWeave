## ADDED Requirements

### Requirement: Job creation
The system SHALL allow users and agents to create AI Jobs with a name, target agent, message body, cron expression, and session mode (new or resume). The job SHALL be assigned a unique ID and stored in the active transport's backend (file-based for local/git, Hub DB for http). The cron expression SHALL be validated at creation time using croniter; invalid expressions MUST be rejected with a descriptive error.

#### Scenario: Successful job creation (local mode)
- **WHEN** user runs `agentweave jobs create --agent pm --message "Check status" --cron "*/10 * * * *" --name "PM Check"`
- **THEN** a JSON file is written to `.agentweave/jobs/<id>.json` with all fields populated and `enabled: true`

#### Scenario: Invalid cron expression rejected
- **WHEN** user provides `--cron "every 10 minutes"` (non-standard format)
- **THEN** the command exits with a non-zero status and prints a cron format error

#### Scenario: Job creation via Hub (http transport)
- **WHEN** user creates a job with http transport active
- **THEN** a POST to `/api/v1/jobs` persists the job to the Hub DB and returns the job ID

### Requirement: Job listing
The system SHALL provide a command and API endpoint to list all jobs, optionally filtered by agent name. Each job entry SHALL include id, name, agent, cron, enabled status, last_run, next_run, and run_count.

#### Scenario: List all jobs
- **WHEN** user runs `agentweave jobs list`
- **THEN** all jobs are displayed in a tabular format with status indicators

#### Scenario: Filter by agent
- **WHEN** user runs `agentweave jobs list --agent project-manager`
- **THEN** only jobs targeting `project-manager` are shown

### Requirement: Job enable/disable (toggle)
The system SHALL allow toggling a job's enabled state without deleting it. Disabled jobs MUST NOT be fired by the scheduler or Watchdog.

#### Scenario: Pause a job
- **WHEN** user runs `agentweave jobs pause <id>`
- **THEN** the job's `enabled` field is set to `false` and the scheduler stops firing it

#### Scenario: Resume a paused job
- **WHEN** user runs `agentweave jobs resume <id>`
- **THEN** the job's `enabled` field is set to `true` and the next cron-aligned fire is scheduled

### Requirement: Job deletion
The system SHALL allow permanent deletion of a job by ID. Deletion SHALL also remove all associated run history files (local mode) or DB records (Hub mode).

#### Scenario: Delete job
- **WHEN** user runs `agentweave jobs delete <id>`
- **THEN** the job definition and its history are removed from storage

### Requirement: Immediate job execution
The system SHALL allow firing a job immediately on demand, regardless of its cron schedule, via CLI command and MCP tool. Immediate execution SHALL record a run history entry with `trigger: "manual"`.

#### Scenario: Manual fire
- **WHEN** user runs `agentweave jobs run <id>`
- **THEN** the job's message is sent to the target agent immediately and a JobRun record is created

### Requirement: Run history tracking
The system SHALL record each job execution as a JobRun entry containing: id, job_id, fired_at (ISO 8601 UTC), status (fired/failed), session_id, and trigger (scheduled/manual). History SHALL be retained for the last 100 runs per job; older entries SHALL be pruned automatically.

#### Scenario: History recorded after scheduled fire
- **WHEN** a job fires on schedule
- **THEN** a JobRun entry is created with `trigger: "scheduled"` and `fired_at` set to the actual fire time

#### Scenario: History pruned at 100 entries
- **WHEN** a job has 100 history entries and fires again
- **THEN** the oldest entry is deleted and the new run is appended

### Requirement: Session mode per job
Each job SHALL store a `session_mode` field with value `new` or `resume`. When `session_mode` is `resume`, the system SHALL pass the `session_id` from the last successful run to the agent trigger. When `session_mode` is `new`, a fresh session SHALL always be started.

#### Scenario: Resume mode reuses session
- **WHEN** a job with `session_mode: resume` fires and a prior `session_id` exists in the job record
- **THEN** the agent trigger is called with `session_mode: resume` and the stored `session_id`

#### Scenario: New mode always fresh
- **WHEN** a job with `session_mode: new` fires
- **THEN** the agent trigger is called with `session_mode: new` and no session_id
