---
description: Install AgentWeave, start it, and check that your machine is ready.
---

# Installation

AgentWeave is one Python package, and it runs as one local app.

## Requirements

- **Python 3.11 or later.**
- **At least one agent CLI**, installed and signed in: [Claude Code](https://docs.anthropic.com/en/docs/claude-code),
  [Codex](https://github.com/openai/codex) or [GitHub Copilot CLI](https://github.com/github/copilot-cli)
  (version 1.0.81 or later). AgentWeave launches these CLIs and uses the sign-in they already
  have. It does not ask for your provider keys.
- **git**, for the per-task worktrees and the merge on approval. A project that is not a git
  repository still works, but its agents share one directory and nothing is merged.

## Install

```bash
pip install agentweave-ai
```

`agentweave-ai` brings the Hub (the local server and the app it serves) with it. There is no second
package to install and no configuration file to write.

To open the app in its own chromeless window instead of a browser tab, install the optional extra:

```bash
pip install "agentweave-ai[app]"
```

## Start it

Run it from the directory you want to work on:

```bash
cd ~/code/my-project
agentweave
```

On first launch AgentWeave:

1. creates its state under `~/.agentweave/hub/` (a SQLite database and a generated `.env`);
2. runs the database migrations;
3. starts the Hub on `http://localhost:8000`;
4. registers the current directory as a project, and opens that project's Overview.

Run `agentweave` again from another directory to add that project to the same running instance.
Closing the window leaves the Hub running. Use `agentweave stop` to stop it.

!!! tip "Another port, or a separate instance"
    `agentweave --port 8010` moves the app to another port. `agentweave --profile NAME --port PORT`
    runs a completely separate instance, with its own database under
    `~/.agentweave/hub/profiles/NAME/`. This is useful for trying things out without touching your
    real projects.

## Check your machine

```bash
agentweave doctor
```

`doctor` checks everything AgentWeave needs, and it starts nothing and writes nothing while it
checks:

- the Python version and the Hub installation;
- which agent CLIs are on your `PATH`, and whether Copilot is signed in;
- whether something is already running on the port;
- that the database is reachable;
- the state directory's permissions, and the symlink privilege on Windows;
- whether the bundled app is current.

Add `--json` for machine-readable output with stable check ids. Secret values are never printed.

The other everyday commands:

```bash
agentweave status    # is it running, where, and which projects it holds
agentweave stop      # stop it
agentweave reset     # delete local Hub state and start clean (asks first)
agentweave --version
```

`aw` is a short alias for `agentweave`. The full list is in the [CLI reference](../reference/cli-commands.md).

## Upgrading

```bash
pip install -U agentweave-ai
agentweave stop
agentweave
```

The next start runs any new database migrations against your existing state. Your projects and
their history stay where they are.

### The app updates itself

In the app window, AgentWeave also checks PyPI (at most once a day, and quietly if it cannot reach it)
for a newer final release. When one exists, **App settings → Hub connection → Updates** offers
**Update to *version***. The window is the part that does the updating, so the settings appear only
there, not in a browser tab.

An update goes in this order:

1. If work is running, the button names it and asks you to confirm, because updating stops it.
2. The Hub is stopped, and a copy of its database is saved under
   `~/.agentweave/hub/update-backups/`. The newest three copies are kept.
3. `agentweave-ai` and `agentweave-hub` are upgraded with pip.
4. The Hub is started again, and must report the new version within two minutes.

If any step after the copy fails, the previous version is installed again, the database copy is put
back, the old Hub is started, and the window says why the update failed. Nothing is left half
applied. Only one update runs at a time, and an update is refused while another Hub of the same
installation is running on another port.

**Update automatically when I open AgentWeave** is on by default. With it on, opening the app
upgrades it first when a newer release exists, nothing is running, and no other window or Hub of the
installation is open. The Update button stays either way. To check a different package index, set
[`AW_UPDATE_INDEX_URL`](../reference/env-variables.md#the-cli).

A Hub run from a git checkout, as the AgentWeave project's own developers do, is not upgraded with
pip. Its updates come from the checkout's **local master**: it counts the commits master has that the
running Hub lacks, and never fetches. The Update button restarts the Hub onto master, only while the
checkout is on master, and lists any uncommitted files before asking you to confirm. Before it stops
the Hub, it runs the new migrations on a copy of the database as a rehearsal, and a failure there
leaves the running Hub untouched. If the restarted Hub does not come up healthy, the database is
restored and the previous commit is started. The checkout's own switch, **Restart onto master
automatically when I open AgentWeave**, is off by default.

## Docker

To run the Hub in a container, for example on a shared or headless machine, see
[Running in Docker](../guides/docker.md).

## Next

[Your first project](quickstart.md) walks through adding agents, writing a specification, and
taking one task all the way to a merge.
