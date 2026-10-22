---
description: Every agentweave command and flag.
---

# CLI commands

The CLI manages the local AgentWeave instance. It does not manage collaboration: there is no command
for messages, tasks, agents or jobs. Operators use the app, and agents use their
[tools](agent-tools.md). The one exception is `vault add`, because adding a folder of files is
easier from a terminal.

`aw` is an alias for `agentweave`.

## Global options

| Option | Default | Meaning |
|---|---|---|
| `--port PORT` | `8000` | The instance's port. |
| `--profile NAME` | `default` | A separate instance with its own state under `~/.agentweave/hub/profiles/NAME/`. A profile other than `default` also needs `--port`. |
| `--version` | | Print the version. |

## `agentweave` — start or open

```bash
agentweave [--port PORT] [--profile NAME] [--docker] [--local] [--no-detach] [--desktop-shortcut]
```

Starts the Hub if it is not running, registers (or reopens) the current directory as a project, and
opens that project's Overview. On first launch it creates `~/.agentweave/hub/`, generates the
instance key, and runs the database migrations. Later launches run any new migrations.

| Option | Meaning |
|---|---|
| `--docker` | Run the Hub in Docker instead. See [Running in Docker](../guides/docker.md). |
| `--local` | Docker, built from a local `./hub/` checkout (contributors). |
| `--no-detach` | Run in the foreground instead of in the background. |
| `--desktop-shortcut` | Windows: create a desktop shortcut that opens the app. |

The app opens in its own window when possible: pywebview if you installed `agentweave-ai[app]`,
otherwise a Chromium or Edge app window, otherwise a normal browser tab.

## `agentweave doctor`

```bash
agentweave doctor [--json] [--port PORT] [--profile NAME]
```

Checks readiness without starting anything or writing any state. It checks the Python version, the
Hub installation, the agent CLIs on `PATH` (and Copilot's sign-in), whether something is already on
the port, the database, the state directory's permissions, the symlink privilege on Windows, and
whether the bundled app is current. `--json` gives stable check ids. Secret values are never
printed. (`--no-network` is accepted for compatibility.)

## `agentweave status`

```bash
agentweave status [--port PORT] [--profile NAME]
```

Whether the instance is running, its URL and process id, and the projects it holds.

## `agentweave stop`

```bash
agentweave stop [--port PORT] [--profile NAME] [--local]
```

Stops the instance, native or Docker. A stale process id is never used to stop an unrelated process.

## `agentweave reset`

```bash
agentweave reset [--yes] [--all] [--profile NAME]
```

Deletes the instance's database after confirmation, so the next start is clean. `--all` also removes
the generated `.env` (and with it the instance key) and the log files. Reset **never** touches your
project directories or their contents. It reports any file it could not delete instead of claiming
success.

## `agentweave vault add`

```bash
agentweave vault add PATHS... (--distil | --no-distil)
    [--private | --tracked]
    [--type transcript|document|rules|example|note]
    [--dated YYYY-MM-DD]
    [--project ID] [--json] [--port PORT] [--profile NAME]
```

Adds files or folders to a project's [knowledge vault](../guides/knowledge-vault.md). You must
say whether to extract facts now (`--distil`) or not (`--no-distil`). `--private` keeps the sources
on this machine only, and `--tracked` puts them in the repository. The project defaults to the one
registered for the current directory.

Limits: text up to 1 MiB, PDFs and images up to 10 MiB, at most 200 files per call. The command
authenticates with `AW_KEY` if set, otherwise with the local instance's key.
