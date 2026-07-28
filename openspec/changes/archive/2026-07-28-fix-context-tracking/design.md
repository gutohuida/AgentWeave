## Context

The Blocker 0 findings from `investigate-blockers` identify concrete failure points in the context-usage pipeline from CLI stream events through the Hub UI. This change implements the smallest fix that makes the pipeline work end-to-end for every runner the dev loop uses.

The exact implementation depends on the findings, so this design intentionally leaves the technical approach open. The implementing agent fills in the implementation details once the user approves the findings.

## Goals / Non-Goals

**Goals:**

- Repair every `BROKEN` arrow identified in `openspec/changes/investigate-blockers/findings/blocker-0.md`.
- Fill in or remove every `UNTESTED` arrow by testing it as part of the fix.
- Ensure the Hub UI renders a trustworthy context percentage for every active agent session.

**Non-Goals:**

- Touch unrelated context-handling code.
- Change the watchdog's retry behaviour (that is the durable-trigger-retry change).
- Change the auto-reset behaviour (that is the add-auto-reset-mode change).

## Decisions

### Decision: Repair is per-arrow, not a rewrite

Each broken arrow is fixed at its source rather than replaced with a parallel pipeline. The user has stated that previous attempts at wholesale rewrites made things worse. Per-arrow fixes keep blast radius small.

### Decision: OpenCode context fallback is acceptable when events are missing

If the Blocker 0 findings show that OpenCode does not emit context-usage events in `--format json` output, the watchdog SHALL add a polling or heuristic fallback that writes a context-usage file for OpenCode agents. The implementation agent picks between polling and heuristic based on what is least invasive.

### Decision: End-to-end test is required

The fix SHALL include a test that runs a long session per runner and asserts the Hub stores and renders a context value matching the CLI's report within a documented tolerance. The test SHALL fail if any runner silently swallows context data.

## Open Questions

- The specific failure points will be revealed by the findings. The implementing agent decides the implementation after reading the findings.
- Whether the existing `_post_context_usage_to_hub` helper is replaced or repaired depends on how broken the helper actually is.