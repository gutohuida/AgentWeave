# Handoff: Change 4 section 4 complete; Hub persistence section 5 next

**Date:** 2026-07-29T12:04:01+01:00 · **Branch:** `master` · **HEAD:** `aa8a1bc`
**Agent:** Codex (GPT-5)
**Previous handoff:** `.claude/handoffs/2026-07-29-1134-change4-section4-4to8-uncommitted.md`
**Status:** chunk complete

## Goal

Implement OpenSpec Change 4, `add-agent-stream-kinds`, so all supported runners produce one
canonical structured stream-event contract and one canonical context-usage contract, delivered
safely through the CLI, Hub, and UI with rolling-upgrade compatibility. Sections 1-4 are now
complete and committed; section 5 ("Hub stream persistence and APIs") is the next task boundary.

## Current state

Section 4 is fully complete: tasks 4.1-4.13 are checked in
`openspec/changes/add-agent-stream-kinds/tasks.md`. This session resumed the unverified 4.4-4.8
working tree from the previous handoff, verified/fixed it, added end-to-end collector wiring tests,
and committed it as `3f1d594`. It then implemented 4.9-4.13 and committed that as `aa8a1bc`.

The CLI now:

- drives Codex rollout, Copilot OTel, and Kimi Wire collectors through invocation setup/bind/
  observe/final-poll/close;
- uses one atomic canonical context snapshot writer and rejects mismatched-session collector
  samples;
- resets new sessions to `unavailable` before measurement;
- normalizes legacy local context aliases (`tokens_used`, `tokens_limit`, `input_tokens`,
  `context_limit`, and ratio-form `context_usage`) at the reader boundary;
- converts contradictory legacy percentages to token-only state and ambiguous zero-without-limit
  values to unavailable;
- posts canonical context through the transport interface;
- posts structured `kind`, `payload`, `run_id`, and `sequence` alongside readable content;
- recursively redacts stream content/payload before transport;
- falls back to the old transport signature on `TypeError` and retries text-only output when an
  older Hub rejects additive structured fields with HTTP 400/422;
- uses the same run ID and monotonically increasing sequence counter for started, normalized
  output, completion/error, and retry lifecycle events.

Section 5 is not started. The current Hub `AgentOutput` model has only `id`, `project_id`, `agent`,
`session_id`, `content`, and `timestamp`. The latest migration is `0010`; task 5.1 therefore needs
new migration `0011`. `AgentOutputCreate` and `AgentOutputResponse` currently expose only content,
session, and timestamp. The default output query currently orders ascending and then limits,
which selects the oldest N records rather than newest N (task 5.6).

## Files touched

- `openspec/changes/add-agent-stream-kinds/tasks.md` — tasks 4.4-4.13 marked complete; finished and
  committed across `3f1d594` and `aa8a1bc`.
- `src/agentweave/watchdog.py` — canonical writer/collector invocation wiring, context reader
  normalization, structured event delivery, lifecycle run/sequence continuity, stale-session
  rejection, and exception return-code initialization; finished and committed.
- `src/agentweave/stream_events.py` — added legacy/canonical context normalization and redacted
  transport serialization; finished and committed.
- `src/agentweave/transport/base.py` — added backward-compatible optional output/context posting
  interfaces; finished and committed.
- `src/agentweave/transport/http.py` — added structured output request fields and 400/422
  text-only degradation; finished and committed.
- `tests/test_watchdog.py` — added full invocation tests for collector preference/fallback,
  new-session reset ordering, Copilot environment injection, legacy reading, structured
  run/sequence delivery, final polling, stale-session rejection, process failure, simultaneous
  output/usage, and old transport signatures; finished and committed.
- `tests/test_stream_events.py` — added legacy normalization, contradiction, canonical round-trip,
  ambiguous-zero, and transport-redaction tests; finished and committed.
- `tests/test_http_transport.py` — added structured, text-only, older-Hub degradation, and canonical
  context request tests; finished and committed.
- `tests/test_transport_local.py` — added safe no-op tests for the optional delivery interface;
  finished and committed.
