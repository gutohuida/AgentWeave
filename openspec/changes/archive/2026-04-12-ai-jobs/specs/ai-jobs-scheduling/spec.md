## ADDED Requirements

### Requirement: Watchdog job polling (local/git mode)
The Watchdog SHALL check enabled jobs on each poll cycle when the transport is local or git. For each enabled job, the system SHALL evaluate the cron expression against the current UTC time using croniter. If the cron expression matches the current minute AND `last_run` is more than 50 seconds ago, the job SHALL fire.

#### Scenario: Job fires at correct time
- **WHEN** Watchdog polls and current UTC time matches a job's cron expression
- **THEN** the Watchdog executes `agentweave run <agent> "<message>"` with appropriate session flags

#### Scenario: Job does not double-fire within same minute
- **WHEN** Watchdog polls twice within the same cron minute
- **THEN** the job fires only once (guarded by `last_run` recency check)

#### Scenario: Disabled job skipped
- **WHEN** a job's `enabled` field is `false`
- **THEN** the Watchdog skips it regardless of schedule match

### Requirement: File lock for job firing (local mode)
Before firing a job in local/git mode, the Watchdog SHALL acquire a file lock named `job-<id>` using the existing locking module. The lock SHALL prevent double-firing if multiple Watchdog instances are running.

#### Scenario: Lock prevents concurrent fire
- **WHEN** two Watchdog processes attempt to fire the same job simultaneously
- **THEN** only one succeeds; the other skips silently (lock already held)

### Requirement: APScheduler integration (Hub mode)
The Hub SHALL start an `AsyncIOScheduler` in the FastAPI lifespan. On startup, the scheduler SHALL load all enabled jobs from the DB and schedule them using their cron expressions. When a job fires, the scheduler SHALL call the agent trigger function internally (no HTTP round-trip). `misfire_grace_time` SHALL be set to 60 seconds; `coalesce` SHALL be `true` to prevent burst re-fires after downtime.

#### Scenario: Scheduler starts with existing jobs
- **WHEN** Hub starts and enabled jobs exist in the DB
- **THEN** all enabled jobs are registered with APScheduler using their cron expressions

#### Scenario: Missed fire on restart
- **WHEN** Hub was down and a job's cron time was missed
- **THEN** APScheduler fires the job once on startup (within `misfire_grace_time`)

#### Scenario: Scheduler shuts down cleanly
- **WHEN** Hub FastAPI lifespan shutdown event fires
- **THEN** APScheduler shuts down without waiting for pending jobs (wait=False)

### Requirement: Hub job CRUD updates scheduler
When a job is created, updated (enabled/disabled), or deleted via the Hub REST API, the scheduler SHALL be updated in real time without requiring a Hub restart.

#### Scenario: New job scheduled immediately
- **WHEN** POST /api/v1/jobs creates a new enabled job
- **THEN** the scheduler adds the job and it fires at the next cron-aligned time

#### Scenario: Paused job removed from scheduler
- **WHEN** PATCH /api/v1/jobs/{id} sets enabled=false
- **THEN** the scheduler removes the job; it does not fire until re-enabled

### Requirement: Local-to-Hub job sync
When the CLI transport switches to HTTP (Hub becomes available), the system SHALL push all local job definitions to Hub. For each local job, the system SHALL attempt POST /api/v1/jobs with the job's existing ID. If the Hub returns 409 (already exists), the local job SHALL be marked as synced without overwriting the Hub record.

#### Scenario: Local job promoted to Hub
- **WHEN** transport switches to HTTP and a local job exists that Hub does not know about
- **THEN** the job is created in Hub via POST /api/v1/jobs and marked `synced: true` locally

#### Scenario: Duplicate ID skipped
- **WHEN** Hub already has a job with the same ID
- **THEN** the local job is not overwritten; sync marks it as already-synced
