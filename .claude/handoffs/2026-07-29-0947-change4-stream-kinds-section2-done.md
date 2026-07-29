# Handoff: Change 4 (add-agent-stream-kinds) — section 2 (all 5 stdout adapters) complete, section 3 next

**Date:** 2026-07-29T09:47:00+01:00 · **Branch:** `master` · **HEAD:** `7b957ca`
**Agent:** Claude (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-07-29-0155-change4-stream-kinds-adapters-in-progress.md`
**Status:** chunk complete (section 2 fully done); section 3 not started

## Goal

Implement Change 4 (`add-agent-stream-kinds`, folded with former Change 6), a 94-task plan at
`openspec/changes/add-agent-stream-kinds/tasks.md` that replaces five runners' (Claude, Codex,
OpenCode, Copilot, Kimi) ad-hoc `List[str]`/tuple stdout parsers with one canonical
`AgentStreamEvent`/`ContextUsageSample`/`ParsedRunnerLine` contract (`src/agentweave/
stream_events.py`), then threads that contract through the invocation lifecycle, Hub
persistence, and Hub UI. The goal in this session was to finish section 2 (stdout adapters),
which the previous handoff left at 3-of-5 runners done.

## Current state

**Sections 1 and 2 are both fully done — every task in both checked off in tasks.md.**
Section 1 (canonical contracts) was already complete before this session. Section 2 (17 tasks,
2.1–2.13) is now 17/17 checked off across 4 commits made this session:

- **Kimi** (`d70f2f0`): Rewrote `_KimiCodeParser.feed()` to return `ParsedRunnerLine`. Live-probed
  an installed Kimi Code CLI 0.29.1 (`kimi -p ... --output-format stream-json`) and found the
  actual wire format is the *flat* `{"role":..., "content":..., "tool_calls":...}` shape — the
  old docstring had the labels backwards, calling this shape "v1.x kimi-cli only" and calling a
  never-observed wrapped `{"type":"context.append_message","message":{...}}` shape "v0.x". Fixed
  the docstring/test framing (flat shape is now the primary/unprefixed tests; the wrapped shape
  is `legacy_wrapped_`-prefixed, regression-only). Also found and fixed a real (if latent) bug:
  `_KIMI_RESUME_RE = re.compile(r"kimi -r ([a-f0-9\-]{36})")` could never match Kimi Code 0.29.1's
  actual `session_`-prefixed session IDs (e.g. `session_2b9bd712-cc0f-4d85-8b4f-6fea27c83c3b`,
  confirmed live to be the exact string `--session` must be given verbatim to resume) — fixed the
  character class to `[A-Za-z0-9_\-]+`, and more importantly added a `role="meta"` /
  `session.resume_hint` → `SessionChange` mapping so the session ID is now captured in real time
  from the JSON event itself. No usage/context field appears anywhere in Kimi's print stream;
  that's out of scope for this adapter (comes from the session-status/Wire auxiliary collector,
  section 3). 24 tests kept (same count as before, same behavior), plus 1 new session-hint test.

- **Copilot** (`76266a1`): User installed the Copilot CLI locally mid-session, so this ended up
  live-verified (CLI 1.0.75) instead of the documentation-derived fixtures originally planned.
  Split `_parse_copilot_stdout_line` into a pure `_parse_copilot_stream_line` (matching the
  Claude/Codex pattern) plus a thin session-ID-extraction wrapper. Found the old adapter never
  rendered tool *results* at all — it only rendered `assistant.message.toolRequests` as
  announcements, which never carry success/failure. The new adapter sources tool_use/tool_result
  from the dedicated `tool.execution_start`/`tool.execution_complete` lifecycle pair instead,
  which does report `success`/`result.content`/`error.message`. `assistant.reasoning.content`
  was empty/opaque in every probe (gpt-5-mini doesn't expose readable reasoning by default) — only
  a non-empty value ever becomes a `thinking_event`. No usage field appears anywhere in this
  stream either (`session.usage_checkpoint` is aggregate billing, not context occupancy);
  Copilot's context tracking is OTel-only (section 3). 15 new tests.

- **Cross-adapter conformance** (`7b957ca`, task 2.13): Added `TestStreamAdapterConformance` in
  `tests/test_watchdog.py`, driving all five adapters (Claude, Codex, OpenCode, Copilot as pure
  functions; Kimi as a `_KimiCodeParser()` instance) through one shared calling convention via
  lambdas, asserting every event's `.kind` stays in `STREAM_EVENT_KINDS`, `usage` is always
  `None`/`ContextUsageSample`, and each adapter's own usage-only and text-only fixtures prove
  events/usage are genuinely independent. **Writing the garbage-input battery for this test
  caught a real, shared bug**: every one of the five adapters calls `.get("type", ...)` on the
  `json.loads(line)` result *outside* the try/except that catches decode failures — so a line
  that is syntactically valid JSON but not an object (`"null"`, `"42"`, `"[]"`, `"true"`, a bare
  string) parsed successfully and then crashed with an uncaught `AttributeError`, which would
  have propagated up through the watchdog's per-line stdout loop and killed that agent's
  invocation. Fixed all five (Claude, Codex, OpenCode, Copilot stream-line functions, plus
  `_KimiCodeParser.feed`) by raising inside the existing try/except when the parsed value isn't a
  `dict`, so it now falls through to the same malformed-line fallback already used for decode
  failures. 81 new conformance tests (65 garbage-input parametrized + 16 targeted).

**Not started: sections 3–9** (all still `[ ]` in tasks.md), starting with section 3 (`Auxiliary
context collectors`, tasks 3.1–3.16) — Codex rollout-file resolution, Copilot OTel-span
collection, Kimi session-status/Wire fallback, OpenCode model-limit resolution. This is
architecturally distinct from section 2: new `RunnerUsageCollector`-shaped code that reads
session-bound auxiliary files/services *alongside* (not instead of) the stdout adapters just
finished, feeding the *exact* (not estimated) context samples the design docs call for.

## Files touched

- `src/agentweave/watchdog.py` — this session's changes, in commit order:
  - `d70f2f0`: `_KimiCodeParser` class body fully rewritten (feed() now returns
    `ParsedRunnerLine`); `_KIMI_RESUME_RE` regex fixed; `_parse_kimi_stdout_line` updated to
    consume the new contract and extract `session_change`; import list gained
    `AgentStreamEvent`, `SessionChange`.
  - `76266a1`: `_parse_copilot_stdout_line` split into new pure `_parse_copilot_stream_line` +
    thin wrapper; the `is_copilot` branch in the main stdout loop (`_do_run_agent_subprocess`)
    updated to the `ParsedRunnerLine`-to-legacy-`readable_lines` bridge pattern.
  - `7b957ca`: added a `isinstance(data, dict)` guard (raising into the existing except block)
    to `_parse_claude_stream_line`, `_parse_codex_stream_line`, `_parse_opencode_stdout_line`,
    `_parse_copilot_stream_line`, and `_KimiCodeParser.feed` — the non-dict-JSON crash fix.
- `tests/test_watchdog.py` — this session's changes:
  - `d70f2f0`: `TestKimiCodeParser` fully rewritten in place (24 tests; unprefixed = flat shape
    confirmed live, `legacy_wrapped_`-prefixed = old wrapped shape, regression-only); top-level
    import gained `_KimiCodeParser`.
  - `76266a1`: new `TestParseCopilotStreamLine` class (15 tests) inserted between
    `TestAgentPingCmdCopilot` and `TestCopilotUsesPat`; top-level import gained
    `_parse_copilot_stream_line`.
  - `7b957ca`: new `TestStreamAdapterConformance` class (81 tests) inserted in the same location
    (before `TestCopilotUsesPat`); top-level import gained
    `from agentweave.stream_events import ContextUsageSample, ParsedRunnerLine, STREAM_EVENT_KINDS`.
- `openspec/changes/add-agent-stream-kinds/tasks.md` — checked off 2.9–2.13 (all of section 2 now
  `[x]`); 2.10's line also got an inline note that it was superseded by a live Copilot capture
  rather than staying documentation-derived.
- `.claude/handoffs/LATEST.md` — about to be rewritten by this handoff (was pointing at the
  previous one, `2026-07-29-0155-...`).

Nothing else changed. No OpenSpec proposal/design/spec files were edited this session (only the
tasks.md checkboxes). No Hub, CLI, or non-watchdog source files were touched.

## Key decisions

- **Kept `_KimiCodeParser` as a class, not a plain function**, even though its only prior state
  (`_assistant_count`) was write-only/dead and got dropped — the call site in
  `_do_run_agent_subprocess` instantiates it once and polymorphically calls `.feed()` alongside
  the genuinely-stateful `_KimiWireParser`/`_KimiParser`; changing that call-site pattern was out
  of scope for this task.
- **Relabeled which Kimi wire shape is "primary" based on live evidence, not the old docstring.**
  design.md decision 10 and the `agent-stream-events` spec both already said "Kimi conformance
  SHALL target the supported v0.29.x print stream" — the live probe confirmed that stream is the
  flat shape, so the rename (flat = primary/unprefixed tests, wrapped = `legacy_wrapped_`) makes
  the code match what the planning docs already specified, not a unilateral reinterpretation.
- **`_KimiWireParser` (the `--wire` JSON-RPC parser) was deliberately left untouched.** It's
  unreachable in every command `_agent_ping_cmd` currently builds — `use_wire_mode` is a dead
  parameter nothing ever sets `True`, and both the v0.x and v1.x command branches omit `--wire`.
  Task 2.11 only covers "the Kimi parser" (the print-stream one); rewriting genuinely dead code
  into the new contract wasn't requested and would have been unrequested scope.
- **Copilot tool_use/tool_result sourced from `tool.execution_start`/`tool.execution_complete`,
  not `assistant.message.toolRequests`.** Both describe the same call, but only the lifecycle
  pair reports success/failure — using it (a) matches the Codex adapter's existing
  `item.started`/`item.completed` correlation precedent and (b) fixes a real functionality gap
  (the old adapter never showed whether a tool call succeeded at all).
- **Did not chase down a populated `assistant.reasoning.content` fixture for Copilot.** Tried
  `--enable-reasoning-summaries --effort medium` with a few `--model` values; none were available
  under this account/plan (`Error: Model "X" from --model flag is not available`). Content stayed
  empty/opaque under every reachable condition, which is itself the safe, spec-compliant case
  (opaque reasoning must never be copied into content) — not blocking, just an untested branch.
- **Fixed the non-dict-JSON crash inline rather than filing it as a follow-up.** It was found
  *while writing* the task-2.13 conformance test this session already required, the fix is a
  one-line guard per adapter (5 lines total), and shipping a conformance test that documents a
  known crash as "expected" instead of fixing it would have been dishonest test design.

## Constraints and user directives (verbatim)

- "You can continue to copilot for testing" — user's message this session, after installing the
  Copilot CLI locally themselves; license to live-probe Copilot rather than stay
  documentation-derived.
- "continue" — user's message after the Copilot commit, confirming section 2.13 (cross-adapter
  conformance) should proceed next.
- From the inherited handoff chain, still binding for any remaining/future runner or collector
  work: target Kimi v0.29.x only, do not expand v1 support; never commit `.agentweave/*`; use
  template loading not hardcoded template strings; lock task mutations; preserve unrelated dirty
  work.
- Standing repo rule (CLAUDE.md): zero new runtime dependencies for the CLI/watchdog — every
  change this session is stdlib-only (`json`, `re`), consistent with this.

## Dead ends

- Tried to get a populated (non-opaque) `assistant.reasoning.content` fixture from Copilot via
  `--enable-reasoning-summaries --effort medium --model gpt-5-mini` → `Error: Model "gpt-5-mini"
  from --model flag is not available`; tried `--model gpt-5.4` (the exact example from `copilot
  --help`) → same "not available" error. Gave up after two attempts; not a code problem, just an
  account/plan model-availability limit in this environment. The empty-content case is already
  correctly handled (dropped, never smuggled into `content`), so this doesn't block anything —
  just means that specific branch stays proven-safe-on-empty rather than proven-correct-on-full.
- Copilot's `-p` prompt mode without `--allow-all-tools` did *not* hang or error as expected (the
  CLI help text implies `--allow-all-tools` is "required for non-interactive mode") — a read-only
  "list files" prompt completed fine without it. Not investigated further since it wasn't the
  thing being tested (was trying to trigger a permission-denial event) and isn't relevant to the
  adapter code.
- First attempt at probing Copilot reasoning-summaries picked `--model auto` implicitly (no
  `--model` flag) → `Error: Model "auto" does not support reasoning effort configuration`. Not a
  real dead end, just the reason the `--model gpt-5-mini`/`gpt-5.4` attempts above happened.

## Verification

Ran after each of the three commits this session (Kimi, Copilot, conformance+bugfix), and again
just before writing this handoff:

- `.venv\Scripts\python.exe -m pytest tests\ -q` — final run: **832 passed, 4 skipped** (up from
  736 at session start: +17 net Kimi test-count parity change — actually 24→24, no net change
  there, the count growth is +15 Copilot + 81 conformance +... let me be precise: 736 → 751 after
  Copilot (+15) → 832 after conformance (+81). The 4 pre-existing skips are unrelated/unchanged).
- `.venv\Scripts\python.exe -m ruff check src\ tests\` — all checks passed after each commit (one
  auto-fixable import-order violation caught and fixed with `--fix` after adding the
  `stream_events` import to the test file for the conformance commit).
- `.venv\Scripts\python.exe -m black --check src\ tests\` — clean after each commit (black
  auto-reformatted `watchdog.py`/`test_watchdog.py` at each step; always re-verified with a fresh
  `--check` afterward).
- `.venv\Scripts\python.exe -m mypy src\` — success after each commit (only the pyproject
  Python-3.8-unsupported configuration warning, pre-existing and unrelated).
- Live CLI probes: Kimi Code 0.29.1 (5 probes: plain reply, tool success, tool failure, bad-model
  stderr-only failure, session-resume round-trip) and GitHub Copilot CLI 1.0.75 (5 probes: plain
  reply, tool success, tool failure, reasoning-summaries attempt ×2 both rejected) — real JSON
  captured, inspected, used directly as fixtures, scratch files cleaned up afterward.
- Ad-hoc repro script confirming the non-dict-JSON crash existed pre-fix (`AttributeError:
  'NoneType'/'int'/'list'/'str'/'bool' object has no attribute 'get'` for all 5 adapters on
  `"null"`/`"42"`/`"[]"`/`'"just a string"'`/`"true"`) and confirming it was gone post-fix (same
  script, all five now return a valid `ParsedRunnerLine` instead of raising).
- `openspec status --change add-agent-stream-kinds --json` was **not** re-run this session (ran
  at the end of the previous session, showing all 4 planning artifacts `done`; the tasks.md
  checkbox count — now 30/94 — is tracked manually in the file itself, not by that command).

Not run:

- Hub backend/UI test suites (`hub\tests`, `hub\ui`) — untouched this session, no Hub-side files
  edited (that's sections 5–8).
- Any actual `mkdocs build` — MkDocs is not installed in this environment (noted in every prior
  handoff too, unrelated to this session's work).
- Section 3 collector code — none exists yet; nothing to verify.

## Git state

- Branch: `master`
- HEAD: `7b957ca` (message: "Add cross-adapter conformance tests and fix a shared non-dict-JSON
  crash")
- Upstream: `origin/master` is 8 commits behind (unchanged tracking baseline `bae45f1` from the
  previous handoff); nothing from this change has been pushed yet. Unpushed commits, oldest
  first:
  - `97bc0c4 Fold context-usage tracking into agent-stream-kinds`
  - `d619dbb Add canonical stream-event and context-usage contracts`
  - `ca8abd2 Migrate the Claude stdout adapter to canonical stream events`
  - `99df59d Migrate the Codex stdout adapter to canonical stream events`
  - `960782e Migrate the OpenCode stdout adapter to canonical stream events`
  - `d70f2f0 Migrate the Kimi stdout adapter to canonical stream events` (this session)
  - `76266a1 Migrate the Copilot stdout adapter to canonical stream events` (this session)
  - `7b957ca Add cross-adapter conformance tests and fix a shared non-dict-JSON crash` (this
    session)
- Working tree: clean except `.claude/handoffs/LATEST.md` (pointer update, about to be rewritten
  by this handoff) and the four pre-existing untracked handoff files from earlier sessions
  (unrelated to this work; already untracked before this session started). No application or
  OpenSpec source changes are uncommitted.
- Not asked to push this session.

## Next steps

1. **Read `openspec/changes/add-agent-stream-kinds/design.md`** decisions 1 and 5 (the
   `RunnerUsageCollector` shape and per-runner collector binding rules) and the full
   `specs/agent-context-usage/spec.md` file (not just the Kimi section read previously) — section
   3's 16 tasks are collector work, a different shape of code from section 2's per-line stdout
   adapters, and haven't been designed against in this session at all yet.
2. **Start with Codex (tasks 3.2–3.5)**, since Codex's rollout-file format was already
   live-probed in the *previous* session (see the exploration doc's "Codex rollout" table:
   `last_token_usage`, `model_context_window`, `total_token_usage` fields, confirmed via a real
   installed Codex CLI 0.145.0) — the least additional live-verification risk of the four
   collectors, and the codebase already has `_write_codex_context_usage` (in `watchdog.py`, tested
   by `TestWriteCodexContextUsage`) as a likely integration point to inspect first.
3. Implement `RunnerUsageCollector` per design.md decision 1 (task 3.1) before or alongside the
   first concrete collector — the interface should be validated against at least one real
   implementation (Codex), not designed in the abstract and then retrofitted.
4. After Codex, proceed to Copilot (3.6–3.9, needs a fresh live OTel-exporter probe — the
   installed Copilot CLI 1.0.75 supports `COPILOT_OTEL_FILE_EXPORTER_PATH` per design.md, but this
   session never actually set that env var and inspected the resulting file), then Kimi (3.10–
   3.14, needs a live probe of the session-status REST service if reachable, or the `agents/main/
   wire.jsonl` fallback file — neither was probed this session, only the print-stream stdout was),
   then OpenCode (3.15–3.16, model-catalog/config resolution — no live CLI interaction needed,
   pure config-reading logic).
5. Each collector should land as its own commit with a full pytest/ruff/black/mypy pass first,
   matching this session's and the previous session's one-commit-per-runner pattern.

## Open questions for the user

- None new this session. Whether to push the 8 unpushed commits to `origin/master` now or keep
  accumulating local history was not asked this session (carried forward as open from the
  previous handoff too).

## Read on resume

- `openspec/changes/add-agent-stream-kinds/tasks.md` — the authoritative 94-task checklist; read
  the full file to re-orient, not just section 3 (sections 1–2 being fully `[x]` is itself
  useful confirmation the tree matches this handoff).
- `openspec/changes/add-agent-stream-kinds/design.md` — decisions 1 ("Coordinate two producers at
  the invocation boundary" — the `RunnerUsageCollector` shape) and 5 ("Bind auxiliary collectors
  to the active invocation") are the normative design for section 3 and were only skimmed in the
  previous session, not read in full against this session's work.
- `openspec/changes/add-agent-stream-kinds/specs/agent-context-usage/spec.md` — full file; the
  Codex/Copilot/Kimi/OpenCode "context mapping" requirement sections are the per-runner
  collector specs section 3 must satisfy exactly.
- `src/agentweave/watchdog.py` — specifically `_write_codex_context_usage` and
  `_write_context_usage` (search for both; exact line numbers will have shifted from this
  session's edits) — the existing context-file-writing code section 3's collectors will feed
  into, and `_extract_kimi_code_session`/`_extract_codex_mcp_result`-style existing
  session/file-discovery helpers worth reusing rather than reinventing.
- `openspec/explorations/2026-07-29-stream-events-context-usage-boundary.md` — the fold-decision
  exploration with the full runner-by-runner live-probe evidence table (Codex rollout fields,
  Kimi `wire.jsonl` fields, Copilot OTel span fields) that section 3 must implement against;
  written in an *earlier* session (not this one), so worth a fresh read rather than assuming
  familiarity carried over.
