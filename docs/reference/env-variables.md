---
description: Every environment variable the Hub, the CLI and agent runs read or set.
---

# Environment variables

Most people never set any of these. `agentweave` writes what it needs into
`~/.agentweave/hub/.env` on first launch.

## The Hub

Read from the environment, or from a `.env` in the Hub process's working directory.

| Variable | Default | Effect |
|---|---|---|
| `DATABASE_URL` | none | The database to open. **The Hub refuses to start without one** rather than guess. `agentweave` sets it for you (`~/.agentweave/hub/data/agentweave.db`, or the profile's own). An existing value overrides `--profile`. |
| `AW_BOOTSTRAP_API_KEY` | generated | The instance's operator key (`aw_live_…`). Minted on first start if the database has none. |
| `AW_TICKET_SECRET` | random per process | Signs the short-lived tickets used for the live event stream. |
| `AW_TICKET_TTL` | `300` | Ticket lifetime, in seconds. |
| `AW_MAX_BODY_SIZE` | `1048576` | Largest request body, in bytes. Vault file uploads are allowed 10 MiB. |
| `AW_WORKSPACE_ROOT` | unset | When set, projects are accepted only beneath this path. Docker sets `/workspaces`. |
| `AW_CORS_ORIGINS` | unset | Extra allowed origins. By default, same origin only. |
| `AW_RUNTIME` | detected | `docker` or `native`, as reported by `/health`. |
| `AW_TRACE_PUSH_INTERVAL` | `5.0` | Seconds between pushes to an OTLP trace collector (minimum 0.2). |
| `HUB_URL` | the Hub's own address | The address handed to agent runs. Set it if runs must reach the Hub by another name. |
| `CODEX_HOME` | Codex's default | Where the Hub reads Codex's model list. |
| `COPILOT_HOME` | `~/.copilot` | Where the Hub reads the Copilot sign-in it copies into its own Copilot homes. |
| `AW_HOST`, `AW_PORT` | `127.0.0.1`, `8000` | Used only by the `agentweave-hub` console script and the Docker image. With `agentweave`, use `--port`. |

A Copilot runner using your own key names a variable here, such as `ANTHROPIC_API_KEY`. The Hub
reads that variable at launch, stores only its name, and refuses names that point at the Hub's own
credentials.

## Docker

| Variable | Default | Effect |
|---|---|---|
| `AW_WORKSPACE_HOST_ROOT` | `./workspaces` | The host directory mounted at `/workspaces`. |
| `AW_HUB_IMAGE` | `ghcr.io/gutohuida/agentweave-hub:latest` | The image to run. |
| `AW_PORT` | `8000` | The host port. |

## The CLI

| Variable | Default | Effect |
|---|---|---|
| `AW_LOG_LEVEL` | `WARNING` | CLI log level. |
| `AW_LOG_FILE` | unset (stderr) | Write CLI logs to a file. |
| `AW_KEY` | the local instance's key | Operator key for `agentweave vault add`. |
| `DATABASE_URL` | per profile | Passed through to the Hub, and overrides `--profile`. |

## UI development

| Variable | Default | Effect |
|---|---|---|
| `AW_DEV_HUB` | `http://localhost:8000` | The Hub that `npm run dev` proxies to. |

## Set for every agent run

The Hub sets these in each run's environment. They are not for you to set.

| Variable | Meaning |
|---|---|
| `HUB_URL` | Where the run reaches the Hub. |
| `AW_RUN_TOKEN` | The run's own credential, valid only while the run is live. |
| `AW_RUN_ID`, `AW_AGENT_IDENTITY` | Which run, and which agent. |
| `AW_WORKSPACE_DIR` | The run's workspace. |
| `AW_PERMISSION_POSTURE`, `AW_REACH_GRANTS` | Who answers permission requests, and what extra reach is granted. |
| `AW_DECISION_TIMEOUT`, `AW_QUESTION_TIMEOUT` | How long to wait for your permission decision (120 s) and your answer (240 s), unless the agent's settings say otherwise. |
| `AW_TURN_DEPTH` | How many agent-to-agent hops led to this turn. |

The Hub strips its own secrets from every run: `DATABASE_URL`, `AW_BOOTSTRAP_API_KEY`,
`AW_TICKET_SECRET`, `HUB_API_KEY` and `HUB_PROJECT_ID`. For Copilot runs it also strips GitHub
token variables.
