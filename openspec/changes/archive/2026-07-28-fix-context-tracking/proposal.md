## Why

The investigation change (`investigate-blockers`) has identified concrete failure points in the context-usage pipeline from CLI stream events through the Hub UI. This change implements the smallest fix that makes the pipeline work end-to-end for every runner the dev loop uses.

The fix targets the failure points identified by the investigation and does not touch unrelated context-handling code. The investigation findings document is the source of truth for which arrows in the pipeline need repair; this change implements the repair.

## What Changes

- Repair every `BROKEN` arrow identified in the Blocker 0 findings.
- Fill in or remove every `UNTESTED` arrow by testing it as part of the fix.
- Add a Hub REST endpoint for context-usage ingestion if one does not exist, and ensure it is wired up to the watchdog's `_post_context_usage_to_hub` path.
- Ensure the Hub UI renders the context percentage for every active agent session in a way that monotonically increases during a single session and resets on a new session.
- Add an end-to-end test that exercises CLI → file → Hub POST → storage → UI for every supported runner.

## Capabilities

### New Capabilities

- `context-tracking-pipeline`: A reliable, end-to-end context-usage pipeline from CLI stream events through watchdog writer, Hub REST endpoint, Hub storage, and Hub UI rendering.

### Modified Capabilities

None.

## Impact

- CLI/watchdog: changes to `_post_context_usage_to_hub`, `_check_context_usage`, and the per-runner context writers (`_write_context_usage`, `_write_codex_context_usage`, and any new OpenCode writer).
- Hub backend: possible new REST endpoint, new schema or column for storing context usage, fixes to the existing endpoint if it is misimplemented.
- Hub UI: fixes to the context-percentage rendering, possibly a new component or column.
- Tests: new end-to-end test covering all three runners; per-runner unit tests for the parsers.
- Depends on: `investigate-blockers` being shipped (i.e., the user has approved the findings).