# A file path is not redacted as a credential

## Why

**F278 (C).** `redact_secrets` (`hub/hub/runner_events.py:63`) replaces every match of
`_SECRET_VALUE_RE` (`runner_events.py:57-60`) with `<redacted>`. Its third alternative is a bounded
high-entropy catch-all, `[A-Za-z0-9+/=]{32,}`. `/` has to be in that class, because base64 uses it.
A POSIX path is mostly letters and slashes, so any 32-character run of a path with no `.`, `_` or `-`
in it matches, and it is replaced whole.

Re-measured at `ce086b6` (2026-09-24) against the module itself:

| input | stored as |
|---|---|
| `/Users/operator/code/agentweave/hub/main.py` | `<redacted>.py` |
| `src/services/user/repository/handler.py` | `<redacted>.py` |
| `/workspace/proj/.agentweave/worktrees/beta/src/app.py` | `/workspace/proj/.<redacted>.py` |

The path that is lost most reliably is the one under `.agentweave/worktrees/`, which is the agent's
own checkout. That is often the destination an operator reading a transcript wants to find. Every
Docker deployment is Linux, so its paths use `/`. On Windows, `\` is outside the class and paths
survive, which is why this has gone unnoticed on the development machine. `redact_secrets` is also
applied to loop error summaries (`scheduler.py:94`), so a POSIX path in an exception is eaten there
too.

The main spec already sets the bound this breaks. *Structured payload safety*
(`openspec/specs/agent-stream-events/spec.md:101`) says redaction "SHALL be bounded so that it does
not consume identifiers that are not secrets". It names only tool names and document slugs, because
those were the families found then (F31). F118 (task ids) was the second family, and F278 is the
third. All three come from the same catch-all.

## What Changes

- A match of the high-entropy catch-all that is **shaped like a path** is kept. It must be split by
  `/` into **at least three** non-empty segments, and each segment must be an ordinary word: either
  lowercase letters and digits, or capitalised or camel-case letters (`Users`, `AgentWeave`). Every
  other match is redacted exactly as today.
- **A segment of 32 or more characters is still judged by itself.** A long hex or base64 value used
  as a URL segment (`…/tokens/<40 hex>`) is redacted even though the rest of the path survives.
- The two recognised prefixes (`aw_live_`, `sk-`) and the field-name rule are unchanged.
- The CLI's own `agentweave.diagnostics.SECRET_VALUE_RE` (`src/agentweave/diagnostics.py:43`) is
  **not** changed. Its class is `[A-Za-z0-9_=-]`, with no `/`, so it never had F278.

## Capabilities

### Modified Capabilities

- `agent-stream-events`: *Structured payload safety* adds file paths to the identifiers that
  redaction does not consume, with scenarios for a deep POSIX path, a path with a credential-length
  segment, and a base64 credential that contains `/`.

## Impact

- `hub/hub/runner_events.py`: `_SECRET_VALUE_RE`'s substitution gets a replacement function. The
  pattern itself does not change.
- `hub/tests/test_operator_is_told_the_truth.py`: new cases.
- `hub/tests/test_write_paths_on_run_events.py:139-148`: **this test pins the defect.** It asserts
  that `/workspace/project/src/services/handler.py` is *absent* from `payload["input"]` and that
  `<redacted>` is present. It must be rewritten to keep testing what it is for, which is read-before-
  redact ordering (tasks 1.5).
- No migration, no UI, no MCP change. Rows that are already stored stay redacted. This is not a
  backfill, and a backfill is impossible because the original text is gone.
