# Installation

AgentWeave consists of two parts: the **CLI** (Python package) and the **Hub** (self-hosted server, native by default with optional Docker support).

## CLI Installation

The CLI requires **Python 3.8+**.

### Basic Install

```bash
pip install agentweave-ai
```

### With MCP Support (Recommended)

```bash
pip install "agentweave-ai[mcp]"
```

This includes `fastmcp` and `pyyaml` for the MCP server and declarative configuration. The core CLI supports Python 3.8+, but the `fastmcp` dependency is installed only on Python 3.10+, so use Python 3.10 or newer for MCP mode.

### Development Install

If you're contributing to AgentWeave:

```bash
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave
pip install -e ".[dev]"
```

## Hub Installation

The Hub runs **natively** by default — no Docker required. Docker remains supported for
coordination-only or remote deployments.

### Automatic Setup (Recommended)

```bash
pip install agentweave-hub
agentweave hub start
```

This runs the Hub via uvicorn on the host, scaffolds `~/.agentweave/hub/` (database, `.env`),
runs migrations, and fetches the API key.

The Hub will be available at **http://localhost:8000**.

### Docker Setup (Advanced)

For a containerized instance instead — e.g. a coordination-only or remote deployment:

```bash
agentweave hub start --docker
```

This requires **Docker** and **Docker Compose**, downloads the configuration, starts the
container, and fetches the API key.

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

# Start the Hub
docker compose up -d
```

#### Build from Source

```bash
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave/hub
cp .env.example .env
# Optional: edit .env to set AW_BOOTSTRAP_API_KEY
docker compose up --build -d
```

## Verify Installation

```bash
agentweave --help
aw --help                    # alias
agentweave-watch --help      # watchdog
agentweave hub status        # check Hub status
```

## Next Steps

See the [Quick Start Guide](quickstart.md) to initialize your first project.
