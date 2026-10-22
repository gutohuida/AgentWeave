---
description: Running the Hub in a container — the mounted workspace root, setup, and building from source.
---

# Running in Docker

The native install is the normal way to run AgentWeave. Use a container when you want the Hub on a
shared or headless machine.

```bash
agentweave --docker
```

This needs **Docker** and **Docker Compose**. It downloads the Compose configuration, starts the
container from `ghcr.io/gutohuida/agentweave-hub:latest` (set `AW_HUB_IMAGE` to use another image),
and fetches the instance key. `agentweave stop` stops it.

## The mounted workspace root

A container can only see directories mounted into it. The Compose file mounts one host directory,
`AW_WORKSPACE_HOST_ROOT` (default `./workspaces`), at `/workspaces` in the container, and sets
`AW_WORKSPACE_ROOT=/workspaces`. The Hub then accepts projects **only beneath that root**.

- Put every project you want to open beneath the host root, and register it by its
  **container-visible** path, for example `/workspaces/my-project`.
- A path the container cannot see, such as `/home/you/project` or `C:\Users\you\project`, is refused
  with a `project_workspace_not_mounted` diagnostic that names the configured root.
- The Hub never mounts the Docker socket and never guesses host-to-container path mappings.

This mount is also a real boundary on what agent runs can reach, whatever their
[permission posture](../reference/permission-postures.md).

!!! warning "Agent CLIs inside the container"
    Agents run where the Hub runs. In Docker mode, the agent CLIs and their sign-ins must be
    available inside the container. The native install, which uses the CLIs already on your
    machine, is the simpler path for most people.

## Manual setup

```bash
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example
cp .env.example .env
# Edit .env: set AW_WORKSPACE_HOST_ROOT to the directory holding your projects.
# Optionally set AW_BOOTSTRAP_API_KEY; one is generated if you do not.
docker compose up -d
```

## Building from source

```bash
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave/hub
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
```

The main Compose file deliberately has no `build:` section, because the manual setup above
downloads it into a directory with no source. `docker-compose.build.yml` is the override that adds
one for contributors.
