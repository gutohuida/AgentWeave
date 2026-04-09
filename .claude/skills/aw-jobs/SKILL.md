---
name: aw-jobs
description: Manage scheduled AI jobs in AgentWeave — create recurring tasks that trigger agents on a cron schedule. Usage — /aw-jobs [list|create|pause|resume|delete|run]
---

Manage scheduled AI jobs that trigger agents automatically on a cron schedule.

**Project:** Agentweave
**Principal:** claude
**Agents:** claude, kimi, minimax

## Available Commands

### List Jobs
`agentweave jobs list`

Shows all jobs with status, next run time, and last run result.

### Create Job
`agentweave jobs create --name "<name>" --agent <agent> --message "<message>" --cron "<cron>" [--session-mode new|resume]`

Parameters:
- `--name`: Human-readable job name
- `--agent`: Target agent to trigger (claude, kimi, minimax)
- `--message`: The task/prompt to send to the agent
- `--cron`: Cron expression (e.g., `0 9 * * 1-5` for 9am weekdays)
- `--session-mode`: "new" for fresh session (default) or "resume" to continue last

Examples:
```bash
# Daily standup report at 9am weekdays
agentweave jobs create --name "Daily Standup" --agent kimi --message "Generate daily standup report" --cron "0 9 * * 1-5"

# Weekly code review on Sundays
agentweave jobs create --name "Weekly Review" --agent claude --message "Review code for issues" --cron "0 18 * * 0" --session-mode resume
```

### Run Job Now
`agentweave jobs run <job-id>`

Manually triggers a job immediately, regardless of schedule.

### Pause Job
`agentweave jobs pause <job-id>`

Disables the job temporarily (prevents automatic firing).

### Resume Job
`agentweave jobs resume <job-id>`

Re-enables a paused job.

### Delete Job
`agentweave jobs delete <job-id>`

Permanently removes the job and its run history.

### Get Job Details
`agentweave jobs get <job-id>`

Shows full job configuration and recent run history.

## Hub Mode (HTTP Transport)

When using AgentWeave Hub, jobs are stored in the database and managed by APScheduler:

```bash
# Check transport mode
agentweave transport status

# Sync local jobs to Hub (one-time migration)
# Jobs created in Hub UI are automatically managed
```

## Cron Expression Format

Standard 5-field cron: `minute hour day month weekday`

| Expression | Description |
|------------|-------------|
| `0 9 * * *` | Daily at 9:00 AM |
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `0 */6 * * *` | Every 6 hours |
| `0 0 * * 0` | Weekly on Sunday |
| `0 0 1 * *` | Monthly on 1st |

## Fire Guard Protection

Jobs have a 50-second deduplication guard to prevent double-firing if the system checks twice within the same minute. Minimum cron granularity is 1 minute.

## Session Modes

- **new** (default): Each run starts a fresh conversation context
- **resume**: Continues from the last session ID, maintaining conversation history
