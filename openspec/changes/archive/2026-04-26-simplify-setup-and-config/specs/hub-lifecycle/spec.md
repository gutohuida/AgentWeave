## ADDED Requirements

### Requirement: Hub start command
The CLI SHALL provide `agentweave hub start` that downloads Hub config files to `~/.agentweave/hub/`, starts the Hub via `docker compose up -d`, waits for Hub to be healthy, and prints the Hub URL on success. If `docker-compose.yml` already exists in `~/.agentweave/hub/`, it SHALL skip the download. If Hub is already running, it SHALL print a message and exit successfully.

#### Scenario: First-time hub start
- **WHEN** user runs `agentweave hub start` and no Hub files exist
- **THEN** CLI downloads `docker-compose.yml` and `.env` to `~/.agentweave/hub/`
- **THEN** CLI generates an API key and writes it to `.env` as `AW_BOOTSTRAP_API_KEY`
- **THEN** CLI runs `docker compose up -d` from `~/.agentweave/hub/`
- **THEN** CLI polls `GET http://localhost:8000/health` until healthy (max 30s)
- **THEN** CLI prints "Hub ready at http://localhost:8000"

#### Scenario: Hub already running
- **WHEN** user runs `agentweave hub start` and Hub is already responding at `localhost:8000`
- **THEN** CLI prints "Hub is already running at http://localhost:8000" and exits with code 0

#### Scenario: Docker not available
- **WHEN** user runs `agentweave hub start` and `docker` is not in PATH
- **THEN** CLI prints a clear error message explaining Docker is required with a link to install instructions
- **THEN** CLI exits with a non-zero exit code

---

### Requirement: Hub stop command
The CLI SHALL provide `agentweave hub stop` that runs `docker compose down` in `~/.agentweave/hub/`. If Hub is not running, it SHALL exit successfully with an informational message.

#### Scenario: Successful stop
- **WHEN** user runs `agentweave hub stop` and Hub is running
- **THEN** CLI runs `docker compose down` from `~/.agentweave/hub/`
- **THEN** CLI prints "Hub stopped"

#### Scenario: Hub not running
- **WHEN** user runs `agentweave hub stop` and Hub is not running
- **THEN** CLI prints "Hub is not running" and exits with code 0

---

### Requirement: Hub status command
The CLI SHALL provide `agentweave hub status` that checks whether the Hub container is running and whether it is healthy, then prints a summary.

#### Scenario: Hub running and healthy
- **WHEN** user runs `agentweave hub status` and Hub responds to health check
- **THEN** CLI prints Hub URL, status "running", and version if available

#### Scenario: Hub not running
- **WHEN** user runs `agentweave hub status` and Hub is not running
- **THEN** CLI prints status "stopped" and suggests running `agentweave hub start`

---

### Requirement: Hub auto-generates API key
The Hub SHALL generate a secure API key (`aw_live_<32 hex chars>`) on first startup if `AW_BOOTSTRAP_API_KEY` is unset or matches the placeholder value in `.env.example`. The key SHALL be stored in the database and remain stable across restarts.

#### Scenario: No key configured
- **WHEN** Hub starts and no `AW_BOOTSTRAP_API_KEY` is set (or it matches the placeholder)
- **THEN** Hub generates a new key, stores it in the database, and logs "Bootstrap API key auto-generated"

#### Scenario: Key already set
- **WHEN** Hub starts and `AW_BOOTSTRAP_API_KEY` is a non-placeholder value
- **THEN** Hub uses the provided key without generating a new one

---

### Requirement: Hub exposes setup token endpoint
The Hub SHALL expose `GET /setup/token` that returns the bootstrap API key. This endpoint SHALL only accept requests from `127.0.0.1`. It SHALL return `403 Forbidden` for any other origin. After the CLI has successfully called `agentweave activate` once, this endpoint MAY be disabled by the Hub.

#### Scenario: CLI fetches token from localhost
- **WHEN** `agentweave hub start` calls `GET http://localhost:8000/setup/token` from the same machine
- **THEN** Hub returns `{ "api_key": "aw_live_..." }` with status 200

#### Scenario: Remote request rejected
- **WHEN** a request arrives at `/setup/token` from an IP other than `127.0.0.1`
- **THEN** Hub returns 403 Forbidden
