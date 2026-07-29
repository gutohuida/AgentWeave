# Handoff: Change 4 (add-agent-stream-kinds) — canonical contracts + 3/5 runner adapters done

**Date:** 2026-07-29T01:55:00+01:00 · **Branch:** `master` · **HEAD:** `960782e`
**Agent:** Claude (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-07-29-0040-change1-archived-stream-kinds-next.md`
**Status:** in progress

## Goal

Implement Change 4 (`add-agent-stream-kinds`), which the previous handoff described as
next. Mid-implementation, an uncommitted rewrite was found and — per user decision — folded
Change 6 (`fix-context-tracking-all-runners`) into Change 4: one combined change with two
capability specs (`agent-stream-events`, `agent-context-usage`) and a 94-task plan, so the
five runner adapters, invocation lifecycle, and fixtures are only built once instead of
twice. The goal now is working through those 94 tasks in `openspec/changes/add-agent-stream-kinds/tasks.md`,
section by section, committing after each independently-testable slice.

## Current state

**Section 1 (canonical contracts, 1.1-1.9): done.** `src/agentweave/stream_events.py` defines
`AgentStreamEvent`, `ContextUsageSample`, `ParsedRunnerLine`, `SessionChange`, `ParserControl`,
the seven-kind taxonomy, redaction (wraps `diagnostics.redact_secrets`), 64 KiB payload / 8 KiB
tool-result truncation, and the context-breakdown allowlist. 34 tests in
`tests/test_stream_events.py`.

**Section 2 (stdout adapters, 2.1-2.13): 3 of 5 runners done (2.1-2.8 checked off).**

- **Claude** (`_parse_claude_stream_line` in `watchdog.py`): rewritten to read tool_use/
  tool_result from their real location — Messages-API content blocks nested in assistant/user
  message `content` arrays — instead of the old code's synthetic top-level `type=="tool_use"`/
  `"tool_result"` checks, which real Claude Code stream-json never actually emits (dead code,
  now fixed). Context usage is now `input_tokens + cache_read_input_tokens +
  cache_creation_input_tokens` (previously only raw `input_tokens` — an undercount bug, now
  fixed). Only assistant-message usage is used; `result` usage is deliberately NOT converted to
  a sample (no fixture-proven need for the fallback yet — see design.md decision 4). 23 tests in
  `TestParseClaudeStreamLine`/`TestClaudeUsageSample`/`TestClaudeToolResultText`.
- **Codex** (`_parse_codex_stream_line`): rewritten and **verified against a live installed
  Codex CLI 0.145.0** (two probes: read-only `-s read-only` and workspace-write `-s
  workspace-write`, run from a scratch directory with `--skip-git-repo-check`). Confirmed live:
  `agent_message`, `command_execution` (`command`/`aggregated_output`/`exit_code`/`status`), and
  `file_change` (`changes: [{path, kind}]`, `status: in_progress|completed|failed`) shapes.
  `item.started`/`item.completed` now become a correlated `tool_use`/`tool_result` pair keyed by
  the item's own `id`. `reasoning`/`web_search`/`todo_list`/`plan_update` items were **not**
  observed live (the probed turns never triggered them) — mapped defensively, marked
  best-effort/unverified in both code comments and test docstrings. `turn.completed.usage`
  becomes an explicitly `estimated`/`cumulative_delta` sample (`input + output`, reasoning
  excluded, cache fields breakdown-only) since it's cumulative across a resumed session — the
  exact rollout-derived sample from a later auxiliary-collector section is meant to supersede
  it. Added `turn.failed`/top-level `error` → `error_event` mapping, which plausibly explains why
  the `_parse_codex_stdout_line` stale-session check (`"Session not found for thread_id"`) could
  never have actually fired before (the old parser dropped every top-level type it didn't
  explicitly branch on). 33 tests in `TestParseCodexStreamLine`.
- **OpenCode** (`_parse_opencode_stdout_line`): rewritten and **verified against a live
  installed OpenCode CLI 1.18.5** (a plain run + a `--thinking` run, `--format json`, using the
  free `opencode/big-pickle` model). Confirmed live: `step_start`/`tool_use`/`step_finish`/
  `text`/`reasoning` shapes. Previously this adapter only handled `"text"`/`"error"` and
  produced `usage_data=None` always — OpenCode context tracking literally did not exist before.
  `step_finish.part.tokens = {total, input, output, reasoning, cache:{read,write}}`; context is
  `total - reasoning` (confirmed against the live second-step sample where prior input moved
  into `cache.read` — proves replace-not-accumulate matters, not just theoretical). Confirmed
  live that a fast tool call arrives as ONE line with `state.status` already `"completed"` (no
  separate "running" line) — so a terminal-status `tool_use` line becomes `tool_result` only;
  the parser does not fabricate a `tool_use` that was never independently observed. 24 tests in
  `TestParseOpencodeStdoutLine`.

**Not started:** Copilot (2.9-2.10) — no Copilot CLI installed in this environment, so it can
only be documentation-derived (per design.md, that's an explicitly permitted state, but riskier
since nothing here has verified it). Kimi (2.11-2.12) — Kimi Code 0.29.1 **is** installed
locally; this was about to start when the session was interrupted for a handoff. Cross-adapter
conformance tests (2.13) — not started. Sections 3-9 (auxiliary collectors, invocation
lifecycle, Hub persistence/validation, Hub UI, verification/docs) — not started at all; each has
its own tracked task below.

For each of the three finished adapters, the loop's per-runner branch in the big `_run_cmd`
function inside `watchdog.py` was updated with a **small bridge**: it calls the new canonical
parser, then converts `ParsedRunnerLine.events` back into the `readable_lines: list[str]` the
rest of the loop still expects, and extracts `usage_data: Optional[dict]` from
`ParsedRunnerLine.usage` in the shape the existing `_write_context_usage`/`_write_codex_context_usage`
writers expect. This is deliberate: it lets each adapter ship independently, tested, with
correct arithmetic, without also having to rewrite the shared invocation loop, Hub transport,
and UI in the same commit. Section 4 (`Invocation lifecycle and canonical context delivery`)
is where that bridge gets replaced with real structured delivery end-to-end for all five
runners at once.

## Files touched

- `src/agentweave/stream_events.py` — new canonical contracts module; finished (section 1).
- `tests/test_stream_events.py` — new; finished (section 1).
- `src/agentweave/watchdog.py` — imports from `.stream_events`; `_claude_usage_sample`,
  `_claude_tool_result_text`, `_parse_claude_stream_line`, `_parse_claude_stdout_line` rewritten;
  `_codex_usage_sample`, `_codex_file_change_summary`, `_parse_codex_stream_line`,
  `_parse_codex_stdout_line` rewritten; `_opencode_usage_sample`, `_parse_opencode_stdout_line`
  rewritten; three loop call sites (Claude/Codex/OpenCode branches inside `_run_cmd`) updated
  with bridge logic. Kimi (`_KimiCodeParser`, `_KimiWireParser`, `_parse_kimi_stdout_line`) and
  Copilot (`_parse_copilot_stdout_line`) are UNTOUCHED — still returning the old
  `tuple[list[str], Optional[dict]]` shape.
- `tests/test_watchdog.py` — added `TestClaudeUsageSample`, `TestClaudeToolResultText`,
  `TestParseClaudeStreamLine`, rewrote `TestParseCodexStreamLine`, added
  `TestParseOpencodeStdoutLine`; all finished and passing.
- `openspec/changes/add-agent-stream-kinds/tasks.md` — 1.1-1.9 and 2.1-2.8 checked off (17 of 94
  boxes now checked); 2.9 onward still unchecked.
- `openspec/changes/add-agent-stream-kinds/{proposal.md,design.md,specs/agent-stream-events/spec.md,specs/agent-context-usage/spec.md}` —
  committed as-is from the uncommitted fold rewrite found at session start; not further edited
  this session except via the tasks.md checkboxes above.
- `openspec/explorations/2026-07-29-stream-events-context-usage-boundary.md` — committed as-is
  (the fold-decision exploration found uncommitted at session start); one trailing-whitespace
  fix applied before commit.
- `.claude/handoffs/*` — this handoff plus `LATEST.md` pointer update; the three untracked prior
  handoff files from earlier in the day are pre-existing and unrelated to this work.

## Key decisions

- **Committed the Change 4/6 fold before implementing.** The user chose "commit the fold, then
  implement" when asked. Staged and committed `design.md`/`proposal.md`/`tasks.md`/both spec
  files/the exploration doc as one commit (`97bc0c4`) before starting section 1, so the planning
  rewrite has its own history separate from implementation.
- **One commit per adapter, not one commit for all of section 2.** Each runner's migration is
  independently reviewable and independently verified (or explicitly marked unverified for the
  parts that are), so each got its own commit (`ca8abd2` Claude, `99df59d` Codex, `960782e`
  OpenCode) after its own full test/lint/format/mypy pass.
- **Live-probed Codex and OpenCode instead of guessing wire formats.** Both CLIs are installed
  locally. Ran minimal, scoped, non-destructive turns (`codex exec --json -s read-only` /
  `-s workspace-write` in a scratch dir; `opencode run --format json` with a free model) and
  read the actual JSON rather than reconstructing the schema from memory. This caught that the
  old Codex parser's top-level `tool_use`/`tool_result` type checks were dead code, and that
  OpenCode had no context-usage path at all.
- **Marked unverified mappings as unverified rather than pretending confidence.** Codex's
  `reasoning`/`web_search`/`todo_list` items were never triggered by the probes; the code
  docstring, the `_parse_codex_stream_line` module comment, and the test docstrings all say so
  explicitly ("Best-effort mapping: not observed in the live probe").
- **Did not implement a Claude result-usage fallback.** design.md decision 4 and the
  `agent-context-usage` spec permit (not require) using final-`result` usage as a fixture-proven
  fallback when assistant-message usage is absent. No fixture proves a shape that actually lacks
  assistant usage, so the fallback was deliberately left unimplemented rather than guessed at.
- **Codex's `turn.completed` usage is `estimated`/`cumulative_delta`, never `measured`.**
  design.md decision 4 and the context-usage spec state stdout `turn.completed.usage` is
  cumulative across the whole exec invocation (confirmed live: resumed-turn stdout totals
  include prior turns). The stdout adapter alone (stateless, one line at a time) cannot compute
  a true delta without cross-invocation state, so it reports the raw cumulative total as an
  honest estimate; section 3's rollout collector is meant to supply the exact value.
- **Kept the old loop's readable-lines/usage-dict pipeline via a bridge, per adapter.** Rather
  than rewrite `_run_cmd`'s shared invocation loop (which all five runners funnel through) in the
  same commit as the first adapter, each finished adapter's branch converts
  `ParsedRunnerLine` back to the legacy shapes at the call site. This means Hub posting and
  context-file writes are behaviorally unchanged (aside from the arithmetic fixes) until section
  4 replaces the bridge with real structured delivery for all five runners together.

## Constraints and user directives (verbatim)

- "Commit the fold, then implement" (in response to a question about the uncommitted Change 4/6
  fold rewrite found at session start).
- "Continue now with Section 2" (in response to a pacing question after section 1 was done and
  committed).
- "Continue with Kimi now" (in response to a pacing question after Claude/Codex/OpenCode were
  done, noting Kimi's stateful parser and 20 existing tests, and that Copilot has no installed
  CLI).
- From the inherited handoff chain, still binding: target Kimi v0.29.x only, do not expand v1
  support; never commit `.agentweave/*`; use template loading not hardcoded template strings;
  lock task mutations; preserve unrelated dirty work.
- Standing repo rule (CLAUDE.md): zero new runtime dependencies for the CLI/watchdog — all
  `stream_events.py` code and the adapter rewrites are stdlib-only, consistent with this.

## Dead ends

- None encountered as outright failures this session. Two things worth flagging as "avoid
  repeating":
  - The first `tool_result_event` truncation test used a repeated `"x"` character string as
    "large output" — this tripped the existing `SECRET_VALUE_RE` regex (32+ char alnum run)
    and collapsed to `<redacted>` before truncation could be observed, making the test fail for
    the wrong reason. Fixed by using non-matching repeated text (`"not a secret line\n" * N`).
    If writing more truncation tests for the remaining adapters, avoid single-repeated-character
    padding for the same reason.
  - A first attempt at the Codex `_codex_usage_sample` breakdown dict had a pointless
    `if not cache_write else` branch with identical contents on both sides (an editing mistake,
    not a design dead end) — caught by re-reading the diff before commit and simplified to map
    `cache_write_input_tokens` into the existing `cache_creation_tokens` allowlisted breakdown
    field.

## Verification

Ran and passed after each of the three adapter commits (and again at the end of this session):

- `.venv\Scripts\python.exe -m pytest tests\ -q` — last full run: **736 passed, 4 skipped**
  (up from 653 baseline at the start of this work chunk; +34 stream_events + ~114 watchdog-side
  net new/changed). One intermittent `LockError` warning appeared once in a full-suite run from
  an unrelated pre-existing test (`test_task.py`-style lock contention under thread teardown);
  confirmed pre-existing by running `tests/test_task.py` alone against the pre-Claude-migration
  commit, where it does not reproduce — a flaky full-suite-only warning, not a regression, and
  not something this session's changes touch.
- `.venv\Scripts\python.exe -m ruff check src\ tests\` — all checks passed, after each commit.
- `.venv\Scripts\python.exe -m black --check src\ tests\` — clean, after each commit (black
  auto-formatted `stream_events.py`, `test_stream_events.py`, `watchdog.py`, and
  `test_watchdog.py` at various points; always re-verified with a fresh `--check` after).
- `.venv\Scripts\python.exe -m mypy src\` — success (only the pyproject Python-3.8-unsupported
  configuration warning, pre-existing and unrelated).
- Live CLI probes (see Key decisions) for Codex 0.145.0 and OpenCode 1.18.5 — real JSON events
  captured, inspected, and used directly as test fixtures; scratch files cleaned up afterward.
- `openspec validate add-agent-stream-kinds --strict` and `openspec status --change
  add-agent-stream-kinds --json` — valid, all four planning artifacts `done`, 0/94 → 17/94 tasks
  now checked in `tasks.md` (the `openspec status --json` "tasks" artifact tracks
  presence/shape, not per-checkbox completion, so it still reports the artifact as `done`
  either way — the checkbox count is tracked manually in tasks.md itself).

Not run:

- Hub backend/UI test suites (`hub/tests`, `hub/ui`) — untouched this session, no Hub-side files
  were edited yet (that's sections 5-8).
- Kimi or Copilot fixture tests — neither adapter has been touched yet.
- Any actual `mkdocs build` — MkDocs is not installed in this environment (pre-existing, noted
  in the previous handoff too).
- A live Kimi 0.29.1 probe — Kimi Code 0.29.1 IS installed (`kimi --version` confirmed), but no
  probe was run before this handoff was written; that's the literal next step.

## Git state

- Branch: `master`
- HEAD: `960782ec18f11b810332a39da0403408bb207974`
- Upstream: `origin/master` is 6 commits behind (`bae45f1` is the last pushed commit); nothing
  from this session has been pushed. Unpushed commits, oldest first:
  - `97bc0c4 Fold context-usage tracking into agent-stream-kinds`
  - `d619dbb Add canonical stream-event and context-usage contracts`
  - `ca8abd2 Migrate the Claude stdout adapter to canonical stream events`
  - `99df59d Migrate the Codex stdout adapter to canonical stream events`
  - `960782e Migrate the OpenCode stdout adapter to canonical stream events`
  - (`bae45f1` is the actual last-pushed commit; the 5 above plus the fold commit are unpushed —
    6 total unpushed commits including `97bc0c4`.)
- Working tree: clean except `.claude/handoffs/LATEST.md` (pointer update, about to be rewritten
  by this handoff) and the pre-existing untracked handoff files from earlier today. No
  application or OpenSpec source changes are uncommitted.
- Nothing has been pushed to `origin/master` this session; not asked to push.

## Next steps

1. **Probe Kimi 0.29.1 live** the same way Codex/OpenCode were probed: run a minimal, scoped
   `kimi` turn with `--print --output-format stream-json` (the flags already used by
   `_agent_ping_cmd` for kimi-code v0.x per `tests/test_watchdog.py::TestAgentPingCmdKimiCode`)
   in a scratch directory, capture real events, and confirm the `context.append_message`
   shape and any usage/session-status fields against `_KimiCodeParser`'s existing docstring
   assumptions (`src/agentweave/watchdog.py` line ~1500) before changing anything.
2. Refactor `_KimiCodeParser.feed()` (and the wire-mode `_KimiWireParser` around line 1323, and
   `_parse_kimi_stdout_line` around line 3651) to return `ParsedRunnerLine`/`AgentStreamEvent`
   values instead of `List[str]`, preserving every existing v0.x/v1.x behavior covered by the 20
   tests in `TestKimiCodeParser` (`tests/test_watchdog.py`, currently lines ~230-420) — rewrite
   those tests in place the same way `TestParseCodexStreamLine` and
   `TestParseOpencodeStdoutLine` were rewritten, not deleted. Preserve the module's existing
   v1-regression-only stance (task 2.11: "preserving existing v1 compatibility... SHALL NOT be
   expanded").
3. Add Kimi 0.29.x golden fixtures per task 2.12, run the full suite + ruff + black + mypy, check
   off 2.11-2.12 in `tasks.md`, commit.
4. Copilot (2.9-2.10): no CLI is installed here, so this must be documentation-derived per
   design.md's explicit allowance — flag clearly in code/test docstrings (same pattern as
   Codex's unverified `reasoning`/`web_search`/`todo_list`) that it is unverified pending a real
   CLI capture, per task 9.6's own acknowledgment of this gap.
5. Cross-adapter conformance tests (2.13): a shared test proving every adapter only ever returns
   the seven canonical kinds and never leaks a raw provider event, then check off 2.13 and
   close out section 2 as a whole.
6. Move to section 3 (`Auxiliary context collectors`) — task #3 in the tracked task list — which
   is where Codex's rollout-based exact context sample (superseding the `estimated` stdout
   sample), Copilot's OTel collector, Kimi's session-status collector, and OpenCode's model-limit
   resolution actually get implemented.

## Open questions for the user

- None new this session — the two from the previous handoff (whether to apply Change 4; whether
  the pre-existing `validate_spec.py` baseline failures need their own repair change) were
  effectively resolved by proceeding with implementation, and the `validate_spec.py` question
  remains open but out of scope for this change.
- Whether to push these 6 unpushed commits to `origin/master` now or continue accumulating local
  history — not asked this session.

## Read on resume

- `openspec/changes/add-agent-stream-kinds/tasks.md` — the authoritative 94-task checklist;
  read the full file, not just sections 2-3, to re-orient on what's left.
- `src/agentweave/stream_events.py` — the canonical contracts every adapter builds on; read in
  full before touching Kimi, since its constructors (`thinking_event`, `tool_use_event`,
  `tool_result_event`, `status_event`, `error_event`, `ContextUsageSample`) are what Kimi's
  refactor must produce.
- `src/agentweave/watchdog.py` around lines 1323-1660 (`_KimiWireParser`, `_KimiCodeParser`,
  `_detect_kimi_major_version`) and ~3651 (`_parse_kimi_stdout_line`) — the code about to be
  refactored.
- `tests/test_watchdog.py` around lines 230-420 (`TestKimiCodeParser`) — the 20 tests whose
  *behavior* must survive the refactor even though their assertions will need to change shape
  (string list → `ParsedRunnerLine`).
- `openspec/changes/add-agent-stream-kinds/design.md` decisions 4 and 10, and
  `openspec/changes/add-agent-stream-kinds/specs/agent-context-usage/spec.md` "Kimi 0.29 context
  mapping" section — the normative Kimi arithmetic (`inputOther + inputCacheRead +
  inputCacheCreation + output`, limit `max_input_tokens ?? max_context_tokens`, never
  `llm.request.maxTokens`) that the collector (section 3, not this session's adapter work) must
  implement, but which the stdout adapter refactor should not contradict.
- `openspec/explorations/2026-07-29-stream-events-context-usage-boundary.md` — the fold-decision
  rationale and full runner-by-runner evidence table, useful context for why Kimi's collector
  work (section 3) is scoped the way it is.
