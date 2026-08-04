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

The local operator authenticates with one automatically discovered instance credential; project
identity is explicit in operator API paths and does not come from authentication. Each running
agent receives a short-lived run token bound to its project, agent identity, and active run. HTTP,
MCP, and agent CLI adapters expose the same governed action set.

## Project and filesystem boundary

One Hub owns a collection of directory-backed projects. The database project ID is stable across
renames and explicit relocation, while a canonical working-directory binding and non-secret
`.agentweave/project.json` marker prevent aliases and copied directories from silently merging.

Every runtime filesystem operation resolves through the selected project's workspace service;
the Hub process directory is never project identity. Frontend server-state keys and URLs carry the
project ID, and one operator SSE stream stamps each event with trusted project context. Docker
registrations are additionally restricted to paths beneath one configured mounted workspace root.

## Execution

The Hub validates launchability, creates a run, spawns the configured runner, streams structured
events, accounts for usage, and persists the final outcome. Agent processes do not poll local files
for work.

## Local application lifecycle

Bare `agentweave` owns setup and launch. It registers or reopens its invocation directory in the
one running instance and opens that project's overview. `doctor`, `status`, `stop`, and `reset` are
the only CLI subcommands because operator collaboration belongs to the dashboard and agent
collaboration belongs to the capability plane.

## Repository components

- `src/agentweave/` — lifecycle CLI and agent-facing adapters
- `hub/hub/` — FastAPI backend, scheduler, execution, persistence
- `hub/ui/` — React dashboard
- `openspec/` — authoritative product specifications
