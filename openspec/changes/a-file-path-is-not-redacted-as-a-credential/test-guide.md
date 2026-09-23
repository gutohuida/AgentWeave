# Test guide — a file path is not redacted as a credential

## Agent-verifiable

1. **Paths survive.** Task 1.1 fails before the fix and passes after it, for all four paths.
2. **Credentials still go.** Tasks 1.2 and 1.3, and the existing credential tests (1.4), pass after
   the fix. 1.2 fails before the fix only because today's rule drops the whole URL tail.
3. **The ordering test still tests ordering.** After 1.5, reverse the read in `tool_use_event`
   (move `written_paths` below `redact_secrets`) and confirm the rewritten test fails. Then restore
   it.
4. **Residual rate.** Re-run D2's random-base64 measurement after the fix. It must show at most one
   survivor per million.

## Human-only

1. On a Docker or Linux Hub, open a finished run's transcript where the agent wrote a file under
   `.agentweave/worktrees/<agent>/…`. The tool input shows the full path, not `<redacted>`.
   This machine is Windows, so its paths never showed the defect. Only a Linux host shows the
   before/after difference.
