## ADDED Requirements

### Requirement: Triggered direct-trigger message IDs persist across watchdog restarts
The watchdog SHALL persist the IDs of direct-trigger messages it has already processed to `.agentweave/triggered_direct.json`. On startup, it SHALL load this file to pre-populate the in-memory `seen` set, preventing re-execution of already-triggered messages after a restart.

#### Scenario: Message ID written after spawning
- **WHEN** the watchdog successfully spawns an agent thread for a direct-trigger message
- **THEN** the message ID and current ISO timestamp are appended to `.agentweave/triggered_direct.json`

#### Scenario: Seen set pre-populated on startup
- **WHEN** the watchdog starts and `.agentweave/triggered_direct.json` exists
- **THEN** all message IDs with a timestamp within the last 24 hours are loaded into the in-memory `seen` set before polling begins

#### Scenario: Old entries pruned on load
- **WHEN** `.agentweave/triggered_direct.json` is loaded on startup
- **THEN** entries older than 24 hours are not added to the `seen` set and are removed from the file

#### Scenario: File missing on startup
- **WHEN** the watchdog starts and `.agentweave/triggered_direct.json` does not exist
- **THEN** the watchdog starts with an empty `seen` set (same as current behavior)

#### Scenario: Write failure is non-fatal
- **WHEN** writing to `.agentweave/triggered_direct.json` fails (e.g., permissions error)
- **THEN** the watchdog logs a warning and continues normally; the message is still added to the in-memory `seen` set for this run

### Requirement: Triggered messages file is not committed to version control
The `.agentweave/triggered_direct.json` file SHALL be excluded from version control via `.gitignore`, consistent with other runtime state files under `.agentweave/`.

#### Scenario: File excluded from git
- **WHEN** a developer runs `git status` after the watchdog has written triggered message IDs
- **THEN** `.agentweave/triggered_direct.json` does not appear as an untracked or modified file