- `.claude/handoffs/LATEST.md` — pre-existing tracked handoff pointer; dirty and being updated by
  this handoff, intentionally not part of the implementation commits.
- `.claude/handoffs/2026-07-29-1204-change4-section4-complete-section5-next.md` — this new handoff.
- `.claude/handoffs/2026-07-28-2203-kimi-fix-and-commit-split.md` — pre-existing untracked handoff,
  unchanged.
- `.claude/handoffs/2026-07-28-2320-add-spec-manifest-implementation.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-0040-change1-archived-stream-kinds-next.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-0155-change4-stream-kinds-adapters-in-progress.md` — pre-existing
  untracked handoff, unchanged.
- `.claude/handoffs/2026-07-29-0947-change4-stream-kinds-section2-done.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-1015-change4-section3-3-of-4-collectors-done.md` — pre-existing
  untracked handoff, unchanged.
- `.claude/handoffs/2026-07-29-1115-change4-section3-done-section4-next.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-1134-change4-section4-4to8-uncommitted.md` — previous handoff,
  pre-existing and unchanged.

## Key decisions

- Copilot keeps `model`/`limit_tokens` absent when unresolved. The user explicitly confirmed this
  after resume. No trustworthy Copilot model-to-limit resolver exists; fabricating a table was
  rejected.
- Raw provider dictionaries never cross into the canonical writer. Provider adapters/collectors
  construct `ContextUsageSample`, and one atomic writer serializes it.
- Codex rollout usage wins over cumulative stdout usage; stdout remains an estimated fallback and
  receives the existing model-table/default limit only when rollout resolution fails.
- Threshold policy remains a reader concern and only measured samples auto-warn. Estimated samples
  are displayable but do not trigger warning/critical policy.
- Legacy alias precedence is canonical `context_tokens`, then `tokens_used`, then `input_tokens`;
  this preserves old Codex files where `tokens_used` is total while `input_tokens` is only a
  breakdown operand. Contradictory ratio/denominator values retain trustworthy tokens but discard
  the percentage; zero without a limit becomes unavailable.
- New structured producers always keep readable `content`. Older Python transport objects fall
  back to the three-argument method, and older Hubs that return 400/422 are retried with only
  content/session. Rejecting all structure permanently or adding a new endpoint was rejected
  because the design requires additive rolling compatibility.
- Lifecycle `started` and `_run_cmd` now share the same `run_id` and sequence counter. A retry gets
  a fresh run ID and a fresh counter, with `retrying` as sequence 1.
- New commits only; neither section-4 commit amended prior history.

## Constraints and user directives (verbatim)

- `"$resume"`
- `"yes"` — in response to: “should Copilot context samples remain without model/limit when
  unresolved?”
- `"go ahead"` — authorization to continue with section 4.9-4.13.
- `"$handoff"`
- Carried from the prior handoff and still binding:
  - `"Kimi's session-status service (task 3.10) is intentionally not implemented — do not silently
    implement it."`
  - `"New commits, not amends."`
  - `"Zero new runtime dependencies (stdlib only)."`
  - `"Never commit .agentweave/*; use template loading not hardcoded template strings; lock task
    mutations; preserve unrelated dirty work; target Kimi v0.29.x only."`
  - `"Live CLI probes must run in isolated scratch directories outside the repo, cleaned up
    after."`
  - Pushing has not been requested.

## Dead ends

- The first resumed `pytest tests/ -q` call used too short a command timeout and returned only a
  tooling timeout. Re-running with a 120-second timeout completed normally.
