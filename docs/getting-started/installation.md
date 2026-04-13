# Installation

AgentWeave consists of two parts: the **CLI** (Python package) and the **Hub** (self-hosted Docker server).

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

This includes the `fastmcp` dependency needed for the MCP server and watchdog.

### Development Install

If you're contributing to AgentWeave:

```bash
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave
pip install -e ".[dev]"
```

## Hub Installation

The Hub requires **Docker** and **Docker Compose**.

### Automatic Setup (Recommended)

The CLI handles Hub setup automatically:

```bash
agentweave hub start
```

This downloads the configuration, starts the container, and fetches the API key.

The Hub will be available at **http://localhost:8000**.

### Manual Setup (Advanced)

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

### Build from Source

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
agentweave-mcp               # MCP server (stdio)
agentweave hub status        # check Hub status
```

## Next Steps

See the [Quick Start Guide](quickstart.md) to initialize your first project.
