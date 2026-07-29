# Handoff: Change 4 (add-agent-stream-kinds) — section 4 tasks 4.4-4.8 implemented but UNVERIFIED and UNCOMMITTED

**Date:** 2026-07-29T11:34:28+01:00 · **Branch:** `master` · **HEAD:** `4c34fca`
**Agent:** Claude (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-07-29-1115-change4-section3-done-section4-next.md`
**Status:** blocked — full verification (test suite / ruff / black / mypy) has NOT been run
to completion since these edits; do not assume they pass

## Goal

Implement Change 4 (`add-agent-stream-kinds`, folded with former Change 6), a 94-task plan at
`openspec/changes/add-agent-stream-kinds/tasks.md`. Sections 1-3 are done (committed).
Section 4 ("Invocation lifecycle and canonical context delivery", 13 tasks) is being done in
three user-approved sub-chunks: **4.1-4.3 (committed as `4c34fca`)**, **4.4-4.8 (this
session's work, written but not committed/verified)**, then 4.9-4.13 (not started).

## Current state

**4.1-4.3 are committed and verified** (`4c34fca`, 953 tests passing at that point, ruff/
black/mypy clean). Not at risk — do not re-touch without reason.

**4.4-4.8 are fully written in the working tree but NOT verified and NOT committed.** The
last thing that happened before this handoff: I ran `pytest tests/test_watchdog.py -q` in
isolation (**383 passed**, confirming the file that imports the renamed/removed functions is
internally consistent), then attempted `pytest tests/ -q` (the full suite) and **the user
interrupted/rejected that tool call before it produced output**. So: unknown whether the
other ~30 test files still pass. Ruff/black/mypy have not been run at all since the 4.4-4.8
edits. **Treat this chunk as unverified until proven otherwise — do not report it as done.**

### What 4.4-4.8 actually changed, conceptually

The previous handoff's own investigation (re-read this session) revealed the existing
`_run_cmd` completion path was quietly violating design.md decision 1 ("raw provider
dictionaries do not cross into writers"): for Claude/OpenCode it reduced a fully-formed
`ContextUsageSample` down to a bare `{"input_tokens": ...}` dict and then had the writer
*re-derive* model/limit from session config, discarding the sample's own basis/status/etc.
For Codex, the stdout `turn.completed.usage` (cumulative across the whole exec) was being
written directly as if it were an exact reading, even though `CodexRolloutCollector` (built
last session, tested, never wired in) exists specifically to supply the accurate
non-cumulative number, and there's an already-built-and-tested `_select_codex_usage(rollout,
cumulative_estimate)` preference helper (task 3.4) that was sitting unused. This chunk wires
all of that up.

1. **One canonical writer** (`_write_canonical_context_usage` in `watchdog.py`, replacing
   `_write_context_usage`, `_write_codex_context_usage`, `_write_context_usage_from_wire` —
   all three deleted): serializes a `ContextUsageSample` using its own field names
   (`status`/`context_tokens`/`limit_tokens`/`percent`/`model`/`session_id`/`source`/`basis`/
   `breakdown`/`observed_at`) plus `agent`, via temp-file-then-`os.replace` for an atomic
   write. No `tokens_used`/`context_limit`/`warning`/`critical`/`threshold_*` fields — those
   were moved to the one in-process reader (see point 5).
2. **Collectors instantiated and driven for real** (task 4.5): `_run_cmd` now builds a
   `CodexRolloutCollector`/`CopilotOtelCollector`/`KimiWireCollector` (based on
   is_codex/is_copilot/is_kimi_code) before spawn, calls `.setup(agent=agent)`, merges
   Copilot's `.env` into `proc_env` (handling the `proc_env is None` case — `
   _prepare_agent_env` returns `None`, not `{}`, when the agent has no custom env vars; a
   bare `.update()` on `None` would have crashed), calls `.bind(session_id=...)` once the
   session identity is known mid-stream, polls `.observe()` once per stdout line, does a
   final `.observe()` via `.final_poll()` after stdout closes, then `.close()`.
3. **New-session reset to unavailable** (task 4.6): a small block right after
   `session_id = session_id_ref[0]` inside the stdout loop detects "session identity just
   became known and differs from what we're bound to"; if it's *not* the resume target
   (`run_session_id`), it's a genuinely new session, so it immediately writes
   `ContextUsageSample(status="unavailable", source=runner_type)` before binding the
   collector. Applied uniformly (not just for collector-backed runners).
4. **Codex uses `_select_codex_usage`** (already existed, now actually called): prefers
   `collector_sample` (rollout-derived, exact) over `usage_data_for_context` (stdout
   cumulative estimate). If the *fallback* wins (rollout unresolvable) and it has no
   `limit_tokens`, it gets patched with a `CODEX_MODEL_CONTEXT_LIMITS.get(model, 128000)`
   fallback via `dataclasses.replace` (preserves old behavior's "always show *some*
   percentage" for that fallback path — the rollout-derived winner is never touched, since
   it already carries its own accurate `model_context_window`).
5. **Threshold policy moved into the one reader**, `WatchdogMonitor._check_context_usage`
   (only in-process consumer of the on-disk file besides Hub-push): now computes
   `warning`/`critical`/`threshold_warning`/`threshold_critical` itself from the canonical
   `status`+`percent`, gated on `status == "measured"` (design.md decision 12: "estimated"
   samples don't auto-warn). This keeps `_write_compact_decision` and the Hub-push path
   completely unchanged — they still read `data.get("warning")` etc., just now computed at
   read time instead of write time.
6. **`_make_direct_trigger_callback`'s Hub-UI "[NewSession]" reset path** (a *different*,
   pre-existing reset call site, unrelated to `_run_cmd`) was also switched from a hand-rolled
   dict + the old `_reset_context_usage(recipient)` call to
   `_write_canonical_context_usage(recipient, ContextUsageSample(status="unavailable",
   source="watchdog"))`, for consistency — same reset semantics, one code path.
7. **Legacy Kimi `--wire` (v1) mode** (JSON-RPC, `_KimiWireParser` — NOT the same thing as
   `KimiWireCollector`, which is for kimi-code v0.29.x): parsing is completely untouched
   (design.md decision 10: v1 stays regression-only). Only its *persistence* step changed —
   `_kimi_wire_legacy_sample(wire_usage_dict)` converts the legacy dict to a
   `ContextUsageSample` right before the shared writer, replacing the bespoke
   `_write_context_usage_from_wire`. `_reset_context_usage` (the old legacy dict-shape reset,
   used only by wire-mode's compaction-transition reset) was deliberately left completely
   alone — different trigger, different era, out of scope.
8. **Copilot deliberately gets no model/limit patch.** Design decision 4's table lists
   Copilot's limit mapping as "resolved model metadata; absent if unknown" — same wording as
   Claude's row — but there is no Copilot model→limit table anywhere in the codebase (unlike
   Codex's `CODEX_MODEL_CONTEXT_LIMITS` or OpenCode's own catalog file), and
   `_copilot_otel_usage_sample`'s own docstring already says its limit "stays absent rather
   than fabricated from a table". No section-3 task built a Copilot limit resolver (unlike
   OpenCode's 3.15/3.16). Building one now would be scope creep beyond what's asked; left as
   an open item (see Open questions).
9. **Claude/OpenCode's stdout-native sample is now passed straight through** as the actual
   `ContextUsageSample` object (not reduced to a dict), then patched via `dataclasses.replace`
   with `resolved_model`/`resolved_limit` computed *once* per invocation (not per line) —
   Claude via the existing `_get_context_limit` table, OpenCode via
   `_opencode_model_context_limit(_opencode_models_catalog(), model)` (the section-3 work the
   previous handoff explicitly flagged as section-4's job to wire in).

## Files touched

- `src/agentweave/watchdog.py` — this session's 4.4-4.8 diff (uncommitted): `+dataclasses`
  import; deleted `_write_context_usage`, `_write_codex_context_usage`,
  `_write_context_usage_from_wire`; added `_canonical_context_usage_dict`,
  `_write_canonical_context_usage`, `_kimi_wire_legacy_sample`; rewrote `_run_cmd`'s pre-spawn
  setup (model/limit resolution, collector instantiation/env merge), the stdout loop (usage
  capture now keeps real `ContextUsageSample` objects, not dicts; added session-bind/reset
  block; added per-line `collector.observe()`), and the completion block (final_poll/close,
  single writer-selection block replacing the three old write-context-usage sections);
  updated `WatchdogMonitor._check_context_usage` to compute warning/critical/thresholds from
  canonical fields; updated `_make_direct_trigger_callback`'s new-session reset block.
  Confirmed via `python -c "import agentweave.watchdog"` (clean) and grep (zero remaining
  references to the three deleted function names anywhere in `src/`).
- `tests/test_watchdog.py` — replaced `TestWriteCodexContextUsage` (tested a now-deleted
  function) with `TestWriteCanonicalContextUsage` (4 tests) and `TestKimiWireLegacySample` (2
  tests); updated the top import block (removed `_write_codex_context_usage`, added
  `_write_canonical_context_usage`, `_kimi_wire_legacy_sample`). **Only this file has been
  test-run** (`pytest tests/test_watchdog.py -q` → 383 passed) — the 4.4-4.8 collector-wiring/
  session-reset/writer-consolidation behavior itself has **no new end-to-end tests yet**
  (unlike 4.1-4.3, which got 18 new tests covering the actual wired behavior via
  `_run_agent_subprocess` + mocked Popen). This is the biggest gap before this chunk can be
  called done.
- `openspec/changes/add-agent-stream-kinds/tasks.md` — **NOT yet updated**. 4.1-4.3 show `[x]`
  (committed). 4.4-4.8 are still `[ ]` even though the code is written — do not check them off
  until verification + new tests land.
- `.claude/handoffs/LATEST.md` — about to be rewritten by this handoff.

## Key decisions

- **Threshold policy (warning/critical/threshold_warning/threshold_critical) moved from
  writer to the one in-process reader**, gated on `status == "measured"` per design.md
  decision 12. Rationale: the canonical `ContextUsageSample` has no such fields at all
  (decision 3's field list is exhaustive), and decision 7 says writers emit *only* the
  canonical schema. Old on-disk files from before this migration (if a watchdog restarts
  mid-rollout) will transiently show `warning=False` regardless of their embedded old
  `warning` key, until the next write cycle overwrites them with the canonical shape —
  accepted as a short-lived, self-healing gap since context-usage files get rewritten every
  run cycle in practice. This was a deliberate simplification, not an oversight — full
  legacy-alias reading is explicitly task 4.9/4.10 (next chunk), not this one.
- **Codex's stdout cumulative estimate is kept, not discarded**, specifically because
  `_select_codex_usage` and `_codex_usage_sample`'s own docstring ("supersedes it whenever the
  matching rollout can be resolved") already describe exactly this two-producer-with-fallback
  design from section 3 — discarding it outright would have been building the wrong thing
  despite the infrastructure already existing and being tested (`TestSelectCodexUsage`,
  pre-existing).
- **Copilot gets no coordinator-level model/limit patch** (see point 8 above) — a deliberate
  scope boundary, flagged as an open question below rather than silently building a new
  Copilot model-limit table this session.
- **`dataclasses.replace(...)` used to patch model/limit onto an already-constructed
  `ContextUsageSample`** rather than reconstructing one from scratch, specifically because
  `ContextUsageSample.__post_init__` (which recomputes `percent` from `context_tokens`/
  `limit_tokens`) re-runs on `replace()` (it goes through `__init__` again) — confirmed this
  is the correct way to get `percent` recomputed after patching in a limit that wasn't known
  at construction time, rather than leaving a stale `percent=None`.
- **Session-bind/reset logic applies uniformly to all runner types**, not gated behind
  `collector is not None`, so Claude/OpenCode's context also correctly resets to unavailable
  on a genuinely new (non-resumed) session, even though they have no collector.

## Constraints and user directives (verbatim)

- User's only message this chunk was **"continue"** (after the 4.1-4.3 summary, which ended
  with an explicit offer to pause or continue into 4.4-4.8) — confirms proceeding into
  4.4-4.8 as previously proposed, not a request for anything different.
- All constraints carried forward from every previous handoff in this chain remain binding:
  - Kimi's session-status service (task 3.10) is intentionally **not implemented** — do not
    silently implement it.
  - New commits, not amends.
  - Zero new runtime dependencies (stdlib only) — this chunk added `dataclasses`/`itertools`
    (both stdlib, already used elsewhere in the file) and `os.replace`/`os.getpid` (stdlib).
  - Never commit `.agentweave/*`; use template loading not hardcoded template strings; lock
    task mutations; preserve unrelated dirty work; target Kimi v0.29.x only.
  - Live CLI probes must run in isolated scratch directories outside the repo, cleaned up
    after (not applicable this chunk — no new live probes were run).
  - Pushing the unpushed commits (now 13, `4c34fca` included) has never been asked for.

## Dead ends

- None tried-and-failed this chunk. One considered-and-rejected path: building a Copilot
  model→context-limit table so its sample could get the same model/limit patch as Claude/
  OpenCode — rejected as scope creep since no section-3 task built the supporting resolver
  infrastructure for it (unlike OpenCode's dedicated 3.15/3.16), and `_copilot_otel_usage_sample`'s
  own docstring already documents "absent rather than fabricated" as the intended behavior.
  Not implemented; flagged as an open question instead.

## Verification

- `python -c "import agentweave.watchdog"` — clean, no syntax/import errors.
- `grep` across `src/` for `_write_context_usage\b|_write_codex_context_usage|_write_context_usage_from_wire`
  — zero remaining references (all call sites updated/removed).
- `pytest tests/test_watchdog.py -q` — **383 passed** (this file only).

**Not run / explicitly unverified — do this first on resume:**
- `pytest tests/ -q` (full suite, ~939+ tests across ~30 files) — started, then the tool call
  was interrupted by the user (they invoked `/handoff` mid-run) before any output was
  produced. **Unknown pass/fail state for every file other than `test_watchdog.py`.** Given
  the scope of changes (a reader function used by the watchdog poll loop, a Hub-UI trigger
  callback), plausible candidates for a break: any test that constructs a raw context-usage
  dict and expects the OLD `warning`/`critical` keys to already be present in the *written*
  file rather than computed at read time, or any test for `_make_direct_trigger_callback`'s
  reset path expecting the old ad hoc `reset_data` shape.
- `ruff check src/ tests/`, `black --check src/ tests/`, `mypy src/` — none run since the
  4.4-4.8 edits. Black in particular is very likely to want reformatting (several new
  multi-line blocks were hand-formatted, matching the pattern from the 4.1-4.3 chunk where
  black did reformat two files).
- No new tests were written for the actual wired collector/reset/writer-selection behavior
  (only the writer function and the wire-legacy-sample converter got direct unit tests). The
  4.1-4.3 chunk's pattern (end-to-end via `_run_agent_subprocess` + mocked `Popen` +
  `_fake_proc`/`_prepare_codex_agent` helpers already in `tests/test_watchdog.py`) is the
  established template to extend for: a full Codex run producing a rollout file → collector
  sample wins over stdout estimate; a full Codex run with no resolvable rollout → cumulative
  estimate + `CODEX_MODEL_CONTEXT_LIMITS` fallback limit; a new-session mid-run reset to
  unavailable; Copilot's OTel env var actually reaching the mocked `Popen` call's `env` kwarg.
- `openspec status --change add-agent-stream-kinds --json` not run.

## Git state

- Branch: `master`
- HEAD: `4c34fca` ("Wire run_id, sequence, and lifecycle events into the invocation loop" —
  this is the 4.1-4.3 commit; **4.4-4.8 is NOT committed**, still working-tree changes)
- Upstream: `origin` → `https://github.com/gutohuida/AgentWeave.git`. 13 commits ahead of
  `origin/master` (12 inherited + `4c34fca`), none pushed. Not asked for this session.
- Working tree: dirty —
  - `M src/agentweave/watchdog.py` (4.4-4.8, uncommitted, unverified — see above)
  - `M tests/test_watchdog.py` (same)
  - `M .claude/handoffs/LATEST.md` (pointer, about to be rewritten by this handoff)
  - Six pre-existing untracked handoff files from earlier sessions (unrelated, unchanged)

## Next steps

1. **Run `pytest tests/ -q` to completion** and read the actual output. If anything besides
   `test_watchdog.py` fails, the most likely culprits are anything touching
   `WatchdogMonitor._check_context_usage`'s output shape or `_make_direct_trigger_callback`'s
   reset path (grep `tests/` for `_check_context_usage`, `_make_direct_trigger_callback`,
   `context_usage`, `_reset_context_usage` to find them). Fix before proceeding.
2. **Run `ruff check src/ tests/`, then `black src/ tests/` (auto-fix), then `black --check`
   again, then `mypy src/`** — same sequence as the 4.1-4.3 chunk. Re-run the full test suite
   after black reformats, since it rewrites files.
3. **Write end-to-end tests for the actual 4.4-4.8 wiring** (see the bulleted list under
   Verification above for the specific scenarios) — extend `tests/test_watchdog.py` using the
   `_fake_proc`/`_prepare_codex_agent` helpers already added in the 4.1-4.3 chunk (search for
   `def _fake_proc` and `def _prepare_codex_agent`). At minimum: a Codex run where a rollout
   file is set up (see `_write_codex_rollout` helper, already in the test file, used by
   `TestCodexRolloutCollector`) so `collector_sample` wins over the stdout estimate; a Codex
   run with an unresolvable rollout so the cumulative-estimate + `CODEX_MODEL_CONTEXT_LIMITS`
   fallback path fires; a mid-run new-session detection writing an `unavailable` snapshot
   before the collector's first real sample.
4. **Update `openspec/changes/add-agent-stream-kinds/tasks.md`** lines for 4.4-4.8 from `[ ]`
   to `[x]` only after steps 1-3 are green.
5. **Commit** (new commit, not amend) once 1-4 are done. Suggested scope: one commit for
   4.4-4.8 together (it's one coherent rewrite of `_run_cmd`'s usage-handling, not separable
   into 5 independent pieces the way section 3's collectors were).
6. Then either continue to **4.9-4.13** (legacy context readers/normalization, transport
   extension + tests, watchdog tests for restart/retry/failure scenarios) or check in with the
   user first — the original sub-chunking plan the user approved was "4.1-4.3, then 4.4-4.8,
   then 4.9-4.13" as three separate stops, so pausing after step 5 to report back (matching
   how the 4.1-4.3 chunk ended) is the consistent move, not an automatic continuation.

## Open questions for the user

- **Should Copilot's context sample get a resolved model/limit patch too**, matching Claude/
  OpenCode? Design decision 4's table wording is identical to Claude's row ("resolved model
  metadata; absent if unknown"), but no Copilot model→limit table exists anywhere in the
  codebase and no section-3 task built one. Left absent this session (see Key decisions) —
  worth confirming this is acceptable before section 5/6 (Hub/UI) build any display logic
  that assumes Copilot samples usually have a limit.
- Whether to push the now-13 unpushed commits to `origin/master` — still open, never asked in
  this chain.
- Whether to sub-chunk 4.9-4.13 further, or take it as one chunk — not yet raised.

## Read on resume

- `src/agentweave/watchdog.py` — specifically `_run_cmd` (search for `def _run_cmd`, the
  entire nested function, now substantially rewritten) and
  `_write_canonical_context_usage`/`_canonical_context_usage_dict`/`_kimi_wire_legacy_sample`
  (search for those names) — this is where steps 1-5 above all land.
- `tests/test_watchdog.py` — `TestWriteCanonicalContextUsage`, `TestKimiWireLegacySample` (new
  this chunk), and the 4.1-4.3 chunk's `_fake_proc`/`_prepare_codex_agent` helpers plus
  `TestLifecycleEventsCompletionAndRunError`/`TestLifecycleEventsSkipped`/
  `TestLifecycleEventRetrying` as the established end-to-end test pattern to extend for step 3.
- `openspec/changes/add-agent-stream-kinds/tasks.md` lines 95-107 (tasks 4.4-4.8, still
  unchecked) and design.md decisions 1, 4, 5, 6, 7, 12 (all directly relevant to what this
  chunk implements; already read this session, but re-reading decision 4's table is
  worthwhile for the Copilot open question specifically).
- `WatchdogMonitor._check_context_usage` and `_make_direct_trigger_callback` in
  `watchdog.py` — the two non-`_run_cmd` call sites this chunk also touched; check these
  first if the full test suite run in step 1 turns up a failure outside `test_watchdog.py`.
