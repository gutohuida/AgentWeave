# Quick start

## Install

```bash
uv tool install agentweave-ai --with agentweave-hub
```

You can also install both packages into a virtual environment:

```bash
pip install agentweave-ai agentweave-hub
```

## Launch

```bash
agentweave
```

On first launch AgentWeave creates `~/.agentweave/hub/`, initializes its SQLite database, starts
the native Hub, and opens the dashboard. Configure agents in the dashboard and launch a
conversation from an agent page.

## Daily commands

```bash
agentweave doctor
agentweave status
agentweave stop
```

Use `agentweave reset` only when you intentionally want to delete local Hub state and start clean.

## Troubleshooting

`agentweave doctor` checks Python support, the Hub installation, available runner CLIs, port 8000,
SQLite accessibility, and permissions without starting the app or creating state.
