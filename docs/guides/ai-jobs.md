# AI Jobs - Scheduled Agent Tasks

AI Jobs allow you to schedule recurring tasks for your agents using cron expressions. Jobs can trigger agents automatically at specified intervals, making them ideal for periodic maintenance, scheduled reports, and automated workflows.

## Overview

An AI Job consists of:
- **Name** - A human-readable identifier
- **Agent** - Which agent to trigger
- **Message** - The prompt sent to the agent
- **Cron expression** - When to run (e.g., `0 9 * * 1-5` for weekdays at 9am)
- **Session mode** - Whether to start a fresh session or resume the previous one

## Prerequisites

AI Jobs require either:
- **AgentWeave Hub** (HTTP transport) - Recommended for production use
- **Local transport** - Jobs stored locally, useful for development

Install the optional jobs dependency:

```bash
pip install "agentweave-ai[jobs]"
```

## Creating Jobs

### Basic Job

```bash
agentweave jobs create \
  --name "Daily Standup Report" \
  --agent claude \
  --message "Generate a summary of completed tasks and open PRs from yesterday" \
  --cron "0 9 * * 1-5"
```

### With Session Resume

To continue from the previous session instead of starting fresh:

```bash
agentweave jobs create \
  --name "Weekly Dependency Check" \
  --agent kimi \
  --message "Check for outdated dependencies and create update tasks" \
  --cron "0 10 * * 1" \
  --session-mode resume
```

### Cron Expression Format

AgentWeave uses standard cron syntax:

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6, where 0 = Sunday)
│ │ │ │ │
* * * * *
```

**Common patterns:**

| Expression | Description |
|------------|-------------|
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `0 */6 * * *` | Every 6 hours |
| `0 0 * * 0` | Weekly on Sunday at midnight |
| `0 8 1 * *` | First day of month at 8:00 AM |
| `*/15 * * * *` | Every 15 minutes |

## Managing Jobs

### List All Jobs

```bash
agentweave jobs list
```

Output shows job ID, name, agent, cron schedule, enabled status, and next run time.

### Filter by Agent

```bash
agentweave jobs list --agent kimi
```

### View Job Details

```bash
agentweave jobs get <job_id>
```

Shows complete job configuration plus run history (last 100 runs).

### Pause a Job

```bash
agentweave jobs pause <job_id>
```

### Resume a Job

```bash
agentweave jobs resume <job_id>
```

### Run a Job Immediately

Manually trigger a job outside its schedule:

```bash
agentweave jobs run <job_id>
```

### Delete a Job

```bash
agentweave jobs delete <job_id>
```

You'll be prompted for confirmation. Use `--force` to skip:

```bash
agentweave jobs delete <job_id> --force
```

## Session Modes

### New Session Mode (Default)

Each job execution starts a fresh agent session:

- ✅ Clean slate, no context pollution
- ✅ Good for independent, recurring tasks
- ❌ Agent must re-read project context each time

### Resume Session Mode

Continues from the previous job execution:

- ✅ Maintains context between runs
- ✅ Good for progressive work (daily reports building on previous days)
- ❌ Context can grow large over time
- ❌ Use `--session-mode resume` when creating

## Use Cases

### 1. Daily Standup Reports

```bash
agentweave jobs create \
  --name "Daily Summary" \
  --agent claude \
  --message "Review git log since yesterday and summarize changes. Post summary to #dev-updates." \
  --cron "0 9 * * 1-5"
```

### 2. Dependency Updates

```bash
agentweave jobs create \
  --name "Check Dependencies" \
  --agent kimi \
  --message "Run 'npm outdated' and create tasks for major updates. Group minor/patch updates into a single PR task." \
  --cron "0 10 * * 1" \
  --session-mode resume
```

### 3. Documentation Review

```bash
agentweave jobs create \
  --name "Docs Review" \
  --agent claude \
  --message "Review docs/ directory for stale content. Check if code examples still match implementation. Create tasks for outdated sections." \
  --cron "0 14 * * 1"
```

### 4. Test Health Monitor

```bash
agentweave jobs create \
  --name "Test Health Check" \
  --agent kimi \
  --message "Run test suite. If flaky tests detected, analyze patterns and create fix tasks." \
  --cron "0 */4 * * *"
```

## Job Run History

Each job execution is tracked with:

- **Fired at** - Timestamp of execution
- **Status** - `fired` or `failed`
- **Trigger** - `scheduled` or `manual`
- **Session ID** - The session used (for resume mode)

View history:

```bash
agentweave jobs get <job_id>
```

History is automatically pruned to the last 100 runs per job.

## Hub vs Local Transport

| Feature | Hub (HTTP) | Local |
|---------|------------|-------|
| Job storage | Hub database | `.agentweave/jobs/` |
| Scheduling | Hub scheduler | Manual / external cron |
| Run history | Persisted in Hub | Local JSON files |
| Multi-agent visibility | Yes | Per-machine |

For production deployments, use the Hub for centralized job management.

## MCP Tools for Jobs

Agents can manage jobs programmatically via MCP:

```python
# Create a job
create_job(
    name="Nightly Backup Check",
    agent="kimi",
    message="Verify backups completed and report status",
    cron="0 2 * * *",
    session_mode="new"
)

# List jobs
jobs = list_jobs(agent="kimi")

# Get job details
job = get_job("job-abc123")

# Enable/disable
toggle_job("job-abc123", enabled=False)

# Delete
delete_job("job-abc123")

# Run immediately
run_job("job-abc123")
```

## Troubleshooting

### "croniter is required for cron validation"

Install the jobs extra:

```bash
pip install "agentweave-ai[jobs]"
```

### Jobs not firing

1. Check if job is enabled: `agentweave jobs get <id>`
2. Verify Hub is running (for HTTP transport)
3. Check watchdog is active: `agentweave status`
4. Review Hub logs for scheduler errors

### Invalid cron expression

Test your cron expression with:

```bash
# This will validate and show next run time
agentweave jobs create --name test --agent claude --message test --cron "0 9 * * *"
```

Common mistakes:
- Using `@daily` syntax (use `0 0 * * *` instead)
- Seconds field (cron has minute granularity)
- Invalid ranges like `0-24` (hours are 0-23)

## See Also

- [CLI Commands Reference](../reference/cli-commands.md#jobs)
- [MCP Tools Reference](../reference/mcp-tools.md#jobs)
- [Hub API Reference](../reference/hub-api.md#jobs)
