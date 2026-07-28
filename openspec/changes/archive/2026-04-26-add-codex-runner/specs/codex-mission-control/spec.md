## ADDED Requirements

### Requirement: Context bar populated from Codex JSONL token usage
The watchdog SHALL parse `turn.completed` usage events from Codex stdout and write a context_usage file to `.agentweave/shared/context_usage/<agent>.json` after each completed turn.

Token counts SHALL be derived from the `turn.completed` event:
```json
{"type":"turn.completed","usage":{"input_tokens":N,"cached_input_tokens":N,"output_tokens":N}}
```

The context limit SHALL be looked up from `CODEX_MODEL_CONTEXT_LIMITS` in `constants.py`. If the model is not in the map, the limit SHALL default to `128000`.

#### Scenario: Usage event parsed and written
- **WHEN** `turn.completed` is emitted with token counts
- **THEN** the watchdog writes `{percent, tokens_used, tokens_limit, model, warning, critical}` to the context_usage file

#### Scenario: Unknown model fallback
- **WHEN** the agent's model is not in `CODEX_MODEL_CONTEXT_LIMITS`
- **THEN** `tokens_limit` is set to `128000`

#### Scenario: Warning threshold
- **WHEN** `percent >= 70`
- **THEN** `warning: true` is set in the context_usage file

#### Scenario: Critical threshold
- **WHEN** `percent >= 90`
- **THEN** `critical: true` is set in the context_usage file

---

### Requirement: CODEX_MODEL_CONTEXT_LIMITS constant defined
`constants.py` SHALL define `CODEX_MODEL_CONTEXT_LIMITS` mapping known Codex model names to their effective context window sizes in tokens.

Initial entries SHALL include at minimum:
- `"gpt-5.5"`: `272000`
- `"gpt-4o"`: `128000`

#### Scenario: Known model limit lookup
- **WHEN** the agent uses `model: gpt-5.5`
- **THEN** `CODEX_MODEL_CONTEXT_LIMITS["gpt-5.5"]` returns `272000`

---

### Requirement: Mission Control Compact button replaced for Codex agents
The `MissionCard` component in `MissionControlPage.tsx` SHALL render an "Auto-managed" badge instead of the Compact button when `agent.runner === "codex"`.

The badge SHALL display the text "Auto-managed" with a tooltip: "Codex handles compaction automatically via OpenAI's servers."

#### Scenario: Codex agent shows auto-managed badge
- **WHEN** a MissionCard renders for an agent with `runner === "codex"`
- **THEN** the Compact button is replaced by a static "Auto-managed" badge

#### Scenario: Non-Codex agent shows Compact button
- **WHEN** a MissionCard renders for an agent with any other runner
- **THEN** the Compact button renders as normal

---

### Requirement: Mission Control Reset Context clears thread_id directly for Codex
When "Reset Context" is confirmed for a Codex agent, the Hub backend SHALL persist a `new_session_request` event and the watchdog SHALL handle it by deleting `.agentweave/agents/<agent>-session.json` directly — without sending an inbox message to the agent.

#### Scenario: Reset Context for Codex agent
- **WHEN** user confirms Reset Context for a Codex agent in Mission Control
- **THEN** the Hub posts `new_session_request` and the watchdog deletes the session file on next poll

#### Scenario: Next ping after reset starts fresh
- **WHEN** the session file has been deleted
- **THEN** the next watchdog ping runs `codex exec` without `--resume` (new thread)

#### Scenario: Reset Context for non-Codex agent unchanged
- **WHEN** user confirms Reset Context for a Claude or native agent
- **THEN** the existing inbox message path is used unchanged

---

### Requirement: AgentCard displays Codex runner badge in OpenAI green
`RUNNER_CONFIG` in `AgentCard.tsx` SHALL include a `codex` entry with a distinctive colour.

#### Scenario: Codex runner badge rendered
- **WHEN** an agent has `runner === "codex"` and a `display_model`
- **THEN** the runner badge renders with the Codex color (not the manual grey fallback)
