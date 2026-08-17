# Installation

AgentWeave is one application. Installing it and running it are one command each.

It requires **Python 3.11+**.

## Install

```bash
pip install agentweave-ai
```

That is the whole install. `agentweave-ai` brings the Hub — the local server and the web interface
it serves — with it; you do not install a second package.

## Run

```bash
agentweave
```

This starts the Hub natively via uvicorn, scaffolds `~/.agentweave/hub/` (database, `.env`), runs
migrations, opens the directory you ran it from as a project, and opens the app in its own window.
No Docker required.

The app is at **http://localhost:8000**, and stays there if you would rather use a normal browser
tab. `agentweave --port 8010` moves it.

The other four commands exist for when it will not start, or when you want it to stop:

```bash
agentweave doctor    # check environment readiness
agentweave status    # is it running?
agentweave stop      # stop it
agentweave reset     # destroy local Hub state and start clean
```

### Development Install

If you're contributing to AgentWeave:

```bash
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave
pip install -e ./hub
pip install -e ".[dev]"
```

The Hub goes in first, from the checkout, so pip resolves `agentweave-ai`'s dependency on it
locally instead of fetching a release from PyPI.

## Docker (Advanced)

For a containerized instance instead — a remote or headless deployment:

```bash
agentweave --docker
```

This requires **Docker** and **Docker Compose**, downloads the configuration, starts the
container, and fetches the API key.

#### Mounted workspace root

A containerized Hub can only see directories that are mounted into it. The Compose file maps
one host directory — `AW_WORKSPACE_HOST_ROOT` (default `./workspaces`) — to the container
workspace root `/workspaces`, and sets `AW_WORKSPACE_ROOT=/workspaces` so the Hub accepts
project registrations only beneath that root.

- Put (or move) every project you want to open somewhere beneath the host root, then register
  it with its **container-visible** path, e.g. `/workspaces/my-project`.
- A path that is not visible beneath the workspace root — for example a host-only path like
  `/home/you/project` or `C:\Users\you\project` — is refused with a typed
  `project_workspace_not_mounted` diagnostic that names the configured root.
- The Hub never mounts the Docker socket and never guesses host/container path mappings.

#### Manual Docker Setup

If you prefer manual control:

```bash
# Download config files
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example

# Create your .env
cp .env.example .env

# Optional: set a custom API key (auto-generated if not set)
# Edit .env and set AW_BOOTSTRAP_API_KEY

# Point the workspace root at the directory holding your projects
# Edit .env and set AW_WORKSPACE_HOST_ROOT=/path/to/your/projects

# Start the Hub
docker compose up -d
```

#### Build from Source

```bash
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave/hub
cp .env.example .env
# Optional: edit .env to set AW_BOOTSTRAP_API_KEY

docker build -t agentweave-hub:dev .
AW_HUB_IMAGE=agentweave-hub:dev docker compose up -d
```

The compose file carries no `build:` section on purpose — the manual setup above downloads it into
a directory with no source in it, and Compose builds instead of pulling when a service declares
both. `AW_HUB_IMAGE` is the supported way to point it at an image you built yourself.

## Verify Installation

```bash
agentweave --version
agentweave --help
aw --help                    # `aw` is an alias for `agentweave`
agentweave status            # is the Hub running?
agentweave doctor            # runtimes, ports, database, permissions
```

## Next Steps

See the [Quick Start Guide](quickstart.md) to initialize your first project.
