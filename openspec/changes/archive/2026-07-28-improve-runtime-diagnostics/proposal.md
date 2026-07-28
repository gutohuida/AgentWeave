## Why

AgentWeave currently has several places where failures are detected late, logged only to stderr, or treated as non-fatal without durable visibility. This makes common operational problems, such as missing proxy API keys, stale watchdogs, unreachable Hub transport, or failed job execution, difficult for users to diagnose.

## What Changes

- Add a runtime readiness and diagnostics capability that checks whether the current project can actually run its configured agents.
- Add a `agentweave doctor` command that reports session, configuration, transport, Hub auth, watchdog, runner CLI, proxy environment, context-file, MCP, and job readiness.
- Add preflight readiness checks to `agentweave activate`, `agentweave start`, `agentweave agent configure`, and watchdog-triggered execution.
- Emit durable structured diagnostic events for degraded, skipped, failed, and unavailable runtime states.
- Improve proxy runner behavior by warning when required provider API keys are missing during configuration and activation, and by skipping automatic watchdog launches that cannot succeed.
- Improve Hub visibility for queued agent triggers when the host watchdog is stale, absent, or unable to run the target agent.
- Improve Hub Logs usability so filters reflect actual configured/custom agents and common failure categories.
- Improve asynchronous job failure visibility with durable run history and clear error summaries.
- No breaking changes are intended.

## Capabilities

### New Capabilities

- `runtime-diagnostics`: Runtime readiness checks, structured diagnostics, and user-visible health reporting for AgentWeave CLI, watchdog, Hub, runners, transports, logs, and jobs.

### Modified Capabilities

- None.

## Impact

- CLI: `src/agentweave/cli.py`, `src/agentweave/runner.py`, `src/agentweave/watchdog.py`, `src/agentweave/transport/http.py`, `src/agentweave/transport/config.py`, `src/agentweave/logging_handlers.py`.
- Hub backend: `hub/hub/api/v1/agent_trigger.py`, `hub/hub/api/v1/agents.py`, `hub/hub/api/v1/logs.py`, `hub/hub/api/v1/jobs.py`, `hub/hub/scheduler.py`, and related schemas/models if new diagnostic fields are needed.
- Hub UI: Logs, overview/status, agents, jobs, and setup/readiness surfaces.
- Tests: CLI unit tests, watchdog tests, HTTP transport tests, Hub API tests, and focused UI behavior checks where practical.
- Dependencies: no new CLI runtime dependencies should be added.
