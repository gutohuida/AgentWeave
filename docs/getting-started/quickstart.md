# Quick start

## Install

```bash
pip install agentweave-ai
```

One package, and it brings the Hub with it. Requires Python 3.11+.

## Launch

```bash
agentweave
```

Run this command from the directory you want to use as a project. On first launch AgentWeave
creates `~/.agentweave/hub/`, initializes its SQLite database, starts the native Hub, registers the
current directory, and opens that project's Overview. Configure agents in the dashboard and launch
a conversation from an agent page.

To add or reopen another project, change into that directory and run `agentweave` again. The same
Hub instance opens it without mixing project agents, conversations, tasks, settings, or files. You
can also use **Open existing project** or **Create new project** from the dashboard project rail.

## Daily commands

```bash
agentweave doctor
agentweave status
agentweave stop
```

Use `agentweave reset` only when you intentionally want to delete local Hub state and start clean.
Reset never deletes registered project directories or source content.

## Troubleshooting

`agentweave doctor` checks Python support, the Hub installation, available runner CLIs, port 8000,
SQLite accessibility, and permissions without starting the app or creating state.
