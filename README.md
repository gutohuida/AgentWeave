# AgentWeave

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![PyPI version](https://badge.fury.io/py/agentweave-ai.svg)](https://pypi.org/project/agentweave-ai/)

AgentWeave is a self-hosted workspace where multiple AI coding agents collaborate through one
Hub-owned runtime. The Hub provides the dashboard, agent execution, REST/SSE APIs, and the shared
agent capability plane. Legacy watchdog, local transport, Git transport, and collaboration CLI
workflows have been retired.

## Quick start

Install the CLI and native Hub together:

```bash
uv tool install agentweave-ai --with agentweave-hub
```

Then start AgentWeave:

```bash
agentweave
```

The first launch creates user-local Hub state, runs database migrations, starts the native Hub,
registers the current directory as a project, and opens its overview at `http://localhost:8000`.
Run `agentweave` from another directory to add or reopen that project in the same instance.
Projects keep separate agents, conversations, tasks, settings, caches, and runtime workspaces.

## CLI

The CLI manages only the local application instance:

```bash
agentweave                 # Start or open the app
agentweave doctor          # Check installation and runtime readiness
agentweave status          # Show instance URL, port, and project collection
agentweave stop            # Stop the local instance
agentweave reset           # Delete local Hub state after confirmation
agentweave --version
```

Messages, tasks, agents, jobs, questions, and project settings are managed through the dashboard or
the run-authenticated agent capability plane—not CLI subcommands.

## What the dashboard provides

- Agent roster, launch readiness, conversations, and streamed output
- Task board, messages, questions, and scheduled jobs
- Usage accounting, logs, traces, specifications, and project settings
- Direct Hub-owned execution for configured runners
- One least-privilege capability API shared by HTTP, MCP, and agent-facing CLI adapters

## Local state and configuration

The native instance stores state under `~/.agentweave/hub/`:

- `.env` — generated bootstrap identity and local configuration
- `data/agentweave.db` — SQLite database
- `hub.pid` — native process identity while running

Important environment settings include:

| Variable | Default | Purpose |
|---|---|---|
| `AW_BOOTSTRAP_API_KEY` | generated | Instance-local operator credential |
| `AW_BOOTSTRAP_PROJECT_ID` | unset | Legacy migration bootstrap only |
| `AW_WORKSPACE_ROOT` | unset | Container-visible project root in explicit Docker mode |
| `AW_WORKSPACE_HOST_ROOT` | `./workspaces` | Host directory mounted at `/workspaces` by Compose |
| `AW_PORT` | `8000` | Hub port |
| `AW_HOST` | `127.0.0.1` | Native bind address |
| `DATABASE_URL` | generated SQLite URL | Database connection |

Provider credentials remain environment variables available to the Hub process. Secret values are
never returned by readiness or diagnostic APIs.

## Agent capability plane

Every running agent receives a short-lived run token. That identity can access only the project and
agent actions permitted to that run. HTTP, MCP, and CLI adapters expose the same action set and
authorization semantics. Operator APIs use one instance credential and carry project identity in
their URL; choosing a project is navigation, not authentication.

## Development

```bash
pip install -e ".[dev]"
py -3.11 -m pytest tests/ -q

cd hub
py -3.11 -m pytest tests/ -q

cd ui
npm install
npm run test -- --run
npm run build
```

Exercise stateful product commands only inside `testbed/` or another throwaway directory. This
repository is the AgentWeave framework source and must not acquire root `.agentweave/`,
`agentweave.yml`, or `spec/` runtime state.

## Repository layout

```text
src/agentweave/   Python CLI and agent adapters
hub/hub/          FastAPI backend and Hub-owned execution
hub/ui/           React dashboard
tests/            CLI unit tests
hub/tests/        Hub tests
docs/             MkDocs documentation
openspec/         Current specifications and changes
```

## Links

- [Documentation](https://gutohuida.github.io/AgentWeave/)
- [GitHub](https://github.com/gutohuida/AgentWeave)
- [PyPI](https://pypi.org/project/agentweave-ai/)
- [Changelog](CHANGELOG.md)
