## Why

The autonomous dev loop on the AgentWeave repo (planned under a separate change) requires three runtime guarantees before it can work reliably:

1. The Hub can read a trustworthy context-window percentage for every active agent session.
2. The watchdog can force an agent to checkpoint and start a fresh session when context crosses a configured threshold, including a safe force-kill path for agents that ignore the instruction.
3. The watchdog will not silently lose trigger messages when a spawn fails, when an agent subprocess exits quickly with an error, or when the watchdog itself has been down for a while.

In all three cases the current behaviour is unknown or known-broken. The user has observed that the Hub context display never shows the right number and that assumptions about watchdog behaviour have been wrong in the past.

This change ships investigation artefacts only — flow diagrams, behaviour matrices, evidence — and explicitly does NOT ship fixes. Fixes land in follow-up changes once the findings are reviewed and approved.

## What Changes

- Add an investigation findings directory under the change folder containing one document per blocker.
- Each findings document SHALL trace the current behaviour end-to-end with explicit evidence (log lines, screenshots, direct DB queries, observed CLI behaviour).
- Add three capability specs that define the required shape of each findings document.

## Capabilities

### New Capabilities

- `context-tracking-investigation`: Flow diagram and per-arrow evidence for the context-usage pipeline from CLI stream events through watchdog writer, Hub REST endpoint, Hub storage, and Hub UI rendering.
- `auto-reset-investigation`: Per-runner behaviour documentation for what happens when a watchdog-issued reset instruction is delivered to a busy agent at high context, including the grace window recommendation.
- `busy-agent-investigation`: Behaviour matrix documenting what currently happens when a watchdog spawns a second trigger for an agent while the first is still running, across multiple timing scenarios.

### Modified Capabilities

None.

## Impact

- No production code changes.
- Documentation: three new findings documents under `openspec/changes/investigate-blockers/findings/`.
- Tests: investigation-time manual experiments and ad-hoc reproducers captured in the findings.
- Time investment: depends on how long each manual investigation takes; expected order is context tracking first (most user-visible bug), then auto-reset, then busy-agent.