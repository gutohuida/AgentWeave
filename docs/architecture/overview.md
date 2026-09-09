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
agent receives a short-lived run token bound to its project, agent identity, and active run. Two
adapters — HTTP and MCP — expose the same governed action set; there is no third. Identity is never
accepted from a request body or header, on either adapter.

## The agent capability plane

The plane is one HTTP contract with two front doors, and a run is told which one it has at turn
start.

- **HTTP** is the contract. Its operations live under `/api/v1/agent-actions`, the Hub's own
  address reaches the spawned run as `HUB_URL`, and the run's credential reaches it as
  `AW_RUN_TOKEN`, presented as `Authorization: Bearer`. Nothing else is needed: a run holding those
  two environment variables can send messages, create and update tasks, ask the operator a
  question, record evidence, and submit specification documents.
- **MCP** is an adapter over that contract, injected into harnesses that accept it. Every tool it
  serves is one HTTP operation; the tool's arguments are not always spelled the way the route
  spells them, which is why the two renderings are generated from one description
  (`hub/hub/api/v1/agents.py`) rather than written twice.

A run whose harness has no MCP is therefore not a run without capability. It is told the HTTP form
of the same operations — variables named, values never interpolated, because the notice is
prepended to the durable turn prompt.

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
