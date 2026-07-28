## 1. Diagnostics Foundation

- [x] 1.1 Add a CLI diagnostics module with a structured readiness check result type.
- [x] 1.2 Implement checks for session presence, session parseability, and agentweave.yml parseability.
- [x] 1.3 Implement checks for configured transport type, HTTP Hub reachability, Hub auth, and project id availability.
- [x] 1.4 Implement checks for watchdog PID/heartbeat freshness and stale heartbeat detection.
- [x] 1.5 Implement per-agent checks for runner type, runner CLI availability, context file presence, proxy API key variable presence, yolo/pilot/manual status, and configured model.
- [x] 1.6 Add secret-redaction helpers used by diagnostics, log events, and subprocess summaries.

## 2. CLI Integration

- [x] 2.1 Add `agentweave doctor` with grouped human-readable output and process exit behavior for failed checks.
- [x] 2.2 Add `agentweave doctor --json` for machine-readable diagnostics and tests.
- [x] 2.3 Wire readiness checks into `agentweave agent configure` so proxy agents warn when the required API key variable is missing.
- [x] 2.4 Wire readiness summary output into `agentweave activate` after configuration, agent sync, MCP setup, watchdog startup, and context sync.
- [x] 2.5 Wire startup readiness checks into `agentweave start` so missing CLIs and proxy env vars are visible before background execution.
- [x] 2.6 Add tests for CLI diagnostics output, JSON output, missing proxy key warnings, and secret redaction.

## 3. Watchdog Preflight and Execution Diagnostics

- [x] 3.1 Add watchdog preflight checks before spawning agent subprocesses.
- [x] 3.2 Skip proxy agent launches when the required provider API key variable is missing.
- [x] 3.3 Skip agent launches when the resolved runner CLI is unavailable.
- [x] 3.4 Post clear agent output lines to Hub for launch skips when HTTP transport is active.
- [x] 3.5 Emit structured diagnostic events for launch skips, launch failures, non-zero subprocess exits, and stderr summaries.
- [x] 3.6 Preserve retryable message/task state when watchdog skips a launch due to deterministic readiness failures.
- [x] 3.7 Add watchdog tests for missing proxy key, missing CLI, Hub output posting, structured log emission, and retryable state preservation.

## 4. Structured Logging and Transport Classification

- [x] 4.1 Define stable diagnostic event names and severity conventions for setup, transport, watchdog, runner, proxy credentials, jobs, and agent stderr.
- [x] 4.2 Update non-fatal setup and sync paths to emit structured diagnostic events instead of only printing warnings or suppressing exceptions.
- [x] 4.3 Classify HTTP transport failures into unreachable, auth failed, project missing, timeout, schema/response error, and generic transport error.
- [x] 4.4 Ensure local JSONL logs and Hub logs receive equivalent diagnostic event payloads where transport is available.
- [x] 4.5 Add tests for classified transport failures and structured diagnostic log payloads.

## 5. Hub Backend Visibility

- [x] 5.1 Update Hub agent trigger responses to distinguish queued with healthy watchdog, queued with stale watchdog, queued with no watchdog heartbeat, and queued for manual/pilot handling.
- [x] 5.2 Persist structured trigger-confidence events for Hub direct triggers.
- [x] 5.3 Add API support for logs or agents to expose actual agent names usable by the Logs UI filter.
- [x] 5.4 Add job failure diagnostics so scheduler and manual job runs persist failed state and secret-safe error summaries.
- [x] 5.5 Add Hub tests for trigger confidence, stale watchdog responses, dynamic log-agent metadata, and job failure persistence.

## 6. Hub UI Diagnostics

- [x] 6.1 Update Logs view agent filters to use configured agents, self-registered agents, or log-derived agents instead of a hardcoded list.
- [x] 6.2 Add diagnostic category filters or quick filters for transport, watchdog, runner, proxy credentials, setup, jobs, and agent stderr.
- [x] 6.3 Surface stale watchdog and queued-but-not-running states in agent trigger/chat flows.
- [x] 6.4 Surface recent job failure summaries distinctly from disabled, pending, or idle jobs.
- [x] 6.5 Verify that log and diagnostic UI surfaces do not display secret values.

## 7. Verification

- [x] 7.1 Run targeted CLI unit tests for diagnostics, proxy key checks, transport classification, and watchdog preflight.
- [x] 7.2 Run targeted Hub API tests for trigger confidence, logs, agents, and jobs.
- [x] 7.3 Run formatting and linting for changed Python and TypeScript files.
- [x] 7.4 Manually verify a missing proxy key flow from configure, activate, doctor, and watchdog-triggered Hub execution.
- [x] 7.5 Manually verify Hub Logs filters include custom/proxy agents and diagnostic categories.
