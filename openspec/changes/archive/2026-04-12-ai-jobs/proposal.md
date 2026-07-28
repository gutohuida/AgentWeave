## Why

AgentWeave has no way to schedule recurring agent activity — every interaction is manually initiated. AI Jobs adds cron-scheduled message delivery to agents, enabling autonomous recurring workflows (status checks, standups, monitoring) that run on a schedule without human intervention.

## What Changes

- New `AIJob` entity: name, target agent, message, cron expression, session mode (new/resume), enabled flag, run history
- Dual-mode execution: Hub-managed (APScheduler + DB + REST API + UI tab) and Hub-less (file storage + Watchdog)
- Jobs created locally sync to Hub when Hub transport becomes available
- New `/aw-job` skill for human-facing job management from the terminal
- New MCP tools (`create_job`, `list_jobs`, `get_job`, `delete_job`, `toggle_job`, `run_job`) so agents can self-schedule or schedule peers
- Job run history tracked per execution (fired_at, status, session_id)
- New `agentweave jobs` CLI subcommands (create, list, get, pause, resume, delete, run)
- New Hub UI tab "Jobs" with create form, job cards, enable/disable toggle, and run history view

## Capabilities

### New Capabilities

- `ai-jobs-core`: Job entity lifecycle — create, list, get, enable/disable, delete, fire immediately; dual-mode storage (file-based and Hub DB); cron evaluation using croniter; run history tracking
- `ai-jobs-scheduling`: Scheduling engine — APScheduler integration inside Hub FastAPI lifespan for Hub mode; Watchdog `check_jobs()` loop for local/git mode; minute-aligned polling; sync of local job definitions to Hub on reconnect
- `ai-jobs-mcp`: MCP tool surface — `create_job`, `list_jobs`, `get_job`, `delete_job`, `toggle_job`, `run_job` exposed in both CLI MCP server and Hub MCP server
- `ai-jobs-ui`: Hub UI — Jobs tab in Sidebar, JobsPage, JobCard, JobForm (create/edit modal), JobRunHistory panel; React Query hooks for all job endpoints; SSE invalidation on job events

### Modified Capabilities

- None

## Impact

- **New dependencies**: `croniter` (CLI + Hub, cron parsing), `apscheduler` (Hub only, in-process scheduling)
- **CLI**: `src/agentweave/jobs.py` (new), `watchdog.py` (extended), `transport/base.py` / `local.py` / `http.py` (extended), `mcp/server.py` (6 new tools), `cli.py` (new subcommands)
- **Hub**: `hub/hub/db/models.py` (2 new tables: AIJob, JobRun), `hub/hub/api/v1/jobs.py` (new), `hub/hub/scheduler.py` (new), `hub/hub/main.py` (scheduler lifespan), `hub/hub/mcp_server.py` (6 new tools)
- **Hub UI**: `hub/ui/src/components/jobs/` (4 new components), `hub/ui/src/api/jobs.ts` (new), `App.tsx` + `Sidebar.tsx` (updated)
- **Documentation**: Watchdog must be running for job execution in local/git mode (document requirement)
