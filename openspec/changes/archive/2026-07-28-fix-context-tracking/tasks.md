## 1. Fix the broken arrows

- [ ] 1.1 For each `BROKEN` arrow in `openspec/changes/investigate-blockers/findings/blocker-0.md`,
  implement the smallest fix that makes the arrow work end-to-end.
- [ ] 1.2 If the Hub REST endpoint for context-usage ingestion does not exist
  (per the investigation), add it. Verify the watchdog's
  `_post_context_usage_to_hub` posts to the correct URL and method.
- [ ] 1.3 If the Hub endpoint exists but is misimplemented, fix it.
  Reference the finding's evidence when implementing.
- [ ] 1.4 If the Hub storage lacks a context-usage column or table, add it
  via Alembic migration.
- [ ] 1.5 If the Hub UI does not render the percentage, fix the relevant
  component under `hub/ui/src/components/agents/`.

## 2. Fill in untested arrows

- [ ] 2.1 For each `UNTESTED` arrow, design a test or observation that
  classifies it as `WORKING` or `BROKEN`. Update the findings document
  with the result.

## 3. Per-runner parsers

- [ ] 3.1 Verify `_write_context_usage` (Claude path) parses correctly.
- [ ] 3.2 Verify `_write_codex_context_usage` parses correctly.
- [ ] 3.3 Verify Kimi wire-mode `StatusUpdate` events are captured into
  `context_usage/<agent>.json`.
- [ ] 3.4 If OpenCode does not emit context-usage events (per the
  investigation), add a polling or heuristic fallback in the watchdog
  that writes a context-usage file for OpenCode agents.

## 4. Tests

- [ ] 4.1 Add an end-to-end test that runs a long session per runner and
  asserts the Hub stores and renders a context value matching the CLI's
  report within a documented tolerance.
- [ ] 4.2 Add unit tests for each per-runner parser.
- [ ] 4.3 Add a test that simulates a watchdog restart and verifies
  context-usage resumes correctly without stale state from the previous
  run.
- [ ] 4.4 All tests SHALL fail if any runner in the pipeline silently
  swallows context data.

## 5. Documentation

- [ ] 5.1 Update `AGENTS.md` or the relevant guide to describe the
  context-tracking pipeline and its known limitations.
- [ ] 5.2 Note any per-runner tolerance or fallback so users understand
  what "context 78%" actually means.