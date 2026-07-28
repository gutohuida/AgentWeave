## ADDED Requirements

### Requirement: Activate command exists
The CLI SHALL provide `agentweave activate` as a single idempotent command that applies `agentweave.yml` to the full runtime state. Running it multiple times SHALL produce the same result.

#### Scenario: Activate on clean project
- **WHEN** user runs `agentweave activate` in a project with `agentweave.yml` but no prior setup
- **THEN** CLI configures transport, registers agents, sets up MCP, and starts the watchdog in sequence
- **THEN** CLI prints a summary of each step taken

#### Scenario: Activate is idempotent
- **WHEN** user runs `agentweave activate` a second time with no changes to `agentweave.yml`
- **THEN** CLI detects all state is already current and exits successfully without modifying anything

---

### Requirement: Activate configures transport from agentweave.yml
`agentweave activate` SHALL read the `hub.url` from `agentweave.yml`, fetch the API key from the Hub's `/setup/token` endpoint (if `transport.json` does not already exist), and write `transport.json`. If `transport.json` already exists and points to the same Hub URL, it SHALL skip this step.

#### Scenario: First-time transport setup
- **WHEN** `agentweave activate` runs and no `transport.json` exists
- **THEN** CLI calls `GET <hub.url>/setup/token` to fetch the API key
- **THEN** CLI writes `transport.json` with type `http`, the Hub URL, and the API key
- **THEN** CLI prints "Connected to Hub at <url>"

#### Scenario: Transport already configured
- **WHEN** `agentweave activate` runs and `transport.json` already exists with the correct Hub URL
- **THEN** CLI skips transport configuration and prints "Transport: already configured"

---

### Requirement: Activate syncs agents from agentweave.yml
`agentweave activate` SHALL read the `agents:` section of `agentweave.yml` and update `session.json` to reflect the declared agents. New agents SHALL be added. Existing agents SHALL have their runner, model, roles, env, yolo, and pilot flags updated. Agents in `session.json` but absent from `agentweave.yml` SHALL NOT be deleted — a notice SHALL be printed instead.

#### Scenario: New agent added to YAML
- **WHEN** `agentweave.yml` declares an agent not currently in `session.json`
- **THEN** CLI adds the agent to `session.json` with the declared configuration
- **THEN** CLI prints "Agent '<name>' added"

#### Scenario: Existing agent config updated
- **WHEN** `agentweave.yml` declares an agent already in `session.json` with different config
- **THEN** CLI updates the agent's configuration in `session.json`
- **THEN** CLI prints "Agent '<name>' updated"

#### Scenario: Agent in session but not in YAML
- **WHEN** `session.json` contains an agent not declared in `agentweave.yml`
- **THEN** CLI prints "Notice: agent '<name>' is in session but not in agentweave.yml — run `agentweave agent remove <name>` to clean up"
- **THEN** CLI does NOT remove the agent or its data

---

### Requirement: Activate sets up MCP
`agentweave activate` SHALL run MCP registration (equivalent to `agentweave mcp setup`) if MCP is not already registered for the current project. If already registered, it SHALL skip this step.

#### Scenario: MCP not yet registered
- **WHEN** `agentweave activate` runs and MCP server is not registered
- **THEN** CLI registers the MCP server and prints "MCP: registered"

#### Scenario: MCP already registered
- **WHEN** `agentweave activate` runs and MCP server is already registered
- **THEN** CLI prints "MCP: already registered" and skips

---

### Requirement: Activate starts the watchdog
`agentweave activate` SHALL start the watchdog process if it is not already running. If the watchdog is already running, it SHALL skip this step.

#### Scenario: Watchdog not running
- **WHEN** `agentweave activate` runs and no watchdog PID file exists or the process is dead
- **THEN** CLI starts the watchdog and prints "Watchdog: started"

#### Scenario: Watchdog already running
- **WHEN** `agentweave activate` runs and a healthy watchdog is already running
- **THEN** CLI prints "Watchdog: already running" and skips

---

### Requirement: Activate syncs jobs from agentweave.yml
If `agentweave.yml` contains a `jobs:` section, `agentweave activate` SHALL create or update those jobs on the Hub. Jobs in the Hub not present in the YAML SHALL NOT be deleted. A job's `enabled` field SHALL control whether it is active or paused on the Hub.

#### Scenario: New job declared in YAML
- **WHEN** `agentweave.yml` declares a job not yet on the Hub
- **THEN** CLI creates the job on the Hub with the declared schedule, agent, and prompt
- **THEN** CLI prints "Job '<name>' created"

#### Scenario: Job enabled flag toggled
- **WHEN** `agentweave.yml` sets `enabled: false` for an existing active job
- **THEN** CLI pauses the job on the Hub
- **THEN** CLI prints "Job '<name>' paused"

#### Scenario: No jobs section
- **WHEN** `agentweave.yml` has no `jobs:` section
- **THEN** CLI skips job sync entirely with no output

---

### Requirement: Activate requires agentweave.yml
`agentweave activate` SHALL fail with a clear error if no `agentweave.yml` exists in the current directory. It SHALL suggest running `agentweave init` first.

#### Scenario: Missing agentweave.yml
- **WHEN** user runs `agentweave activate` in a directory without `agentweave.yml`
- **THEN** CLI prints "No agentweave.yml found. Run `agentweave init` to create one."
- **THEN** CLI exits with a non-zero exit code