- `ruff`, `black`, and `mypy` were not on the ambient Hermes Python PATH. The correct executables
  are under `.venv\Scripts\`; use those directly.
- The first new context-wiring tests looked under `.agentweave/context_usage`, but the real
  constant is `.agentweave/shared/context_usage`. Two tests failed with `FileNotFoundError` until
  corrected.
- A recording test constructed a measured sample without `basis`, causing the intended
  `ContextUsageSample` validation error. It was fixed with `basis="provider_context"`.
- That test-induced exception exposed a real latent `returncode` unbound path after subprocess
  errors; section 4.9-4.13 initializes `returncode = 1` before the try block.
- A first patch against `http.py` missed because the expected docstring contained a mojibake dash;
  patching against the actual Unicode source succeeded. Do not infer file encoding from rendered
  PowerShell mojibake.

## Verification

Ran after the final section 4.9-4.13 formatting:

- `.\.venv\Scripts\pytest.exe tests/ -q` — **982 passed, 4 skipped** (986 collected).
- `.\.venv\Scripts\ruff.exe check src/ tests/` — **All checks passed**.
- `.\.venv\Scripts\black.exe --check src/ tests/` — **67 files would be left unchanged**.
- `.\.venv\Scripts\mypy.exe src/` — **Success: no issues found in 28 source files**. Mypy also
  prints its environment warning that configured Python 3.8 is no longer supported by this mypy
  version; this is not a project type error.
- `git diff --cached --check` before each commit — clean.
- `openspec status --change add-agent-stream-kinds --json` after 4.4-4.8 — planning artifacts
  reported complete.

Also ran focused suites throughout, including the final focused matrix:
`.\.venv\Scripts\pytest.exe tests/test_stream_events.py tests/test_http_transport.py
tests/test_transport_local.py tests/test_watchdog.py -q` — **486 passed** at that point.

Not tested:

- No Hub backend tests (`hub/tests/`) were run; section 5 has not started.
- No Hub UI build or browser/manual flow was run.
- No live runner CLI probes were run in this session.
- Nothing was pushed to `origin`.

## Git state

- Branch: `master`
- HEAD: `aa8a1bc` (`Deliver canonical context and structured output`)
- Earlier section-4 commit: `3f1d594` (`Unify invocation context usage delivery`)
- Working implementation tree is clean. Dirty state consists only of handoff metadata:
  `.claude/handoffs/LATEST.md` plus the nine handoff markdown files listed under Files touched
  (eight pre-existing and this new file).
- `master` is **15 commits ahead of `origin/master`**; none were pushed.
- Upstream remote is `origin`.

## Next steps

1. Implement task 5.1 by creating
   `hub/hub/migrations/versions/0011_add_agent_output_stream_fields.py`, revision `0011` with
   `down_revision = "0010"`. Add nullable `kind` (bounded string), `payload` (JSON), `run_id`
   (bounded string), and `sequence` (integer) columns to `agent_outputs`, plus the run-ordering
   index required by design.md decision 8. Mirror the existing migration style and include a
   downgrade that removes the index and columns.
2. Update `hub/hub/db/models.py` `AgentOutput` and `hub/hub/schemas/agents.py`
   `AgentOutputCreate`/`AgentOutputResponse` for tasks 5.2-5.3. Re-read the stream-event spec’s
   allowed kinds and 64 KiB payload bound before choosing validators.
3. Update `hub/hub/api/v1/agents.py` output create/list/SSE flow and
   `hub/hub/api/v1/agent_chat.py` projection for tasks 5.4-5.6. Fix newest-window ordering by
   selecting newest N deterministically and returning that window chronologically.
4. Add migration, REST round-trip, legacy-row, chat, SSE, rejection, and newest-window tests in
   `hub/tests/` for task 5.7. Run the relevant Hub tests first, then the full Hub suite.
5. Run CLI verification too if shared files are touched, mark 5.1-5.7 complete only after green,
   and make a new commit (do not amend).

## Open questions for the user

None. Copilot’s unresolved model/limit behavior was explicitly confirmed. Pushing remains
unauthorized and is not a blocker.

## Read on resume

- `openspec/changes/add-agent-stream-kinds/tasks.md` — section 5 task definitions and progress.
- `openspec/changes/add-agent-stream-kinds/design.md` — decisions 8 and 9 for persistence,
  compatibility, bounds, and redaction.
- `hub/hub/db/models.py` — current `AgentOutput` schema and index definitions.
- `hub/hub/schemas/agents.py` — current output request/response Pydantic models.
- `hub/hub/api/v1/agents.py` — output creation, SSE broadcast, and default query ordering.
- `hub/hub/api/v1/agent_chat.py` — chat-history projection that must retain structured fields.
