# Architecture overview

AgentWeave has one runtime: the Hub.

```text
Operator dashboard ─┐
                    ├─ Hub API + database ─ execution scheduler ─ runner processes
Agent capability API┘          │
                               ├─ conversations, messages, tasks, jobs
                               ├─ logs, streams, traces, usage
                               └─ specifications and project settings
```

## Trust boundaries

Operators authenticate with project credentials. Each running agent receives a short-lived run
token bound to its project, agent identity, and active run. HTTP, MCP, and agent CLI adapters expose
the same governed action set.

## Execution

The Hub validates launchability, creates a run, spawns the configured runner, streams structured
events, accounts for usage, and persists the final outcome. Agent processes do not poll local files
for work.

## Local application lifecycle

Bare `agentweave` owns setup and launch. `doctor`, `status`, `stop`, and `reset` are the only CLI
subcommands because operator collaboration belongs to the dashboard and agent collaboration belongs
to the capability plane.

## Repository components

- `src/agentweave/` — lifecycle CLI and agent-facing adapters
- `hub/hub/` — FastAPI backend, scheduler, execution, persistence
- `hub/ui/` — React dashboard
- `openspec/` — authoritative product specifications
