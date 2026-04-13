# agentweave.yml Reference

`agentweave.yml` is the single source of truth for your AgentWeave project configuration. It defines project metadata, Hub connection, agents, and scheduled jobs.

This file **should be committed** to version control. It contains no secrets — API keys and tokens are handled separately via environment variables.

---

## File Location

`agentweave.yml` lives at your project root:

```
my-project/
├── agentweave.yml          # Project configuration
├── .agentweave/            # Runtime state (gitignored)
├── src/
└── ...
```

---

## Full Example

```yaml
# AgentWeave Configuration
# This file defines your project settings, agents, and scheduled jobs.
# It SHOULD be committed to version control.
#
# Secret values (API keys, tokens) should NOT be added here.
# Use environment variables or a .env file instead (gitignored).

project:
  name: "My Awesome App"
  mode: hierarchical

hub:
  url: http://localhost:8000

agents:
  claude:
    runner: claude
    roles:
      - tech_lead
      - backend_dev
    yolo: false
    pilot: false

  kimi:
    runner: kimi
    roles:
      - frontend_dev
    pilot: true

  minimax:
    runner: claude_proxy
    model: MiniMax-M2.7
    env:
      - MINIMAX_API_KEY
    yolo: true

jobs:
  daily-standup:
    schedule: "0 9 * * 1-5"
    agent: claude
    prompt: "Generate a daily standup summary based on yesterday's completed tasks"
    enabled: true

  weekly-review:
    schedule: "0 17 * * 5"
    agent: kimi
    prompt: "Review all pending tasks and send reminders"
    enabled: false
```

---

## Sections

### `project`

Project metadata.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | `"Unnamed Project"` | Project name shown in dashboard |
| `mode` | string | `"hierarchical"` | Collaboration mode: `hierarchical`, `peer`, or `review` |

**Example:**
```yaml
project:
  name: "API Server"
  mode: hierarchical
```

#### Modes

- **`hierarchical`** — Principal agent delegates tasks, delegates report back
- **`peer`** — Equal collaboration, any agent can assign to any other
- **`review`** — Specialized for code review workflows

---

### `hub`

Hub connection settings.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | `"http://localhost:8000"` | Hub URL (no trailing slash) |

**Example:**
```yaml
hub:
  url: http://localhost:8000
```

The API key is fetched automatically from the Hub's `/setup/token` endpoint on first activate.

---

### `agents`

Map of agent name to agent configuration.

#### Agent Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `"claude"` | How to invoke the agent: `claude`, `kimi`, `native`, `claude_proxy`, `manual` |
| `model` | string | (auto) | Model name for claude_proxy agents |
| `roles` | list | `[]` | List of role IDs for this agent |
| `env` | list | `[]` | List of environment variable names to pass to the agent |
| `yolo` | boolean | `false` | Enable yolo mode (auto-execute without confirmations) |
| `pilot` | boolean | `false` | Enable pilot mode (human controls execution) |

**Example:**
```yaml
agents:
  claude:
    runner: claude
    roles: [tech_lead, backend_dev]

  kimi:
    runner: kimi
    pilot: true

  minimax:
    runner: claude_proxy
    model: MiniMax-M2.7
    env: [MINIMAX_API_KEY]
    yolo: true
```

#### Runners

| Runner | Description |
|--------|-------------|
| `claude` | Claude Code CLI (`claude`) |
| `kimi` | Kimi Code CLI (`kimi`) |
| `native` | Use the agent name as the CLI command |
| `claude_proxy` | Claude CLI with custom API endpoint (for MiniMax, GLM, etc.) |
| `manual` | No CLI integration (relay prompts only) |

#### Environment Variables

The `env` field lists environment variable **names**, not values:

```yaml
# CORRECT: List of variable names
env:
  - MINIMAX_API_KEY
  - ANTHROPIC_API_KEY

# WRONG: Key-value pairs will be rejected
env:
  MINIMAX_API_KEY: "secret-value"
```

Actual values are read from your shell environment or a `.env` file at runtime.

---

### `jobs`

Scheduled AI jobs (optional). Map of job name to job configuration.

#### Job Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `schedule` | string | (required) | Cron expression: `minute hour day month weekday` |
| `agent` | string | (required) | Agent to run the job |
| `prompt` | string | (required) | Message/prompt to send to the agent |
| `enabled` | boolean | `true` | Whether the job is active |

**Example:**
```yaml
jobs:
  morning-report:
    schedule: "0 9 * * 1-5"    # Weekdays at 9am
    agent: claude
    prompt: "Check overnight CI failures and report"
    enabled: true

  weekly-cleanup:
    schedule: "0 0 * * 0"       # Sundays at midnight
    agent: kimi
    prompt: "Archive old tasks and generate summary"
    enabled: false             # Paused
```

#### Cron Format

5 fields separated by spaces:

```
minute(0-59) hour(0-23) day(1-31) month(1-12) weekday(0-6, 0=Sunday)
```

Special characters:
- `*` — any value
- `*/n` — every n units
- `n-m` — range
- `n,m` — list

**Examples:**

| Expression | Meaning |
|------------|---------|
| `0 9 * * 1-5` | Weekdays at 9am |
| `*/5 * * * *` | Every 5 minutes |
| `0 0 1 * *` | First of every month at midnight |
| `0 0 * * 0` | Every Sunday at midnight |

---

## Applying Changes

After editing `agentweave.yml`, run:

```bash
agentweave activate
```

This reconciles your configuration with the runtime state.

---

## Validation

The CLI validates `agentweave.yml` on load:

- YAML syntax must be valid
- `project.mode` must be one of: `hierarchical`, `peer`, `review`
- `agents.<name>.runner` must be one of: `claude`, `kimi`, `native`, `claude_proxy`, `manual`
- `agents.<name>.env` must be a list of strings (not key-value pairs)
- `jobs.<name>.schedule` must be a valid 5-field cron expression

Validation errors are reported with line numbers:

```
Line 15: agents.minimax.env: env must be a list of variable names, not key-value pairs
```

---

## Migration from Old Setup

If you have an existing `.agentweave/session.json` but no `agentweave.yml`:

```bash
agentweave init
```

This detects your existing session and generates `agentweave.yml` from it.

---

## See Also

- [Quick Start Guide](../getting-started/quickstart.md)
- [Configuration Guide](../getting-started/configuration.md)
- [CLI Commands Reference](cli-commands.md)
