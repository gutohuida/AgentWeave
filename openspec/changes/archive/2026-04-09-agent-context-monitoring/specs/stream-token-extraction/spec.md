## ADDED Requirements

### Requirement: Watchdog extracts input_tokens from Claude stream result
The watchdog SHALL parse the `usage.input_tokens` field from the `result` JSONL message emitted by `claude --output-format stream-json --verbose` at the end of each turn, and write a `context_usage/<agent>.json` file with the computed context percentage.

#### Scenario: Successful token extraction
- **WHEN** a Claude agent turn completes and the watchdog receives a JSONL line with `{"type": "result", "usage": {"input_tokens": N, ...}}`
- **THEN** the watchdog SHALL write `.agentweave/shared/context_usage/<agent>.json` containing `{"agent": "<name>", "percent": <N/context_limit*100>, "model": "<model>", "input_tokens": N, "context_limit": <limit>, "warning": <bool>, "critical": <bool>}`

#### Scenario: Unknown model defaults to 200K context limit
- **WHEN** the agent's model name is not in the known context-limit map
- **THEN** the watchdog SHALL use 200000 as the context limit and include `"model": "<name>"` in the written file

#### Scenario: Warning flag set at 70% threshold
- **WHEN** computed percent is >= 70
- **THEN** `warning` SHALL be `true` in the written file

#### Scenario: Critical flag set at 90% threshold
- **WHEN** computed percent is >= 90
- **THEN** `critical` SHALL be `true` in the written file

#### Scenario: Context usage cleared on new session
- **WHEN** the watchdog detects a `[NewSession]` marker or a new session ID for an agent
- **THEN** the watchdog SHALL write `{"agent": "<name>", "percent": 0, "warning": false, "critical": false}` to the context_usage file, resetting the display

#### Scenario: Coverage for claude_proxy and native runners
- **WHEN** an agent uses `claude_proxy` or `native` runner (both use `--output-format stream-json`)
- **THEN** token extraction SHALL work identically to the `claude` runner

### Requirement: Context limit map in constants
The codebase SHALL maintain a `CLAUDE_CONTEXT_LIMITS` dict in `constants.py` mapping known model name substrings to integer token limits.

#### Scenario: Known model resolved correctly
- **WHEN** `_get_context_limit("claude-sonnet-4-6")` is called
- **THEN** it SHALL return 200000

#### Scenario: Fallback for unknown model
- **WHEN** `_get_context_limit("some-future-model-xyz")` is called
- **THEN** it SHALL return 200000 (default)
