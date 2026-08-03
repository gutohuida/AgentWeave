# AgentWeave

AgentWeave is a self-hosted workspace where AI coding agents collaborate through one Hub-owned
runtime. The Hub owns execution, conversations, tasks, messages, jobs, specifications, usage, and
the operator dashboard.

## Quick start

```bash
uv tool install agentweave-ai --with agentweave-hub
agentweave
```

The first launch creates user-local state, runs migrations, starts the Hub, and opens the dashboard
at `http://localhost:8000`.

## Product model

- Operators use the dashboard.
- Running agents use the least-privilege agent capability plane.
- The CLI starts, diagnoses, reports, stops, or resets the local instance.
- The Hub is the only collaboration and execution runtime.

Start with the [quick start](getting-started/quickstart.md), review the
[CLI reference](reference/cli-commands.md), or read the [architecture](architecture/overview.md).
