## ADDED Requirements

### Requirement: Context-tracking flow is documented with per-arrow evidence

The investigation findings for Blocker 0 SHALL document the context-usage pipeline from each supported CLI's output stream through the watchdog's local writer, through the Hub's REST endpoint, into Hub storage, and finally into the Hub UI rendering. Each arrow in the pipeline SHALL be marked as `WORKING`, `BROKEN`, or `UNTESTED`, and every non-`WORKING` arrow SHALL have evidence attached.

#### Scenario: Flow diagram exists with arrows classified

- **WHEN** the Blocker 0 findings document is reviewed
- **THEN** it SHALL contain a flow diagram with each arrow explicitly marked `WORKING`, `BROKEN`, or `UNTESTED`
- **AND** every `BROKEN` arrow SHALL be accompanied by evidence (log line, DB query, screenshot, or observed CLI behaviour)
- **AND** every `UNTESTED` arrow SHALL be flagged as a risk that must be tested before any fix is designed

#### Scenario: All three runners are exercised

- **WHEN** the Blocker 0 findings document is reviewed
- **THEN** it SHALL record observed behaviour for at least one long-running session per runner used in the dev loop (opencode, kimi, codex)
- **AND** if a runner cannot be exercised (for example, the CLI is unavailable in the investigation environment), the findings SHALL state that explicitly rather than silently omitting it

#### Scenario: OpenCode context-usage emission is verified

- **WHEN** an agent investigates whether OpenCode emits context-usage events in `--format json` output
- **THEN** the findings SHALL state explicitly whether such events exist and what their shape is, based on a real CLI invocation
- **AND** if the events do not exist, the findings SHALL recommend either a polling alternative or a context-pressure heuristic rather than assuming the events will appear