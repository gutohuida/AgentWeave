# Handoff: Change 4 (add-agent-stream-kinds) — section 3, 3 of 4 collectors done (Codex, Copilot, Kimi); OpenCode next

**Date:** 2026-07-29T10:15:00+01:00 · **Branch:** `master` · **HEAD:** `399f6c2`
**Agent:** Claude (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-07-29-0947-change4-stream-kinds-section2-done.md`
**Status:** chunk complete (14/16 section-3 tasks done); OpenCode (3.15-3.16) not started

## Goal

Implement Change 4 (`add-agent-stream-kinds`, folded with former Change 6), a 94-task plan at
`openspec/changes/add-agent-stream-kinds/tasks.md`. Sections 1 (canonical contracts) and 2
(stdout adapters) were already fully done before this session. This session's goal was section 3
(`Auxiliary context collectors`, 16 tasks): new `RunnerUsageCollector`-shaped code that reads
session-bound auxiliary files/services *alongside* the stdout adapters, feeding exact (not
estimated) context samples for the four runners whose stdout streams don't carry accurate
context data on their own (Codex, Copilot, Kimi, OpenCode).

## Current state

**14 of 16 section-3 tasks done, in 3 commits this session** (`d834cb6`, `1c6970d`, `399f6c2`).
Every collector added this session follows the same shape: a pure `_<runner>_..._usage_sample()`
function (file/response-body → `ContextUsageSample`, independently testable), a resolution
helper that finds the right on-disk/network resource by the bound session ID only (never an
unscoped newest-file heuristic), and a `RunnerUsageCollector` subclass wiring
`setup`/`bind`/`observe`/`final_poll`/`close` around them.

- **Codex** (`d834cb6`, tasks 3.1-3.5): `RunnerUsageCollector` base class (relocated to right
  after the module logger in `399f6c2` — see below) plus `CodexRolloutCollector`. Resolves
  `$CODEX_HOME/sessions/**/rollout-*.jsonl` by the session ID embedded in the filename (bounded
  timestamp fallback verifies `session_meta.session_id` before accepting). Context tokens =
  `last_token_usage.total_tokens - reasoning_output_tokens`; limit = `model_context_window`;
  `cached_input_tokens` stays a breakdown only. `_select_codex_usage(rollout, estimate)` encodes
  "exact rollout always wins over the cumulative-delta stdout estimate" for section 4 to call
  later. 31 new tests.

- **Copilot** (`1c6970d`, tasks 3.6-3.9): `CopilotOtelCollector`. Copilot's stdout carries no
  usage field at all; `setup()` activates a unique per-invocation OTel file exporter
  (`COPILOT_OTEL_FILE_EXPORTER_PATH`) under `.agentweave/shared/copilot_otel/` (new
  `COPILOT_OTEL_DIR` constant) and explicitly pins
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false`; `close()` deletes the scratch file.
  Live-probed 3 real turns (plain reply, tool-calling turn, `task`-tool subagent turn) against
  installed Copilot CLI 1.0.75: the root `invoke_agent` span aggregates every LLM call (summing
  two chat spans gave the wrong inflated total — confirmed live: 13342+14074=27416, the
  aggregate's own reported value), and a `task`-tool subagent gets its own *nested* `invoke_agent`
  span, so its `chat` span's parent is that nested span, not the root — matching only `chat`
  spans whose `parentSpanId` equals the root's `spanId` naturally excludes both without
  special-casing. `gen_ai.usage.input_tokens` used directly (`basis=latest_request_input`);
  cache_read/cache_creation stay breakdowns. No context limit ever appears on these spans, so
  `limit_tokens` stays absent. `cache_creation.input_tokens` was never observed live in any probe
  (same honesty caveat as Copilot's opaque reasoning content from section 2). 26 new tests.

- **Kimi** (`399f6c2`, tasks 3.10-3.14): `KimiWireCollector`. **Task 3.10 (session-status
  service) was investigated live and intentionally NOT implemented** — this required a
  mid-session user decision, see Key decisions below. Implemented only the Wire fallback:
  resolves `agents/main/wire.jsonl` via the *existing* `~/.kimi-code/session_index.jsonl` (same
  file `_extract_kimi_code_session` already reads, keyed there by `workDir`, here by the exact
  `sessionId` this collector is bound to). Context tokens = latest `usageScope="turn"`
  `usage.record`'s `inputOther + inputCacheRead + inputCacheCreation + output`; limit resolved
  via `kimi provider list --json` (a fast local `config.toml` read, no network call) for the
  active model alias, checking a hypothetical `maxInputTokens` key before `maxContextSize` (only
  the latter has ever been observed populated). `llm.request.maxTokens` is never read at all —
  confirmed live across a real 3-turn session that it *decreases* turn over turn (262144 →
  238469 → 238378) while the model's real context window stays fixed at 262144 the whole time,
  proving it's a remaining-completion-budget figure, not a context limit. 29 new tests.

**Not started: OpenCode (tasks 3.15-3.16)** and all of sections 4-9. OpenCode 1.18.5 is installed
locally (confirmed same version live-probed in the previous session for the stdout adapter). No
OpenCode model-limit table exists anywhere in the codebase yet — clean starting point, nothing to
migrate away from.

## Files touched

- `src/agentweave/watchdog.py` — this session's changes, in commit order:
  - `d834cb6`: added `RunnerUsageCollector` (initially placed right before `_codex_home`),
    `_codex_home`, `_codex_sessions_dir`, `_codex_rollout_session_id`,
    `_resolve_codex_rollout_path`, `_codex_rollout_usage_sample`, `_select_codex_usage`,
    `CodexRolloutCollector`. Added `abc.ABC`/`abstractmethod` import.
  - `1c6970d`: added `_span_end_time`, `_copilot_latest_top_level_chat_span`,
    `_copilot_otel_usage_sample`, `CopilotOtelCollector`. Added `generate_id` import from
    `.utils`, `COPILOT_OTEL_DIR` import from `.constants`.
  - `399f6c2`: added `_kimi_home`, `_resolve_kimi_wire_path`, `_kimi_wire_usage_sample`,
    `_kimi_provider_catalog`, `_kimi_model_context_limit`, `KimiWireCollector`. **Relocated**
    `RunnerUsageCollector` from its `d834cb6` position (which was now *after* where
    `KimiWireCollector` needed it, since Kimi's code was inserted near `_extract_kimi_code_session`
    at line ~1760, far earlier in the file than the Codex/Copilot collector block at ~line 2840) to
    right after `logger = logging.getLogger(__name__)` near the top of the file — it's a shared
    base for three collectors now, not something that belongs physically next to just one of them.
  - Net: watchdog.py grew from 3946 lines (session start) to ~4600 lines across the three commits.
- `src/agentweave/constants.py` — `1c6970d` added `COPILOT_OTEL_DIR = SHARED_DIR /
  "copilot_otel"` (per-invocation OTel JSONL scratch files, gitignored via the existing
  `.agentweave/` blanket ignore).
- `tests/test_watchdog.py` — this session's changes:
  - `d834cb6`: `TestCodexRolloutPathResolution`, `TestCodexRolloutSessionId`,
    `TestCodexRolloutUsageSample`, `TestSelectCodexUsage`, `TestRunnerUsageCollectorInterface`,
    `TestCodexRolloutCollector` (31 tests total), inserted before `TestPopenUsesUtf8Encoding`.
  - `1c6970d`: `TestCopilotLatestTopLevelChatSpan`, `TestCopilotOtelUsageSample`,
    `TestCopilotOtelCollector` (26 tests), inserted in the same location.
  - `399f6c2`: `TestResolveKimiWirePath`, `TestKimiWireUsageSample`, `TestKimiModelContextLimit`,
    `TestKimiWireCollector` (29 tests), inserted in the same location.
  - Import list grew each commit to match (see current top-of-file imports for the full list —
    `CodexRolloutCollector`, `CopilotOtelCollector`, `KimiWireCollector`, `RunnerUsageCollector`,
    plus every pure helper function each collector wraps).
- `openspec/changes/add-agent-stream-kinds/tasks.md` — checked off 3.1-3.14 (all of section 3
  except 3.15-3.16); 3.10's line has an inline note (strikethrough + explanation) documenting the
  investigate-and-skip decision instead of a plain `[x]`.
- `.claude/handoffs/LATEST.md` — about to be rewritten by this handoff (was pointing at
  `2026-07-29-0947-...`).

Nothing else changed. No OpenSpec proposal/design/spec files were edited (only tasks.md
checkboxes). No Hub, CLI (`src/agentweave/cli.py`), or non-watchdog source files touched.

## Key decisions

- **Skipped Kimi's session-status service (task 3.10) after a live investigation, with explicit
  user sign-off — this is the most important decision this session and the next session must not
  silently "fix" by implementing it.** Design.md/spec.md describe `kimi web`'s
  `GET /api/v1/sessions/:id/status` as a preferred-when-available source ahead of the Wire
  fallback. Live testing against Kimi Code CLI 0.29.1 found it only reflects accurate usage for
  sessions actively driven through that *same running server process*. AgentWeave's watchdog
  always spawns `kimi -p ...` as its own standalone subprocess — confirmed via three separate
  tests that this never registers with any running `kimi web` server: (1) querying status for a
  session that had just used 28,915 tokens (per its own wire.jsonl) returned `context_tokens: 182`
  — stable and reproducible across repeated queries and fresh server instances; (2) tried
  `resume`/`attach`/`load`/`open`/`reload`/`sync` POST actions on the session — all returned
  `{"code":40001,"msg":"unsupported action: X"}`; (3) ran a headless `kimi -p` prompt *while a
  `kimi web` server was already running concurrently* (the most plausible way they could
  coordinate) — status was still wrong (174 tokens for a turn that surely used thousands). The
  endpoint itself is undocumented (checked the official docs site — no mention of any REST API).
  I surfaced this finding to the user via `AskUserQuestion` before proceeding (three options:
  skip / implement-with-cross-check-heuristic / implement-as-literally-specified); the user's
  first reply asked whether an alternative existed and to search further before giving up — the
  three tests above are that further search — after which they confirmed skipping was right ("If
  there is no alternative we can skip it"). Documented in tasks.md's 3.10 line and in the
  `399f6c2` commit message rather than silently dropped.
- **Kimi model-capability limit resolved via `kimi provider list --json` (a subprocess call to
  the CLI itself), not a hardcoded table or TOML parsing of `config.toml` directly.** The raw
  data lives in `~/.kimi-code/config.toml` under `[models."<alias>"]` sections, but parsing TOML
  would need either Python 3.11+'s stdlib `tomllib` (project claims 3.8+ support, though the
  *existing* mypy config already only supports 3.10+ — a pre-existing, unrelated inconsistency
  noted in every prior handoff) or a new `tomli` dependency, which would violate CLAUDE.md's
  "zero new runtime dependencies" rule. `kimi provider list --json` is a ~0.5s local subprocess
  call with no network round-trip (confirmed via `time`), matching the existing
  `_detect_kimi_major_version`'s established pattern of shelling out to `kimi --version`
  elsewhere in this same file.
- **`RunnerUsageCollector` relocated to near the top of the file, next to the module logger.**
  It was originally placed immediately before `_codex_home` (right before `CodexRolloutCollector`
  needed it) in `d834cb6`, which worked fine until Kimi's code in `399f6c2` needed to reference it
  from ~1100 lines earlier in the file (Python resolves base classes at class-definition time, so
  a forward reference across a plain module-level class statement is a `NameError`/`F821`, not
  deferred like a function body would be). Moving the shared interface to the top, once, was
  simpler and more correct than threading Kimi's new code down near the Codex/Copilot block only
  to keep the file's per-runner grouping.
- **Model preferred for Copilot is `gen_ai.response.model`, falling back to
  `gen_ai.request.model`.** Confirmed live: `gen_ai.request.model` can be the unresolved literal
  `"auto"` (whatever the user passed via `--model`), while `gen_ai.response.model` is always the
  concrete model that actually served the request (e.g. `"gpt-5-mini"`) — the right one to key
  any future limit lookup on.
- **Each collector's on-disk/subprocess resolution is scoped strictly to the bound session ID,
  never an unscoped "newest file" heuristic** (design.md decision 5, applied identically across
  Codex/Copilot/Kimi): Codex matches the rollout filename's embedded ID (bounded-timestamp
  fallback still verifies `session_meta` before accepting); Copilot generates a brand new
  per-invocation file path so there's nothing to disambiguate; Kimi looks up the exact
  `sessionId` in `session_index.jsonl`. All three collectors also reject a resolved
  sample whose *own* embedded session/conversation ID disagrees with the bound one, as defense in
  depth against a stale/reused file slipping through.

## Constraints and user directives (verbatim)

- "start" — user's message this session, confirming the plan (implement Codex's
  `RunnerUsageCollector` + collector first) laid out at the end of the previous handoff should
  proceed.
- "fix" — user's instruction to amend the Codex commit's message after I caught my own error (it
  said "104 new tests" when the real count was 31, confirmed via `pytest --collect-only`).
  Amended once; not a pattern to repeat casually — this repo's default is new commits, not
  amends, and this was an explicit one-off exception the user asked for.
- "yes" — confirming continuation to the Copilot OTel probe after I asked before starting it.
- "Yes, start on the Copilot OTel probe." — explicit go-ahead for the live Copilot investigation.
- "yes" — confirming continuation to Kimi after Copilot's commit landed.
- On the Kimi status-service question: **"Is there any alternative? Search documentation and
  test locally. If there is no alternative we can skip it."** — this is the operative instruction
  for any future work touching Kimi's status service. It was not a blanket "skip investigating
  things", it was "search harder before concluding no alternative exists" — satisfied this
  session via the three concrete tests listed under Key decisions above. Do not implement the
  status-service path without either a genuinely new alternative or another explicit user
  sign-off; the investigation already done should not need repeating from scratch.
- "yes" — confirming continuation to Kimi's implementation after the skip decision was settled.
- From the inherited handoff chain, still binding for any remaining/future runner or collector
  work: target Kimi v0.29.x only, do not expand v1 support; never commit `.agentweave/*`; use
  template loading not hardcoded template strings; lock task mutations; preserve unrelated dirty
  work; zero new runtime dependencies for the CLI/watchdog (every collector this session is
  stdlib-only — `json`, `re`, `subprocess`, `urllib` was not even needed since Kimi's HTTP-like
  interaction turned out unnecessary once the status path was dropped).

## Dead ends

- **Tried to make Kimi's session-status service accurate for a headless invocation — confirmed
  impossible client-side, not a code problem.** See Key decisions above for the three specific
  tests (resume/attach/reload actions all `"unsupported action"`; concurrent `kimi web` +
  `kimi -p` still stale; repeated queries of the same session stable-but-wrong). Do not re-attempt
  without a new angle (e.g. if a future Kimi Code version documents a supported attach mechanism).
- Considered parsing `~/.kimi-code/config.toml` directly for Kimi model capabilities instead of
  shelling out to `kimi provider list --json` — rejected because it would need a TOML parser
  dependency (`tomllib` is 3.11+-only in stdlib; the project's `pyproject.toml` claims 3.8+
  support) or fragile hand-rolled TOML parsing. The subprocess call is slower (~0.5s) but simpler,
  dependency-free, and already an established pattern in this file (`_detect_kimi_major_version`
  shells out to `kimi --version` the same way).
- Tried resolving Codex's rollout file by globbing `sessions/**/rollout-*<session-id>.jsonl`
  first, considered a bounded-timestamp-only fallback as primary — kept the filename-match-first
  design since Codex genuinely embeds the exact session ID in every rollout filename (confirmed
  live), making the bounded fallback a true fallback, only needed for a hypothetical future naming
  change, not the common case.

## Verification

Ran after each of the three commits this session, and again just before writing this handoff:

- `.venv\Scripts\python.exe -m pytest tests\ -q`:
  - After Codex (`d834cb6`): 863 passed, 4 skipped (832 → 863, +31).
  - After Copilot (`1c6970d`): 889 passed, 4 skipped (863 → 889, +26).
  - After Kimi (`399f6c2`): 918 passed, 4 skipped (889 → 918, +29).
  - Final run just now: **918 passed, 4 skipped** — matches, no drift since the last commit.
- `.venv\Scripts\python.exe -m ruff check src\ tests\` — clean after each commit. One real
  `F821 Undefined name RunnerUsageCollector` caught and fixed by the relocation described above
  (not a pre-existing/auto-fixable issue — a genuine ordering bug introduced then immediately
  caught within the same commit, before it was ever committed).
- `.venv\Scripts\python.exe -m black --check src\ tests\` — black auto-reformatted
  `tests\test_watchdog.py` after each commit's new test additions; always re-verified with a
  fresh `--check` afterward, clean every time.
- `.venv\Scripts\python.exe -m mypy src\` — success after each commit (only the pre-existing
  Python-3.8-unsupported pyproject warning, unrelated to this session).
- Live CLI probes, all conducted in isolated scratch directories outside the repo, cleaned up
  after each:
  - Copilot CLI 1.0.75: 3 real `COPILOT_OTEL_FILE_EXPORTER_PATH` captures (plain reply,
    tool-calling turn, `task`-tool subagent turn) — real OTel JSONL inspected directly, span
    shapes and field names used verbatim (trimmed of verbose irrelevant fields) as test fixtures.
  - Kimi Code CLI 0.29.1: inspected `~/.kimi-code/server/instances/*.json` +
    `~/.kimi-code/server.token` discovery files; queried the status endpoint ~6 times across 4
    separate `kimi web` server instances; inspected 3 real `wire.jsonl` files (single-turn and a
    3-turn session) for `usage.record`/`llm.request` shapes; ran `kimi provider list --json` and
    inspected the real `config.toml` it reads from.
  - All scratch directories/temp files from these probes were deleted before each commit; none
    were left in the repo working tree (confirmed via `git status --short` showing only the
    pre-existing untracked handoff files and the LATEST.md pointer, both unrelated).
- `openspec status --change add-agent-stream-kinds --json` was **not** re-run this session
  (tasks.md's checkbox count — now 44/94 — is tracked manually in the file itself).

Not run:

- Hub backend/UI test suites (`hub\tests`, `hub\ui`) — untouched this session (that's sections
  5-8).
- Any actual `mkdocs build` — MkDocs is not installed in this environment (noted in every prior
  handoff, unrelated).
- OpenCode collector code — none exists yet; nothing to verify.
- Section 4+ integration code (wiring any of these three collectors into the actual invocation
  loop in `_do_run_agent_subprocess`) — deliberately out of scope for section 3 per this
  session's own scoping decision (see previous handoff's same note re: Codex); that's section 4's
  job (tasks 4.4, 4.5, 4.8), not designed against yet.

## Git state

- Branch: `master`
- HEAD: `399f6c2` (message: "Implement the Kimi Wire context-usage collector")
- Upstream: `origin` → `https://github.com/gutohuida/AgentWeave.git`; `git status -sb` confirms
  `master...origin/master [ahead 11]` — 11 commits ahead, matching the 8 already-unpushed from
  the previous handoff plus this session's 3. (An earlier `git log origin/$(git branch
  --show-current)..HEAD` in this same session produced no output and fell through to a "no
  upstream" echo — false alarm, resolved via the commands above; disregard that artifact if it
  appears earlier in this session's transcript.) Nothing pushed this session. Unpushed commits,
  oldest first:
  - `99df59d Migrate the Codex stdout adapter to canonical stream events`
  - `960782e Migrate the OpenCode stdout adapter to canonical stream events`
  - `d70f2f0 Migrate the Kimi stdout adapter to canonical stream events`
  - `76266a1 Migrate the Copilot stdout adapter to canonical stream events`
  - `7b957ca Add cross-adapter conformance tests and fix a shared non-dict-JSON crash`
  - `d834cb6 Implement the Codex rollout context-usage collector` (this session)
  - `1c6970d Implement the Copilot OTel context-usage collector` (this session)
  - `399f6c2 Implement the Kimi Wire context-usage collector` (this session)
- Working tree: clean except `.claude/handoffs/LATEST.md` (pointer update, about to be rewritten
  by this handoff) and the five pre-existing untracked handoff files from earlier sessions
  (unrelated; already untracked before this session started).
- Not asked to push this session.

## Next steps

1. **Read `openspec/changes/add-agent-stream-kinds/tasks.md` section 3 tasks 3.15-3.16** (already
   quoted in full in this handoff's Current state section, but re-read in place to confirm no
   drift) and the relevant OpenCode paragraph in
   `openspec/changes/add-agent-stream-kinds/design.md` decision 4's table row: *"OpenCode |
   Current model `limit.input`, otherwise effective context fallback"* plus decision 5's line:
   *"Use stdout-native samples for Claude and OpenCode, while resolving OpenCode's current model
   capability from its own catalog/configuration rather than a primary hard-coded table."* — note
   OpenCode's *usage* itself already comes from stdout (done in section 2, task 2.7 — see
   `_opencode_usage_sample` in `watchdog.py`), so this remaining piece really is narrower than the
   other three: only the *limit* needs resolving from OpenCode's own catalog, not a whole new
   usage-source collector. This may mean 3.15-3.16 don't need a `RunnerUsageCollector` subclass at
   all — worth confirming against the spec before assuming one is required.
2. **Live-probe OpenCode 1.18.5's own model-catalog/config mechanism** (installed locally,
   confirmed above) to find where it exposes `limit.input` for the active model — likely an
   `opencode.json`/config file or a CLI subcommand analogous to `kimi provider list --json`. Do
   not assume the shape; verify live, following this session's established pattern for Codex/
   Copilot/Kimi.
3. Implement the OpenCode model-limit resolution, add tests per spec (declared input limits,
   fallback limits, model switches, unknown model metadata), verify with the full
   pytest/ruff/black/mypy pass, check off 3.15-3.16, commit — completing section 3 (16/16).
4. After OpenCode, section 3 is fully done. Section 4 (`Invocation lifecycle and canonical
   context delivery`, 13 tasks) is the natural next chunk: this is where the four collectors
   built this session actually get wired into `_do_run_agent_subprocess`'s invocation loop,
   replacing the legacy `_write_context_usage`/`_write_codex_context_usage`/
   `_write_context_usage_from_wire` call sites (see `watchdog.py` lines ~3430-3465 as of this
   session, though line numbers will have shifted). Read design.md decisions 1, 5, 6, 7 in full
   before starting — only decisions 1 and 5 were read this session and last.

## Open questions for the user

- Whether to push the now-11 unpushed commits to `origin/master` was not asked this session —
  carried forward as open from every previous handoff in this chain too.

## Read on resume

- `openspec/changes/add-agent-stream-kinds/tasks.md` — the authoritative 94-task checklist;
  sections 1-3 being `[x]` except 3.15-3.16 is itself useful confirmation the tree matches this
  handoff.
- `openspec/changes/add-agent-stream-kinds/design.md` — decision 4's OpenCode table row and
  decision 5's OpenCode line (both quoted in full in Next steps above, but worth reading in
  their surrounding context, particularly decision 5's framing of OpenCode as *not* needing a
  full auxiliary collector the way Codex/Copilot/Kimi did).
- `src/agentweave/watchdog.py` — specifically `_opencode_usage_sample` and
  `_parse_opencode_stdout_line` (the existing section-2 stdout adapter this session's limit work
  needs to feed into, not replace) and the newly-relocated `RunnerUsageCollector` near the top of
  the file (search for `class RunnerUsageCollector` — now right after `logger =
  logging.getLogger`), to decide whether OpenCode's limit resolution needs its own collector
  subclass or can be a plain helper function called from wherever `_opencode_usage_sample`'s
  result is consumed.
- `tests/test_watchdog.py` — specifically the three new collector test-class blocks added this
  session (`TestCodexRolloutCollector`, `TestCopilotOtelCollector`, `TestKimiWireCollector`, all
  immediately before `TestPopenUsesUtf8Encoding`) as the pattern to match for OpenCode's tests.
- `openspec/explorations/2026-07-29-stream-events-context-usage-boundary.md` — the fold-decision
  exploration with the runner-by-runner live-probe evidence table; written in an earlier session,
  worth a fresh read for the OpenCode-specific evidence row rather than assuming familiarity
  carried over.
